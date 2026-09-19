"""Pobieranie wyników z CDN. Wyniki API żyją min. 7 dni — trzymamy je lokalnie.

Osobny klient httpx BEZ nagłówka Authorization: poświadczenia nie mogą trafić
do CDN/storage.
"""

import os
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import httpx

_EXT_BY_TYPE = {"video/mp4": ".mp4", "image/jpeg": ".jpg", "image/png": ".png",
                "image/webp": ".webp", "video/quicktime": ".mov"}


def output_urls(result: dict) -> list[str]:
    """URL-e mediów z odpowiedzi statusu: images[], video, audio, audios[]."""
    urls = [i["url"] for i in result.get("images") or [] if i.get("url")]
    for key in ("video", "audio"):
        if isinstance(result.get(key), dict) and result[key].get("url"):
            urls.append(result[key]["url"])
    urls += [a["url"] for a in result.get("audios") or [] if a.get("url")]
    return urls


def _extension(url: str, content_type: str | None) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix and len(suffix) <= 5:
        return suffix
    return _EXT_BY_TYPE.get((content_type or "").split(";")[0].strip(), ".bin")


def download_outputs(urls: list[str], dest: Path, *, kind: str, request_id: str,
                     client: httpx.Client | None = None) -> list[str]:
    own = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(30.0, read=300.0), follow_redirects=True)
    base = f"{date.today().isoformat()}_{kind}_{request_id[:8]}"
    saved = []
    try:
        for n, url in enumerate(urls, start=1):
            if not url.startswith("https://"):
                raise ValueError(f"Odrzucono niebezpieczny URL wyniku: {url}")
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                name = base + (f"_{n}" if len(urls) > 1 else "") + _extension(url, resp.headers.get("content-type"))
                target = dest / name
                part = target.with_suffix(target.suffix + ".part")
                with open(part, "wb") as fh:
                    for chunk in resp.iter_bytes():
                        fh.write(chunk)
                os.replace(part, target)
            saved.append(str(target))
    finally:
        if own:
            client.close()
    return saved
