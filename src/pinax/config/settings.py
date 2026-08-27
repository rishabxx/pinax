"""Config/data/cache paths (platform-correct via `platformdirs`) and TOML load/save.

Uses stdlib `tomllib` to read. Writing uses a small hand-rolled serializer since our schema
is flat sections of scalars only — not worth a TOML-writer dependency for that.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from platformdirs import PlatformDirs

from .models import Settings

_DIRS = PlatformDirs(appname="pinax", appauthor=False)


def config_dir() -> Path:
    return Path(_DIRS.user_config_dir)


def data_dir() -> Path:
    return Path(_DIRS.user_data_dir)


def cache_dir() -> Path:
    return Path(_DIRS.user_cache_dir)


def config_path() -> Path:
    return config_dir() / "config.toml"


def database_path() -> Path:
    return data_dir() / "pinax.db"


def _to_toml(settings: Settings) -> str:
    lines: list[str] = []
    for section_name, section in settings.model_dump().items():
        lines.append(f"[{section_name}]")
        for key, value in section.items():
            # TOML has no null literal — omit the key entirely so the pydantic default
            # (None) applies again on the next load, rather than round-tripping as the
            # literal string "None".
            if value is None:
                continue
            lines.append(f"{key} = {_toml_value(value)}")
        lines.append("")
    return "\n".join(lines)


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return '"' + str(value).replace('"', '\\"') + '"'


def load_settings() -> Settings:
    path = config_path()
    if not path.exists():
        settings = Settings()
        save_settings(settings)
        return settings

    with open(path, "rb") as f:
        raw = tomllib.load(f)
    return Settings.model_validate(raw)


def save_settings(settings: Settings) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_to_toml(settings))


__all__ = ["Settings", "config_dir", "data_dir", "cache_dir", "config_path", "database_path", "load_settings", "save_settings"]
