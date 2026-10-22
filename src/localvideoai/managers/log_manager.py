from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from localvideoai import APP_NAME
from localvideoai.core.exceptions import PathError
from localvideoai.core.paths import ensure_directory, logs_dir

_LOGGER_NAME = "localvideoai"
_configured = False


class LogManager:
    """Process-wide rotating file + stderr logging. Failures are raised, not hidden."""

    def __init__(
        self,
        *,
        log_dir: Path | None = None,
        level: str = "INFO",
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
    ) -> None:
        self.log_dir = log_dir or logs_dir()
        self.level = level
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.log_file = self.log_dir / "localvideoai.log"

    def configure(self) -> logging.Logger:
        global _configured
        try:
            ensure_directory(self.log_dir)
        except PathError:
            raise
        logger = logging.getLogger(_LOGGER_NAME)
        logger.setLevel(getattr(logging, self.level.upper(), logging.INFO))
        logger.propagate = False
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler = RotatingFileHandler(
            self.log_file,
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)
        _configured = True
        logger.debug("Logging configured at %s", self.log_file)
        return logger

    @staticmethod
    def get_logger(name: str | None = None) -> logging.Logger:
        if name:
            return logging.getLogger(f"{_LOGGER_NAME}.{name}")
        return logging.getLogger(_LOGGER_NAME)


def get_logger(name: str | None = None) -> logging.Logger:
    return LogManager.get_logger(name)
