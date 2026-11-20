from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def get_log_directory() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "StarBinder" / "logs"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "StarBinder"
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "starbinder" / "logs"


def configure_logging(log_directory: Path | None = None) -> Path:
    directory = log_directory or get_log_directory()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            directory / "starbinder.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
    except OSError as exc:
        raise RuntimeError(f"Could not initialize StarBinder logs in '{directory}': {exc}") from exc

    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    handler.setLevel(logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    for existing in root_logger.handlers:
        if isinstance(existing, RotatingFileHandler) and Path(existing.baseFilename) == directory / "starbinder.log":
            root_logger.removeHandler(existing)
            existing.close()
    root_logger.addHandler(handler)

    logger = logging.getLogger("starbinder")
    logger.info("Logging to %s", directory / "starbinder.log")
    return directory
