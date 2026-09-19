"""Klient Higgsfield oparty na oficjalnym SDK (higgsfield-client 0.2.x).

Z SDK bierzemy: skonfigurowanego klienta HTTP z nagłówkiem `Authorization: Key
id:secret`, upload przez presigned URL i cancel. Trzy odstępstwa od domyślnego
użycia SDK, każde wymuszone dokumentacją:

1. Transport bez ponowień (NoRetry). Domyślny ponawia także POST na 5xx/429,
   a generowanie nie ma klucza idempotencji — ponowiony POST to drugie
   (płatne) zlecenie. GET-y statusu ponawia nasz poller z backoffem.
2. Status czytamy jako JSON (SDK `status()` zwraca samą klasę statusu, bez
   URL-i wyników i pola `error`).
3. Nie używamy `subscribe()` — polluje co 0.5 s bez backoffu i bez limitu czasu.
"""

from functools import cached_property

import httpx
from higgsfield_client import HiggsfieldClientError, SyncClient
from higgsfield_client.http.retry import NoRetry
from higgsfield_client.http.transport import HttpTransport

from . import const

_HINTS = {
    400: "Nieprawidłowe parametry albo osiągnięty limit równoległych zadań konta.",
    401: "Nieprawidłowe lub brakujące poświadczenia — `higgsfield setup`.",
    403: "Brak kredytów na koncie — doładuj w https://console.higgsfield.ai.",
    404: "Nie znaleziono: model niedostępny dla konta albo request_id należy do innego konta.",
    422: "Walidacja treści żądania nie przeszła.",
    423: "Model jest tymczasowo zablokowany — spróbuj później.",
    503: "Model wyłączony lub niegotowy — spróbuj później.",
}


class HfApiError(Exception):
    def __init__(self, status_code: int | None, detail: str, correlation_id: str | None = None):
        self.status_code = status_code
        self.detail = detail
        self.correlation_id = correlation_id
        super().__init__(self.describe())

    @property
    def retryable(self) -> bool:
        """Bezpieczne do ponowienia tylko dla GET-ów (5xx)."""
        return self.status_code is not None and self.status_code >= 500

    @property
    def concurrency_limit(self) -> bool:
        return self.status_code == 400 and "concurrent" in self.detail.lower()

    def describe(self) -> str:
        code = self.status_code
        hint = "Osiągnięty limit równoległych zadań — poczekaj, aż trwające się zakończą." \
            if self.concurrency_limit else _HINTS.get(code, "Błąd serwera — spróbuj później." if code and code >= 500 else "")
        parts = [f"HTTP {code}" if code else "Błąd API", self.detail]
        if hint:
            parts.append(hint)
        if self.correlation_id:
            parts.append(f"X-Correlation-ID: {self.correlation_id}")
        return " | ".join(p for p in parts if p)


class HfNetworkError(Exception):
    """Błąd sieci/timeout. Po POST generowania wynik jest NIEZNANY (mogło przejść)."""


def _detail(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except ValueError:
        return resp.text.strip()[:500]
    detail = data.get("detail", data) if isinstance(data, dict) else data
    if isinstance(detail, list):  # błędy walidacji FastAPI
        return "; ".join(
            f"{'.'.join(str(x) for x in d.get('loc', []))}: {d.get('msg')}" if isinstance(d, dict) else str(d)
            for d in detail
        )
    return str(detail)


class _SdkClient(SyncClient):
    """SyncClient z transportem bez ponowień i opcjonalnym wstrzyknięciem httpx (testy)."""

    def __init__(self, *, api_key: str, timeout: float, http_client=None, upload_client=None):
        super().__init__(base_url=const.BASE_URL, timeout=timeout, api_key=api_key)
        if http_client is not None:
            self.__dict__["_client"] = http_client
        if upload_client is not None:
            self.__dict__["_upload_client"] = upload_client

    @cached_property
    def _transport(self) -> HttpTransport:
        return HttpTransport(self._client, NoRetry())


class HiggsfieldApi:
    def __init__(self, credentials: str, *, timeout: float = 60.0, http_client=None, upload_client=None):
        self._sdk = _SdkClient(api_key=credentials, timeout=timeout,
                               http_client=http_client, upload_client=upload_client)

    def _guard(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except HiggsfieldClientError as e:
            resp = getattr(e.__cause__, "response", None)
            if resp is None:
                raise HfApiError(None, str(e)) from e
            raise HfApiError(resp.status_code, _detail(resp), resp.headers.get("x-correlation-id")) from e
        except httpx.TransportError as e:
            raise HfNetworkError(f"{type(e).__name__}: {e}") from e

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        return self._guard(self._sdk._transport.request, method, url, **kwargs)

    def submit(self, endpoint: str, arguments: dict) -> dict:
        """POST generowania (jedna próba). Zwraca request_id/status_url/cancel_url + correlation_id."""
        resp = self._request("POST", f"/{endpoint}", json=arguments)
        data = resp.json()
        if not data.get("request_id"):
            raise HfApiError(resp.status_code, f"Brak request_id w odpowiedzi: {data}")
        data["correlation_id"] = resp.headers.get("x-correlation-id")
        return data

    def status(self, request_id: str) -> dict:
        return self._request("GET", f"/requests/{request_id}/status").json()

    def cancel(self, request_id: str) -> None:
        self._guard(self._sdk.cancel, request_id)

    def estimate(self, endpoint: str, arguments: dict) -> dict:
        """Koszt w kredytach/USD bez generowania (POST /estimate/<endpoint>)."""
        return self._request("POST", f"/estimate/{endpoint}", json=arguments).json()

    def soul_styles(self) -> list:
        return self._request("GET", const.SOUL_STYLES_PATH).json()

    def upload(self, data: bytes, content_type: str) -> str:
        """Upload przez presigned URL (SDK); zwraca public_url do image_url."""
        return self._guard(self._sdk.upload, data, content_type)
