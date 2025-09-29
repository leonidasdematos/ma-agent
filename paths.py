"""Filesystem locations used by the MA gateway agent.

This module centralises every path that may vary depending on the
deployment.  The defaults are aligned with the production Raspberry Pi
image but they can be overridden through environment variables which is
particularly handy while running the agent locally during development
or tests.
"""
from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "AGENT_ROOT",
    "LOG_DIR",
    "LOG_FILE",
    "UPDATES_DIR",
    "VERSION_FILE",
]

ENV_PREFIX = "MA_AGENT"


def _env_path(name: str, default: str) -> Path:
    value = os.environ.get(f"{ENV_PREFIX}_{name}")
    return Path(value) if value else Path(default)


AGENT_ROOT: Path = _env_path("ROOT", "/opt/ma-agent")
LOG_DIR: Path = _env_path("LOG_DIR", "/var/log/ma-agent")
LOG_FILE: Path = _env_path("LOG_FILE", str(LOG_DIR / "agent.log"))
UPDATES_DIR: Path = _env_path("UPDATES_DIR", str(AGENT_ROOT / "updates"))
VERSION_FILE: Path = _env_path("VERSION_FILE", str(AGENT_ROOT / "VERSION.txt"))

# Directories used by the agent are created lazily by the bootstrap code.