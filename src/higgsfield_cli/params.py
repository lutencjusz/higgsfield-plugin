"""Czyste buildery argumentów żądań — walidacja zanim cokolwiek pójdzie do API.

Wysyłamy wartości jawnie (także domyślne), żeby odcisk żądania (fingerprint)
był stabilny i żeby w rejestrze było widać dokładnie, co zlecono.
"""

import hashlib
import json
import re
from pathlib import Path

from . import const

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class ValidationError(ValueError):
    pass


def _prompt(value, required=True):
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("Prompt nie może być pusty.")
    return value.strip()


def _choice(name, value, allowed):
    if value not in allowed:
        raise ValidationError(f"Niedozwolone {name}={value!r}. Dozwolone: {', '.join(map(str, allowed))}.")
    return value


def _int_range(name, value, lo, hi):
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise ValidationError(f"{name} musi być liczbą całkowitą z zakresu {lo}–{hi} (podano {value!r}).")
    return value


def is_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value or ""))


def build_image_args(prompt, *, aspect_ratio="4:3", resolution="720p", batch_size=1,
                     enhance_prompt=True, seed=None, style_id=None) -> dict:
    args = {
        "prompt": _prompt(prompt),
        "aspect_ratio": _choice("aspect_ratio", aspect_ratio, const.IMAGE_ASPECT_RATIOS),
        "resolution": _choice("resolution", resolution, const.IMAGE_RESOLUTIONS),
        "batch_size": _choice("batch_size", batch_size, const.IMAGE_BATCH_SIZES),
        "enhance_prompt": bool(enhance_prompt),
    }
    if seed is not None:
        args["seed"] = _int_range("seed", seed, *const.IMAGE_SEED_RANGE)
    if style_id is not None:
        if not is_uuid(style_id):
            raise ValidationError("style_id musi być UUID (lista: `higgsfield styles`).")
        args["style_id"] = style_id
    return args


def build_video_args(prompt, *, duration=5, resolution="720p", aspect_ratio="16:9",
                     generate_audio=True) -> dict:
    return {
        "prompt": _prompt(prompt),
        "resolution": _choice("resolution", resolution, const.VIDEO_RESOLUTIONS),
        "generate_audio": bool(generate_audio),
        "duration": _int_range("duration", duration, *const.VIDEO_DURATION_RANGE),
        "aspect_ratio": _choice("aspect_ratio", aspect_ratio, const.VIDEO_ASPECT_RATIOS),
    }


def animate_options(*, prompt=None, duration=5, resolution="720p", generate_audio=True) -> dict:
    """Pola image-to-video poza URL-ami obrazów — walidowane przed uploadem."""
    opts = {
        "resolution": _choice("resolution", resolution, const.VIDEO_RESOLUTIONS),
        "generate_audio": bool(generate_audio),
        "duration": _int_range("duration", duration, *const.VIDEO_DURATION_RANGE),
    }
    p = _prompt(prompt, required=False)
    if p is not None:
        opts["prompt"] = p
    return opts


def build_animate_args(image_url, *, end_image_url=None, **options) -> dict:
    """image_url/end_image_url to publiczne URL-e HTTPS (lokalne pliki najpierw upload)."""
    args = {"image_url": _https_url("image_url", image_url), **animate_options(**options)}
    if end_image_url is not None:
        args["end_image_url"] = _https_url("end_image_url", end_image_url)
    return args


def edit_options(prompt, *, model=const.EDIT_DEFAULT_MODEL, resolution=None, aspect_ratio=None,
                 quality=None, seed=None, n_images=1) -> dict:
    """Pola edycji poza URL-ami referencji — walidowane przed uploadem. Pomija wartości None
    (domyślne modelu), bo dozwolone wartości różnią się między modelami."""
    spec = const.EDIT_MODELS.get(model)
    if spec is None:
        raise ValidationError(f"Nieznany model edycji {model!r}. Dozwolone: {', '.join(const.EDIT_MODELS)}.")
    _int_range("liczba obrazów", n_images, 1, spec["max_images"])
    opts = {"prompt": _prompt(prompt)}
    if resolution is not None:
        opts["resolution"] = _choice("resolution", resolution, spec["resolutions"])
    if aspect_ratio is not None:
        opts["aspect_ratio"] = _choice("aspect_ratio", aspect_ratio, spec["aspect_ratios"])
    if quality is not None:
        if not spec["qualities"]:
            raise ValidationError(f"Model {model} nie ma parametru quality.")
        opts["quality"] = _choice("quality", quality, spec["qualities"])
    if seed is not None:
        if not spec["seed"]:
            raise ValidationError(f"Model {model} nie obsługuje seed.")
        opts["seed"] = _int_range("seed", seed, *const.IMAGE_SEED_RANGE)
    return opts


def build_edit_args(image_urls, **options) -> dict:
    """image_urls: publiczne URL-e HTTPS w kolejności referencji (obraz 1, 2, ...)."""
    opts = edit_options(n_images=len(image_urls), **options)
    return {**opts, "image_urls": [_https_url("image_urls", u) for u in image_urls]}


def check_image_ref(ref: str) -> None:
    """Obraz wejściowy: publiczny https:// albo obsługiwany plik lokalny."""
    if is_remote(ref):
        _https_url("obraz", ref)
    else:
        check_local_image(ref)


def _https_url(name, value):
    if not isinstance(value, str) or not value.startswith("https://"):
        raise ValidationError(f"{name} musi być publicznym adresem https:// (podano {value!r}).")
    return value


def is_remote(ref: str) -> bool:
    return ref.startswith(("https://", "http://"))


def check_local_image(ref: str) -> tuple[Path, str]:
    """Waliduje lokalny obraz wejściowy; zwraca (ścieżka, content-type)."""
    path = Path(ref).expanduser()
    if not path.is_file():
        raise ValidationError(f"Nie ma pliku: {path}")
    if path.stat().st_size == 0:
        raise ValidationError(f"Plik jest pusty: {path}")
    ctype = const.UPLOAD_IMAGE_TYPES.get(path.suffix.lower())
    if ctype is None:
        raise ValidationError(
            f"Nieobsługiwany typ obrazu {path.suffix!r}. Dozwolone: "
            + ", ".join(sorted(const.UPLOAD_IMAGE_TYPES))
        )
    return path, ctype


def input_ref(ref: str | None) -> str | None:
    """Stabilny identyfikator wejścia do odcisku: URL albo skrót SHA-256 pliku.

    Upload daje za każdym razem nowy public_url, więc odcisk z URL-a nie
    wykryłby ponownego zlecenia tego samego pliku.
    """
    if ref is None or is_remote(ref):
        return ref
    path, _ = check_local_image(ref)
    return "file-sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(endpoint: str, args: dict) -> str:
    blob = json.dumps({"endpoint": endpoint, "arguments": args}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
