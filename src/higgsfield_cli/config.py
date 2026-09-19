"""Konfiguracja i poświadczenia — zawsze poza repo/vaultem.

Katalog konfiguracji (config.json + jobs.json), pierwszy pasujący:
1. zmienna HF_CONFIG_DIR,
2. `.higgsfield/` w bieżącym folderze albo w folderze nadrzędnym (tryb projektu —
   np. Cowork, gdzie katalog domowy Windowsa jest niewidoczny),
3. `~/.higgsfield/`.
Względny `output_dir` w configu projektu liczy się od folderu projektu.
"""

import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".higgsfield"
LOCAL_DIR_NAME = ".higgsfield"

ENV_KEY_ID = "HF_API_KEY_ID"
ENV_KEY_SECRET = "HF_API_KEY_SECRET"
ENV_OUTPUT_DIR = "HF_OUTPUT_DIR"
ENV_CONFIG_DIR = "HF_CONFIG_DIR"


def _home() -> Path:
    return Path.home()


class ConfigError(Exception):
    pass


def config_dir() -> Path:
    env = os.environ.get(ENV_CONFIG_DIR)
    if env:
        return Path(env).expanduser()
    cwd = Path.cwd()
    home = _home()
    for folder in (cwd, *cwd.parents):
        if folder == home or folder in home.parents:
            break  # ~/.higgsfield to config domowy, nie projektowy
        local = folder / LOCAL_DIR_NAME
        if (local / "config.json").is_file():
            return local
    return CONFIG_DIR


def config_file() -> Path:
    return config_dir() / "config.json"


def jobs_file() -> Path:
    return config_dir() / "jobs.json"


def load_config() -> dict:
    path = config_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"Uszkodzony {path}: {e}") from e


def save_config(cfg: dict, *, local: bool = False) -> Path:
    path = Path.cwd() / LOCAL_DIR_NAME / "config.json" if local else config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_credentials() -> str:
    """Zwraca 'key_id:secret'. Kolejność: zmienne środowiskowe, potem config.json.

    Nazwy zmiennych jak w dokumentacji REST (HF_API_KEY_ID/HF_API_KEY_SECRET).
    SDK sam szuka innych nazw (HF_KEY, HF_API_KEY) — dlatego klucz przekazujemy
    mu jawnie i nie polegamy na jego wykrywaniu.
    """
    key_id = os.environ.get(ENV_KEY_ID)
    secret = os.environ.get(ENV_KEY_SECRET)
    if not (key_id and secret):
        cfg = load_config()
        key_id = key_id or cfg.get("api_key_id")
        secret = secret or cfg.get("api_key_secret")
    if not (key_id and secret):
        raise ConfigError(
            "Brak poświadczeń Higgsfield. Uruchom `higgsfield setup`, utwórz "
            f"{LOCAL_DIR_NAME}/config.json w folderze projektu albo ustaw "
            f"{ENV_KEY_ID} i {ENV_KEY_SECRET}. Klucze: https://console.higgsfield.ai"
        )
    return f"{key_id.strip()}:{secret.strip()}"


def output_dir(override: str | None = None) -> Path:
    raw = override or os.environ.get(ENV_OUTPUT_DIR)
    base = Path.cwd()
    if not raw:
        raw = load_config().get("output_dir")
        base = config_dir().parent  # względny output_dir z configu = względem projektu
    if raw:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = base / path
    else:
        path = config_dir() / "output"
    path.mkdir(parents=True, exist_ok=True)
    return path
