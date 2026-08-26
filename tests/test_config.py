from pinax.config.models import Settings
from pinax.config.settings import load_settings, save_settings


def test_defaults_match_brief():
    settings = Settings()
    assert settings.reader.width == 86
    assert settings.reader.theme == "midnight"
    assert settings.ai.enabled is False
    assert settings.retrieval.top_k == 6


def test_save_and_load_round_trip(monkeypatch, tmp_path):
    monkeypatch.setattr("pinax.config.settings.config_dir", lambda: tmp_path)

    settings = Settings()
    settings.reader.theme = "nord"
    settings.reader.width = 72
    save_settings(settings)

    loaded = load_settings()
    assert loaded.reader.theme == "nord"
    assert loaded.reader.width == 72


def test_load_settings_creates_default_file_on_first_run(monkeypatch, tmp_path):
    monkeypatch.setattr("pinax.config.settings.config_dir", lambda: tmp_path)
    path = tmp_path / "config.toml"
    assert not path.exists()

    load_settings()
    assert path.exists()
