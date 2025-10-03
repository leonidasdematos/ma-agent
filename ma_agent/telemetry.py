"""Telemetry publisher interfaces used by the gateway session."""
from __future__ import annotations

from typing import Protocol, Any


class TelemetryPublisher(Protocol):
    """Protocol describing the expected telemetry publisher behaviour.

    The concrete implementation is responsible for streaming telemetry
    samples (GNSS fixes, implement data, etc.) to the registered
    :class:`~ma_agent.session.GatewaySession` objects. The session keeps a
    per-connection state (subscriptions, acknowledgements) that the
    publisher can query in order to apply back-pressure or retry logic.
    """

    def register_session(self, session: Any) -> None:
        """Register a session interested in receiving telemetry updates."""

    def unregister_session(self, session: Any) -> None:
        """Remove a session from the telemetry stream."""


__all__ = ["TelemetryPublisher"]