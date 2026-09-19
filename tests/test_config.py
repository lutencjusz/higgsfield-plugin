import json

from higgsfield_cli import cli, config


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_home_config_is_default(tmp_path):
    write(config.CONFIG_DIR / "config.json", {"api_key_id": "h", "api_key_secret": "s"})
    assert config.config_dir() == config.CONFIG_DIR
    assert config.load_credentials() == "h:s"


def test_project_config_wins_and_is_found_from_subfolder(tmp_path, monkeypatch):
    write(config.CONFIG_DIR / "config.json", {"api_key_id": "home", "api_key_secret": "s"})
    project = tmp_path / "proj"
    write(project / ".higgsfield" / "config.json",
          {"api_key_id": "proj", "api_key_secret": "s", "output_dir": "output"})
    (project / "input").mkdir()
    monkeypatch.chdir(project / "input")
    assert config.load_credentials() == "proj:s"
    assert config.jobs_file() == project / ".higgsfield" / "jobs.json"
    assert config.output_dir() == project / "output"  # względem projektu, nie cwd


def test_env_overrides(tmp_path, monkeypatch):
    write(tmp_path / "cfg" / "config.json", {"api_key_id": "c", "api_key_secret": "s"})
    monkeypatch.setenv(config.ENV_CONFIG_DIR, str(tmp_path / "cfg"))
    assert config.load_credentials() == "c:s"
    monkeypatch.setenv(config.ENV_KEY_ID, "e")
    monkeypatch.setenv(config.ENV_KEY_SECRET, "x")
    assert config.load_credentials() == "e:x"


def test_setup_local_writes_project_config(tmp_path, monkeypatch):
    monkeypatch.setenv(config.ENV_KEY_ID, "id1")
    monkeypatch.setenv(config.ENV_KEY_SECRET, "sec1")
    assert cli.main(["setup", "--local", "--output-dir", "output"]) == 0
    data = json.loads((tmp_path / ".higgsfield" / "config.json").read_text(encoding="utf-8"))
    assert data == {"api_key_id": "id1", "api_key_secret": "sec1", "output_dir": "output"}
    assert not (config.CONFIG_DIR / "config.json").exists()


def test_walk_stops_at_home(tmp_path, monkeypatch):
    # ~/.higgsfield nie może być brany za config projektu przy pracy w podfolderze domu
    home = tmp_path / "home"
    write(home / ".higgsfield" / "config.json", {"api_key_id": "h", "api_key_secret": "s"})
    (home / "work").mkdir()
    monkeypatch.chdir(home / "work")
    assert config.config_dir() == config.CONFIG_DIR
    monkeypatch.chdir(tmp_path)  # powyżej domu też nie szukamy
    assert config.config_dir() == config.CONFIG_DIR
