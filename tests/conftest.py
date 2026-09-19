import httpx
import pytest

from higgsfield_cli import config, const
from higgsfield_cli.client import HiggsfieldApi

RID = "d7e6c0f3-6699-4f6c-bb45-2ad7fd9158ff"


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Konfiguracja i rejestr zawsze w katalogu tymczasowym, bez prawdziwych kluczy."""
    home = tmp_path / "home"
    monkeypatch.setattr(config, "_home", lambda: home)
    monkeypatch.setattr(config, "CONFIG_DIR", home / ".higgsfield")
    monkeypatch.chdir(tmp_path)  # żaden prawdziwy ./.higgsfield/ nie może się wczytać
    for var in (config.ENV_KEY_ID, config.ENV_KEY_SECRET, config.ENV_OUTPUT_DIR, config.ENV_CONFIG_DIR):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def make_api(handler, upload_handler=None):
    """HiggsfieldApi na prawdziwym SDK, z httpx podmienionym na MockTransport."""
    http = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url=const.BASE_URL,
        headers={"Authorization": "Key kid:secret", "Content-Type": "application/json"},
    )
    upload = httpx.Client(transport=httpx.MockTransport(upload_handler or handler))
    return HiggsfieldApi("kid:secret", http_client=http, upload_client=upload)
