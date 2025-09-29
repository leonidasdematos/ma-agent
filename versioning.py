"""Utilities for dealing with the agent version."""
from __future__ import annotations

from pathlib import Path

from .paths import VERSION_FILE


def read_version(version_file: Path | None = None) -> str:
    target = version_file or VERSION_FILE
    try:
        return target.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "0.0.1-dev"


__all__ = ["read_version"]