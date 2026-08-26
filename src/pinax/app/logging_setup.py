"""File logging (brief §64: "Write logs to a predictable location").

Wired up once at CLI startup. The TUI itself must never print to stdout/stderr — Textual
owns the terminal — so anything worth diagnosing (a page that failed to render, an image
that couldn't be decoded) goes here instead of being silently swallowed.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..config.settings import data_dir

LOGGER_NAME = "pinax"


def log_path() -> Path:
    return data_dir() / "pinax.log"


def configure_logging() -> Path:
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        handler = logging.FileHandler(path)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False

    return path


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


__all__ = ["configure_logging", "get_logger", "log_path"]
