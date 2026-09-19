import json

import httpx
import pytest

from conftest import RID, make_api
from higgsfield_cli.client import HfApiError, HfNetworkError, HiggsfieldApi


def accepted():
    return {"status": "queued", "request_id": RID,
            "status_url": f"https://api.higgsfield.ai/requests/{RID}/status",
            "cancel_url": f"https://api.higgsfield.ai/requests/{RID}/cancel"}


def test_submit_posts_to_endpoint_with_key_auth():
    seen = {}

    def handler(req):
        seen.update(url=str(req.url), auth=req.headers["authorization"], body=json.loads(req.content))
        return httpx.Response(200, json=accepted(), headers={"X-Correlation-ID": "corr-1"})

    data = make_api(handler).submit("bytedance/seedance-2.0/text-to-video", {"prompt": "p"})
    assert seen["url"] == "https://api.higgsfield.ai/bytedance/seedance-2.0/text-to-video"
    assert seen["auth"] == "Key kid:secret"
    assert seen["body"] == {"prompt": "p"}
    assert data["request_id"] == RID and data["correlation_id"] == "corr-1"


def test_sdk_client_uses_explicit_credentials():
    # Bez wstrzykniętego httpx: SDK buduje klienta z NASZYM kluczem, nie z HF_KEY
    api = HiggsfieldApi("abc:def")
    assert api._sdk._client.headers["authorization"] == "Key abc:def"


@pytest.mark.parametrize("code", [500, 502, 503, 429])
def test_submit_is_never_retried(code):
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(code, json={"detail": "boom"})

    with pytest.raises(HfApiError) as e:
        make_api(handler).submit("m", {"prompt": "p"})
    assert len(calls) == 1  # brak idempotencji -> jedna próba
    assert e.value.status_code == code


def test_error_mapping_keeps_detail_and_correlation():
    def handler(req):
        return httpx.Response(400, json={"detail": "Maximum number of concurrent requests (4) has been reached"},
                              headers={"X-Correlation-ID": "c-9"})

    with pytest.raises(HfApiError) as e:
        make_api(handler).submit("m", {})
    assert e.value.concurrency_limit
    assert "c-9" in str(e.value) and "limit równoległych" in str(e.value)
    assert not e.value.retryable


def test_validation_list_detail_is_readable():
    def handler(req):
        return httpx.Response(422, json={"detail": [{"loc": ["body", "duration"], "msg": "too big"}]})

    with pytest.raises(HfApiError) as e:
        make_api(handler).submit("m", {})
    assert "body.duration: too big" in e.value.detail


def test_network_error_is_distinguished():
    def handler(req):
        raise httpx.ConnectTimeout("timeout", request=req)

    with pytest.raises(HfNetworkError):
        make_api(handler).submit("m", {})


def test_status_returns_full_json_with_outputs():
    def handler(req):
        assert req.url.path == f"/requests/{RID}/status"
        return httpx.Response(200, json={"status": "completed", "request_id": RID,
                                         "video": {"url": "https://cdn/v.mp4"}})

    assert make_api(handler).status(RID)["video"]["url"] == "https://cdn/v.mp4"


def test_estimate_and_cancel_paths():
    paths = []

    def handler(req):
        paths.append((req.method, req.url.path))
        if req.url.path.startswith("/estimate/"):
            return httpx.Response(200, json={"credits": "1.5", "usd": "0.09"})
        return httpx.Response(202)

    api = make_api(handler)
    assert api.estimate("higgsfield-ai/soul/v2/standard", {"prompt": "p"})["credits"] == "1.5"
    api.cancel(RID)
    assert paths == [("POST", "/estimate/higgsfield-ai/soul/v2/standard"),
                     ("POST", f"/requests/{RID}/cancel")]


def test_upload_does_not_send_credentials_to_storage():
    storage = {}

    def api_handler(req):
        assert req.url.path == "/files/generate-upload-url"
        assert json.loads(req.content) == {"content_type": "image/png"}
        return httpx.Response(200, json={
            "public_url": "https://cdn/in.png", "upload_url": "https://storage/presigned",
            "content_type": "image/png",
            "upload_headers": {"Content-Type": "image/png", "x-amz-tagging": "retention=temporary"}})

    def storage_handler(req):
        storage.update(headers=dict(req.headers), body=req.content)
        return httpx.Response(200)

    url = make_api(api_handler, storage_handler).upload(b"PNGDATA", "image/png")
    assert url == "https://cdn/in.png"
    assert storage["body"] == b"PNGDATA"
    assert "authorization" not in storage["headers"]
    assert storage["headers"]["x-amz-tagging"] == "retention=temporary"
