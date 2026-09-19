import json

import pytest

from conftest import RID
from higgsfield_cli import cli, config, const
from higgsfield_cli.client import HfApiError, HfNetworkError


class FakeApi:
    def __init__(self, statuses=({"status": "completed", "video": {"url": "https://cdn/v.mp4"}},),
                 submit_error=None):
        self.statuses = list(statuses)
        self.submit_error = submit_error
        self.submitted, self.uploads, self.estimates, self.canceled = [], [], [], []

    def submit(self, endpoint, arguments):
        if self.submit_error:
            raise self.submit_error
        self.submitted.append((endpoint, arguments))
        return {"request_id": RID, "status": "queued", "correlation_id": "c1"}

    def status(self, rid):
        data = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return {"request_id": rid, **data}

    def upload(self, data, ctype):
        self.uploads.append(ctype)
        return "https://cdn/uploaded.jpg"

    def estimate(self, endpoint, arguments):
        self.estimates.append((endpoint, arguments))
        return {"credits": "10", "usd": "0.6"}

    def cancel(self, rid):
        self.canceled.append(rid)


@pytest.fixture
def fake(monkeypatch, tmp_path):
    api = FakeApi()
    monkeypatch.setattr(cli, "_api", lambda: api)
    downloads = []

    def fake_download(urls, dest, *, kind, request_id):
        downloads.append((urls, dest))
        return [str(dest / f"{kind}.bin")]

    monkeypatch.setattr(cli, "download_outputs", fake_download)
    monkeypatch.setenv(config.ENV_OUTPUT_DIR, str(tmp_path / "out"))
    api.downloads = downloads
    return api


def jobs():
    return json.loads(config.jobs_file().read_text(encoding="utf-8"))


def test_video_end_to_end(fake, capsys):
    assert cli.main(["video", "coastal road", "--duration", "6"]) == 0
    endpoint, args = fake.submitted[0]
    assert endpoint == const.VIDEO_ENDPOINT and args["duration"] == 6
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "completed" and out["request_id"] == RID
    assert fake.downloads[0][0] == ["https://cdn/v.mp4"]
    assert jobs()[0]["files"] == out["files"]


def test_duplicate_submission_is_blocked(fake):
    assert cli.main(["video", "same"]) == 0
    assert cli.main(["video", "same"]) == cli.EXIT_DUPLICATE
    assert len(fake.submitted) == 1
    assert cli.main(["video", "same", "--force"]) == 0
    assert len(fake.submitted) == 2


def test_validation_error_never_reaches_api(fake):
    with pytest.raises(SystemExit):  # argparse choices
        cli.main(["video", "x", "--resolution", "8k"])
    assert cli.main(["video", "x", "--duration", "30"]) == cli.EXIT_USAGE
    assert fake.submitted == []


def test_ambiguous_network_error_blocks_resubmission(fake, capsys):
    fake.submit_error = HfNetworkError("read timeout")
    assert cli.main(["video", "x"]) == cli.EXIT_ERROR
    assert jobs()[0]["status"] == const.LOCAL_SUBMIT_UNKNOWN
    assert "NIE WIADOMO" in capsys.readouterr().err
    fake.submit_error = None
    assert cli.main(["video", "x"]) == cli.EXIT_DUPLICATE


def test_rejected_submission_does_not_block_retry(fake):
    fake.submit_error = HfApiError(403, "Not enough credits")
    assert cli.main(["image", "x"]) == cli.EXIT_ERROR
    assert jobs()[0]["status"] == "rejected"
    fake.submit_error = None
    assert cli.main(["image", "x"]) == 0


@pytest.mark.parametrize("status,needle", [("nsfw", "Moderacja"), ("failed", "nie powiodło")])
def test_terminal_failures(fake, capsys, status, needle):
    fake.statuses = [{"status": status, "error": "Generation failed" if status == "failed" else None}]
    assert cli.main(["image", "x"]) == cli.EXIT_ERROR
    assert needle in capsys.readouterr().err
    assert jobs()[0]["status"] == status
    assert fake.downloads == []


