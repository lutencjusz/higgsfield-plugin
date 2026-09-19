import pytest

from higgsfield_cli.pricing import output_size, seedance_estimate


@pytest.mark.parametrize("res,ar,size", [
    ("720p", "16:9", (1280, 720)), ("1080p", "16:9", (1920, 1080)), ("720p", "9:16", (720, 1280)),
    ("720p", "1:1", (720, 720)), ("4k", "16:9", (3840, 2160)), ("480p", "4:3", (640, 480)),
])
def test_output_size(res, ar, size):
    assert output_size(res, ar) == size


def test_reference_request_cost():
    # 5 s × 1280 × 720 × 24 / 1024 = 108 000 tokenów × $0.014/1k
    e = seedance_estimate({"resolution": "720p", "duration": 5, "aspect_ratio": "16:9"})
    assert e["video_tokens"] == 108_000 and e["approx_usd"] == 1.51


def test_4k_uses_lower_rate_and_animate_assumes_16_9():
    e = seedance_estimate({"resolution": "4k", "duration": 5})
    assert e["video_tokens"] == 972_000 and e["approx_usd"] == 7.78
    assert "16:9" in e["note"]
