import httpx
import pytest

from higgsfield_cli.download import download_outputs, output_urls
from higgsfield_cli.jobs import JobStore


def reserve(store, fp="fp1", force=False):
    return store.reserve(kind="video", endpoint="e", arguments={"prompt": "p"}, fp=fp, force=force)


def test_reserve_blocks_duplicates_until_terminal_failure(tmp_path):
    store = JobStore(tmp_path / "jobs.json")
    job = reserve(store)["job"]
    assert reserve(store)["duplicate"]["id"] == job["id"]        # 'submitting' blokuje
    store.update(job["id"], request_id="r1", status="in_progress")
    assert "duplicate" in reserve(store)
    store.update(job["id"], status="completed")
    assert "duplicate" in reserve(store)                          # gotowe = nie płać drugi raz
    assert "job" in reserve(store, force=True)                    # chyba że świadomie


@pytest.mark.parametrize("status", ["failed", "nsfw", "canceled", "rejected", "upload_failed"])
def test_failed_jobs_do_not_block(tmp_path, status):
    store = JobStore(tmp_path / "jobs.json")
    job = reserve(store)["job"]
    store.update(job["id"], status=status)
    assert "job" in reserve(store)


def test_get_by_request_id_and_persistence(tmp_path):
    store = JobStore(tmp_path / "jobs.json")
    job = reserve(store)["job"]
    store.update(job["id"], request_id="r1", status="queued")
    again = JobStore(tmp_path / "jobs.json")
    assert again.get("r1")["status"] == "queued"
    assert again.get("nope") is None
    assert not (tmp_path / "jobs.lock").exists()


def test_output_urls_all_shapes():
    assert output_urls({"images": [{"url": "https://a"}, {"url": "https://b"}]}) == ["https://a", "https://b"]
    assert output_urls({"video": {"url": "https://v"}}) == ["https://v"]
    assert output_urls({"audio": {"url": "https://s"}, "audios": [{"url": "https://t"}]}) == ["https://s", "https://t"]
    assert output_urls({"status": "failed"}) == []


def test_download_names_files_and_sends_no_auth(tmp_path):
    seen = []

    def handler(req):
        seen.append(req.headers.get("authorization"))
        ctype = "video/mp4" if "vid" in str(req.url) else "image/png"
        return httpx.Response(200, content=b"DATA", headers={"content-type": ctype})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    files = download_outputs(["https://cdn/vid", "https://cdn/img.png"], tmp_path, kind="image",
                             request_id="abcdef1234", client=client)
    assert [f.rsplit("_", 1)[-1] for f in files] == ["1.mp4", "2.png"]
    assert all("_image_abcdef12_" in f for f in files)
    assert seen == [None, None]
    assert not list(tmp_path.glob("*.part"))


def test_download_rejects_non_https(tmp_path):
    with pytest.raises(ValueError):
        download_outputs(["http://cdn/x.mp4"], tmp_path, kind="video", request_id="r",
                         client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200))))
