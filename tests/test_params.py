import pytest

from higgsfield_cli import params
from higgsfield_cli.params import ValidationError


def test_video_defaults_match_reference_request():
    # Referencyjne żądanie z dokumentacji Seedance 2.0 text-to-video
    assert params.build_video_args("A cinematic tracking shot") == {
        "prompt": "A cinematic tracking shot",
        "resolution": "720p",
        "generate_audio": True,
        "duration": 5,
        "aspect_ratio": "16:9",
    }


@pytest.mark.parametrize("kwargs", [
    {"duration": 3}, {"duration": 16}, {"duration": True}, {"resolution": "2k"}, {"aspect_ratio": "2:1"},
])
def test_video_rejects_out_of_schema(kwargs):
    with pytest.raises(ValidationError):
        params.build_video_args("x", **kwargs)


@pytest.mark.parametrize("prompt", ["", "   ", None])
def test_prompt_required(prompt):
    with pytest.raises(ValidationError):
        params.build_video_args(prompt)
    with pytest.raises(ValidationError):
        params.build_image_args(prompt)


def test_image_args_and_limits():
    a = params.build_image_args("  portret  ", batch_size=4, seed=42)
    assert a["prompt"] == "portret" and a["batch_size"] == 4 and a["seed"] == 42
    with pytest.raises(ValidationError):
        params.build_image_args("x", batch_size=2)
    with pytest.raises(ValidationError):
        params.build_image_args("x", seed=0)
    with pytest.raises(ValidationError):
        params.build_image_args("x", resolution="4K")
    with pytest.raises(ValidationError):
        params.build_image_args("x", style_id="not-a-uuid")


def test_animate_requires_https_and_optional_prompt():
    a = params.build_animate_args("https://cdn/x.jpg", end_image_url="https://cdn/y.jpg", duration=8)
    assert a["image_url"] == "https://cdn/x.jpg" and a["end_image_url"] == "https://cdn/y.jpg"
    assert "prompt" not in a and "aspect_ratio" not in a  # image-to-video: kadr z obrazu
    with pytest.raises(ValidationError):
        params.build_animate_args("http://insecure/x.jpg")
    with pytest.raises(ValidationError):
        params.animate_options(prompt="  ")


def test_local_image_checks(tmp_path):
    good = tmp_path / "a.PNG"
    good.write_bytes(b"\x89PNG")
    assert params.check_local_image(str(good))[1] == "image/png"
    bad = tmp_path / "a.bmp"
    bad.write_bytes(b"BM")
    empty = tmp_path / "e.jpg"
    empty.write_bytes(b"")
    for ref in (str(bad), str(empty), str(tmp_path / "missing.jpg")):
        with pytest.raises(ValidationError):
            params.check_local_image(ref)


def test_input_ref_hashes_file_content(tmp_path):
    f1, f2 = tmp_path / "1.jpg", tmp_path / "2.jpg"
    f1.write_bytes(b"same")
    f2.write_bytes(b"same")
    assert params.input_ref(str(f1)) == params.input_ref(str(f2))
    assert params.input_ref("https://x/y.jpg") == "https://x/y.jpg"


def test_fingerprint_is_order_independent():
    assert params.fingerprint("e", {"a": 1, "b": 2}) == params.fingerprint("e", {"b": 2, "a": 1})
    assert params.fingerprint("e", {"a": 1}) != params.fingerprint("f", {"a": 1})


def test_edit_args_per_model_limits():
    a = params.build_edit_args(["https://cdn/a.jpg", "https://cdn/b.jpg"], prompt="x",
                               resolution="2k", aspect_ratio="4:3", seed=7)
    assert a == {"prompt": "x", "resolution": "2k", "aspect_ratio": "4:3", "seed": 7,
                 "image_urls": ["https://cdn/a.jpg", "https://cdn/b.jpg"]}
    m = params.build_edit_args(["https://cdn/a.jpg"], prompt="x", model="marketing",
                               resolution="4k", quality="high", aspect_ratio="auto")
    assert m["quality"] == "high" and "seed" not in m
    bad = [
        dict(image_urls=["https://cdn/a.jpg"] * 4),                        # qwen: maks. 3
        dict(image_urls=[]),                                                # min. 1
        dict(image_urls=["https://cdn/a.jpg"], resolution="4k"),            # 4k tylko marketing
        dict(image_urls=["https://cdn/a.jpg"], quality="high"),             # qwen bez quality
        dict(image_urls=["https://cdn/a.jpg"], model="grok", quality="high"),
        dict(image_urls=["https://cdn/a.jpg"], model="grok", seed=1),       # seed tylko qwen
        dict(image_urls=["http://cdn/a.jpg"]),
        dict(image_urls=["https://cdn/a.jpg"], model="nano"),
    ]
    for kw in bad:
        urls = kw.pop("image_urls")
        with pytest.raises(ValidationError):
            params.build_edit_args(urls, prompt="x", **kw)