def test_no_wait_then_wait_resumes(fake, capsys):
    assert cli.main(["video", "x", "--no-wait"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "queued"
    assert fake.downloads == []
    assert cli.main(["wait", RID]) == 0
    assert jobs()[0]["status"] == "completed"


def test_ownership_is_enforced(fake, capsys):
    other = "11111111-2222-3333-4444-555555555555"
    for cmd in ("status", "wait", "cancel"):
        assert cli.main([cmd, other]) == cli.EXIT_USAGE
    assert cli.main(["status", "not-a-uuid"]) == cli.EXIT_USAGE
    assert "nie występuje w rejestrze" in capsys.readouterr().err


def test_estimate_does_not_submit_or_register(fake, capsys):
    assert cli.main(["video", "x", "--estimate"]) == 0
    assert fake.submitted == [] and not config.jobs_file().exists()
    assert json.loads(capsys.readouterr().out)["credits"] == "10"


def test_animate_uploads_local_file_and_dedups_by_content(fake, tmp_path):
    img = tmp_path / "foto.jpg"
    img.write_bytes(b"JPEGDATA")
    assert cli.main(["animate", str(img), "--prompt", "wiatr"]) == 0
    endpoint, args = fake.submitted[0]
    assert endpoint == const.ANIMATE_ENDPOINT
    assert args["image_url"] == "https://cdn/uploaded.jpg" and fake.uploads == ["image/jpeg"]
    copy = tmp_path / "kopia.jpg"
    copy.write_bytes(b"JPEGDATA")
    assert cli.main(["animate", str(copy), "--prompt", "wiatr"]) == cli.EXIT_DUPLICATE
    assert len(fake.uploads) == 1  # duplikat wykryty przed uploadem


def test_animate_rejects_unsupported_file(fake, tmp_path):
    bmp = tmp_path / "x.bmp"
    bmp.write_bytes(b"BM")
    assert cli.main(["animate", str(bmp)]) == cli.EXIT_USAGE
    assert fake.uploads == []


def test_cancel_marks_job(fake):
    assert cli.main(["video", "x", "--no-wait"]) == 0
    assert cli.main(["cancel", RID]) == 0
    assert fake.canceled == [RID] and jobs()[0]["status"] == "canceled"


def test_missing_credentials_message(monkeypatch, capsys):
    assert cli.main(["jobs"]) == 0  # nie wymaga kluczy
    assert cli.main(["styles"]) == cli.EXIT_USAGE
    assert "higgsfield setup" in capsys.readouterr().err


def test_animate_estimate_does_not_upload(fake, tmp_path):
    img = tmp_path / "foto.png"
    img.write_bytes(b"PNG")
    assert cli.main(["animate", str(img), "--estimate", "--duration", "10"]) == 0
    assert fake.uploads == [] and fake.submitted == []
    assert fake.estimates[0][1]["image_url"].startswith("https://")
    assert fake.estimates[0][1]["duration"] == 10


def test_interrupted_submit_leaves_clear_duplicate_message(fake, capsys):
    fake.submit_error = KeyboardInterrupt()
    assert cli.main(["video", "x"]) == cli.EXIT_ERROR
    assert jobs()[0]["status"] == const.LOCAL_SUBMIT_UNKNOWN
    capsys.readouterr()
    fake.submit_error = None
    assert cli.main(["video", "x"]) == cli.EXIT_DUPLICATE
    err = capsys.readouterr().err
    assert "bez request_id" in err and "wait None" not in err


class CheckApi(FakeApi):
    def __init__(self, styles_error=None, estimate_error=None):
        super().__init__()
        self.styles_error, self.estimate_error = styles_error, estimate_error

    def soul_styles(self):
        if self.styles_error:
            raise self.styles_error
        return []

    def estimate(self, endpoint, arguments):
        if self.estimate_error and endpoint == const.ANIMATE_ENDPOINT:
            raise self.estimate_error
        return super().estimate(endpoint, arguments)


def run_check(monkeypatch, capsys, api):
    monkeypatch.setattr(cli, "_api", lambda: api)
    code = cli.main(["check"])
    out = capsys.readouterr().out
    return code, json.loads(out) if out.strip() else None


def test_check_all_ok_probes_three_endpoints(monkeypatch, capsys):
    api = CheckApi()
    code, report = run_check(monkeypatch, capsys, api)
    assert code == 0 and report["credentials"] == "ok"
    assert {e for e, _ in api.estimates} == {const.IMAGE_ENDPOINT, const.VIDEO_ENDPOINT, const.ANIMATE_ENDPOINT}


def test_check_401_means_bad_credentials(monkeypatch, capsys):
    code, report = run_check(monkeypatch, capsys, CheckApi(styles_error=HfApiError(401, "Invalid credentials")))
    assert code == cli.EXIT_ERROR and "401" in report["credentials"]


def test_check_styles_404_is_not_a_credentials_problem(monkeypatch, capsys):
    api = CheckApi(styles_error=HfApiError(404, "Not found"))
    code, report = run_check(monkeypatch, capsys, api)
    assert code == 0 and report["credentials"] == "ok" and "404" in report["soul_styles"]
    assert len(api.estimates) == 3


def test_check_reports_unavailable_endpoint(monkeypatch, capsys):
    code, report = run_check(monkeypatch, capsys, CheckApi(estimate_error=HfApiError(404, "Model not found")))
    assert code == cli.EXIT_ERROR
    assert report["endpoints"][const.ANIMATE_ENDPOINT]["ok"] is False
    assert report["endpoints"][const.VIDEO_ENDPOINT]["ok"] is True


def test_video_estimate_adds_local_cost_when_api_returns_description(fake, capsys):
    fake.estimate = lambda endpoint, args: {"type": "description", "pricing_description": "..."}
    assert cli.main(["video", "x", "--estimate", "--resolution", "1080p"]) == 0
    local = json.loads(capsys.readouterr().out)["local_estimate"]
    assert local["assumed_size"] == "1920x1080" and local["approx_usd"] == 3.4


def test_video_submit_prints_cost(fake, capsys):
    assert cli.main(["video", "x", "--no-wait"]) == 0
    assert "≈ 1.51 USD" in capsys.readouterr().err


def test_edit_uploads_references_in_order_and_dedups(fake, tmp_path):
    fake.statuses = [{"status": "completed", "images": [{"url": "https://cdn/out.png"}]}]
    bg, ppl = tmp_path / "bg.jpg", tmp_path / "ppl.png"
    bg.write_bytes(b"BG")
    ppl.write_bytes(b"PPL")
    argv = ["edit", "wstaw osoby z image 2 na plażę z image 1", "-i", str(bg), "-i", str(ppl),
            "--model", "marketing", "--resolution", "2k", "--quality", "high"]
    assert cli.main(argv) == 0
    endpoint, args = fake.submitted[0]
    assert endpoint == const.EDIT_MODELS["marketing"]["endpoint"]
    assert args["image_urls"] == ["https://cdn/uploaded.jpg"] * 2 and fake.uploads == ["image/jpeg", "image/png"]
    assert args["quality"] == "high" and args["resolution"] == "2k"
    assert jobs()[0]["kind"] == "edit"
    assert cli.main(argv) == cli.EXIT_DUPLICATE and len(fake.submitted) == 1


def test_edit_estimate_sends_no_photos(fake, tmp_path, capsys):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"A")
    assert cli.main(["edit", "x", "-i", str(img), "-i", str(img), "--estimate"]) == 0
    assert fake.uploads == [] and fake.submitted == []
    assert len(fake.estimates[0][1]["image_urls"]) == 2


def test_edit_validation_before_upload(fake, tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"A")
    assert cli.main(["edit", "x", "-i", str(img), "--quality", "high"]) == cli.EXIT_USAGE
    assert cli.main(["edit", "x"] + ["-i", str(img)] * 4) == cli.EXIT_USAGE
    assert fake.uploads == [] and fake.submitted == []
