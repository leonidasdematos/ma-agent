"""Telemetry publisher interfaces used by the gateway session."""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Iterable, Set

try:  # pragma: no cover - typing.Protocol may be unavailable on older Python
    from typing import Protocol
except ImportError:  # pragma: no cover
    try:
        from typing_extensions import Protocol  # type: ignore
    except ImportError:  # pragma: no cover
        class Protocol:  # type: ignore
            """Fallback Protocol base when typing module lacks the feature."""

            pass

from .protocol.messages import Message, MessageType

class TelemetryPublisher(Protocol):
    """Protocol describing the expected telemetry publisher behaviour."""

    def register_session(self, session: Any) -> None:
        """Register a session interested in receiving telemetry updates."""

    def unregister_session(self, session: Any) -> None:
        """Remove a session from the telemetry stream."""


@dataclass
class _TelemetrySample:
    """Simple value object describing a simulated GNSS fix."""

    sequence: int
    latitude: float
    longitude: float
    heading_deg: float
    speed_mps: float
    accuracy_m: float

    def to_message(self) -> Message:
        """Transform the sample into a GNSS fix message."""

        timestamp_ms = int(time.time() * 1000)
        return Message(
            type=MessageType.GNSS_FIX,
            payload={
                "sequence": self.sequence,
                "latitude": self.latitude,
                "longitude": self.longitude,
                "heading_deg": self.heading_deg,
                "speed_mps": self.speed_mps,
                "accuracy_m": self.accuracy_m,
                "timestamp_ms": timestamp_ms,
            },
        )


class SimulatedTelemetryPublisher:
    """Stream simulated GNSS fixes to all subscribed sessions."""

    def __init__(
        self,
        *,
        base_latitude: float = -23.55052,
        base_longitude: float = -46.633308,
        radius_m: float = 15.0,
        sample_rate_hz: float = 1.0,
        speed_mps: float = 3.0,
        accuracy_m: float = 0.5,
    ) -> None:
        self._base_latitude = base_latitude
        self._base_longitude = base_longitude
        self._radius_m = radius_m
        self._sample_rate_hz = sample_rate_hz
        self._speed_mps = speed_mps
        self._accuracy_m = accuracy_m
        self._sessions: Set[Any] = set()
        self._sessions_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._sequence = 0
        self._worker = threading.Thread(
            target=self._run,
            name="simulated-telemetry",
            daemon=True,
        )
        self._worker.start()

    # Public API -----------------------------------------------------
    def register_session(self, session: Any) -> None:
        with self._sessions_lock:
            self._sessions.add(session)

    def unregister_session(self, session: Any) -> None:
        with self._sessions_lock:
            self._sessions.discard(session)

    def stop(self) -> None:
        """Stop the background telemetry generator."""

        self._stop_event.set()
        if self._worker.is_alive():
            self._worker.join(timeout=2.0)

    # Internal helpers -----------------------------------------------
    def _run(self) -> None:
        interval = 1.0 / self._sample_rate_hz if self._sample_rate_hz else 1.0
        while not self._stop_event.is_set():
            sessions = self._snapshot_sessions()
            if not sessions:
                time.sleep(interval)
                continue

            sample = self._next_sample()
            message = sample.to_message()
            for session in sessions:
                if not getattr(session, "telemetry_subscribed", True):
                    continue
                if getattr(session, "awaiting_ack", False):
                    continue
                try:
                    sent = session.send_message(message)
                    if not sent:
                        continue
                except Exception:
                    self.unregister_session(session)
            time.sleep(interval)

    def _snapshot_sessions(self) -> Iterable[Any]:
        with self._sessions_lock:
            return list(self._sessions)

    def _next_sample(self) -> _TelemetrySample:
        self._sequence += 1
        angle = (self._sequence % 360) * math.pi / 180.0
        earth_radius_m = 6_371_000.0
        delta_lat = (self._radius_m / earth_radius_m) * (180.0 / math.pi)
        delta_lon = delta_lat / max(math.cos(math.radians(self._base_latitude)), 1e-6)
        latitude = self._base_latitude + delta_lat * math.sin(angle)
        longitude = self._base_longitude + delta_lon * math.cos(angle)
        heading_deg = (math.degrees(angle) + 360.0) % 360.0

        return _TelemetrySample(
            sequence=self._sequence,
            latitude=latitude,
            longitude=longitude,
            heading_deg=heading_deg,
            speed_mps=self._speed_mps,
            accuracy_m=self._accuracy_m,
        )


__all__ = ["TelemetryPublisher", "SimulatedTelemetryPublisher"]