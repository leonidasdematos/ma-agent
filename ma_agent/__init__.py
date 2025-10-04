"""MA gateway agent package."""
from __future__ import annotations

from typing import Any, Iterable

__all__ = ["AgentConfig", "GatewayService", "read_version"]


def __getattr__(name: str) -> Any:  # pragma: no cover - simple import proxy
    if name == "AgentConfig":
        from .config import AgentConfig  # local import for lazy loading

        return AgentConfig
    if name == "GatewayService":
        from .gateway import GatewayService  # local import for lazy loading

        return GatewayService
    if name == "read_version":
        from .versioning import read_version  # local import for lazy loading

        return read_version
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> Iterable[str]:  # pragma: no cover - introspection helper
    return sorted(set(globals()) | set(__all__))