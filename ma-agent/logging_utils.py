"""Logging helpers for the MA gateway agent."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterable

from paths import LOG_DIR, LOG_FILE

DEFAULT_LOG_LEVEL = logging.INFO


def setup_logging(extra_handlers: Iterable[logging.Handler] | None = None) -> None:
    """Configure the root logger used by the agent.

    The logger streams human-readable lines to stdout (useful during
    development) and also writes to a rotating file under
    ``/var/log/ma-agent`` by default.  Consumers can supply additional
    handlers when embedding the service in a different runtime.
    """

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    if root.handlers:
        # Assume logging is already configured.
        return

    root.setLevel(DEFAULT_LOG_LEVEL)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    if extra_handlers:
        for handler in extra_handlers:
            root.addHandler(handler)


__all__ = ["setup_logging", "DEFAULT_LOG_LEVEL"]