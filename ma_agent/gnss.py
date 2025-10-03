"""GNSS coordination interfaces used by the gateway session."""
from __future__ import annotations

from typing import Protocol, Any


class GnssCoordinator(Protocol):
    """Protocol describing how GNSS integrations interact with sessions."""

    def register_session(self, session: Any) -> None:  # pragma: no cover - optional
        """Register a session interested in GNSS fixes."""

    def unregister_session(self, session: Any) -> None:  # pragma: no cover - optional
        """Remove a session from GNSS notifications."""

    def handle_correction(
        self,
        *,
        sequence: int,
        payload: bytes,
        format: str,
        timestamp: float | None = None,
    ) -> None:
        """Forward RTCM/NTRIP corrections to the GNSS hardware."""

    def acknowledge_fix(
        self,
        *,
        sequence: int,
        status: str,
        timestamp: float | None = None,
    ) -> None:  # pragma: no cover - optional
        """Notify the GNSS coordinator that a fix was acknowledged by the monitor."""


__all__ = ["GnssCoordinator"]