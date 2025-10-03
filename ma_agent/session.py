"""Session handling and business logic for monitor communication."""
from __future__ import annotations

import base64
import logging
import subprocess
import time
import zipfile
from typing import Callable, Iterable, List, Optional

from .implement import ImplementProfile
from .paths import AGENT_ROOT, UPDATES_DIR
from .protocol.messages import (
    Message,
    MessageType,
    error_message,
    hello_ack,
    info_message,
    ntrip_correction_ack_message,
)
from .state import AgentState, STATE, VERSION
from .telemetry import TelemetryPublisher
from .gnss import GnssCoordinator

LOGGER = logging.getLogger(__name__)


class HandshakeError(Exception):
    """Raised when the monitor fails to perform the mandatory handshake."""


class GatewaySession:
    """Encapsulates one logical conversation with the monitor."""

    CAPABILITIES: Iterable[str] = (
        "telemetry/basic",
        "telemetry/rtk",
        "corrections/ntrip",
        "implement/management",
        "implement/profile",
        "update/zip",
    )

    def __init__(
        self,
        *,
        state: AgentState | None = None,
        implement_profile: ImplementProfile | None = None,
        telemetry_publisher: TelemetryPublisher | None = None,
        gnss_coordinator: GnssCoordinator | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.state = state or STATE
        self.handshake_complete = False
        self.implement_profile = implement_profile
        self.telemetry_publisher = telemetry_publisher
        self.gnss_coordinator = gnss_coordinator
        self._clock: Callable[[], float] = clock or time.monotonic
        self._telemetry_subscribed = False
        self._registered_with_publisher = False
        self._last_ack_sequence: Optional[int] = None
        self._last_ack_status: Optional[str] = None
        self._last_ack_timestamp: Optional[float] = None
        self._last_heartbeat_at: Optional[float] = None
        self._pending_fix_sequence: Optional[int] = None
        self._message_sender: Optional[Callable[[Message], None]] = None


    # Public API ---------------------------------------------------------
    def handle_message(self, message: Message) -> List[Message]:
        LOGGER.debug("processing message %s", message)
        if not self.handshake_complete and message.type is not MessageType.HELLO:
            LOGGER.warning("received %s before HELLO handshake", message.type)
            return [
                error_message(
                    "handshake required",
                    code="handshake_required",
                )
            ]

        handlers = {
            MessageType.HELLO: self._on_hello,
            MessageType.PING: self._on_ping,
            MessageType.INFO: self._on_info_request,
            MessageType.STATUS_REQUEST: self._on_status_request,
            MessageType.START_JOB: self._on_start_job,
            MessageType.STOP_JOB: self._on_stop_job,
            MessageType.UPDATE: self._on_update,
            MessageType.REBOOT: self._on_reboot,
            MessageType.GNSS_ACK: self._on_gnss_ack,
            MessageType.NTRIP_CORRECTION: self._on_ntrip_correction,
        }

        handler = handlers.get(message.type)
        if handler is None:
            LOGGER.info("no handler for message %s", message.type)
            return [
                error_message(
                    f"unsupported message: {message.type.value}",
                    code="unsupported",
                )
            ]

        return handler(message)

    # Lifecycle management -----------------------------------------------
    def close(self) -> None:
        """Clean-up resources tied to the session lifecycle."""

        if self.telemetry_publisher and self._registered_with_publisher:
            try:
                self.telemetry_publisher.unregister_session(self)
            finally:
                self._registered_with_publisher = False
        self._message_sender = None
        if self.gnss_coordinator:
            unregister = getattr(self.gnss_coordinator, "unregister_session", None)
            if unregister:
                unregister(self)


    # Message handlers ---------------------------------------------------
    def _on_hello(self, message: Message) -> List[Message]:
        self.handshake_complete = True
        self._telemetry_subscribed = self._extract_subscription(message.payload)
        LOGGER.info("handshake completed (telemetry subscribed=%s)", self._telemetry_subscribed)
        if self.telemetry_publisher and not self._registered_with_publisher:
            self.telemetry_publisher.register_session(self)
            self._registered_with_publisher = True
        if self.gnss_coordinator:
            register = getattr(self.gnss_coordinator, "register_session", None)
            if register:
                register(self)
        return [hello_ack(version=VERSION, capabilities=self.CAPABILITIES)]

    def _extract_subscription(self, payload: dict | None) -> bool:
        """Determine if the monitor requested telemetry streaming."""

        if not payload:
            return True
        subscribe = payload.get("subscribe") or payload.get("subscriptions")
        if subscribe is None:
            return True
        if isinstance(subscribe, bool):
            return subscribe
        if isinstance(subscribe, list):
            return "telemetry/rtk" in subscribe or "telemetry" in subscribe
        if isinstance(subscribe, dict):
            if "telemetry/rtk" in subscribe:
                return bool(subscribe["telemetry/rtk"])
            telemetry_node = subscribe.get("telemetry")
            if isinstance(telemetry_node, dict) and "rtk" in telemetry_node:
                return bool(telemetry_node["rtk"])
        return True


    def _on_ping(self, _: Message) -> List[Message]:
        return [Message(type=MessageType.PONG)]

    def _on_info_request(self, _: Message) -> List[Message]:
        snapshot = self.state.snapshot()
        implement_payload = (
            self.implement_profile.to_payload() if self.implement_profile else None
        )
        return [
            info_message(
                version=VERSION,
                uptime_s=snapshot["uptime_s"],
                implement=implement_payload,
            )
        ]

    def _on_status_request(self, _: Message) -> List[Message]:
        snapshot = self.state.snapshot()
        return [
            Message(
                type=MessageType.STATUS_RESPONSE,
                payload={"job_running": snapshot["job_running"]},
            )
        ]

    def _on_start_job(self, message: Message) -> List[Message]:
        self.state.set_job_running(True)
        self.state.mark_command(message.to_dict())
        return [
            Message(
                type=MessageType.ACK,
                payload={"action": MessageType.START_JOB.value},
            )
        ]

    def _on_stop_job(self, message: Message) -> List[Message]:
        self.state.set_job_running(False)
        self.state.mark_command(message.to_dict())
        return [
            Message(
                type=MessageType.ACK,
                payload={"action": MessageType.STOP_JOB.value},
            )
        ]

    def _on_update(self, message: Message) -> List[Message]:
        payload = message.payload
        name = payload.get("name")
        content_b64 = payload.get("content_b64")
        if not name or not content_b64:
            return [error_message("missing name/content")]

        UPDATES_DIR.mkdir(parents=True, exist_ok=True)
        target = UPDATES_DIR / name
        try:
            data = base64.b64decode(content_b64)
        except Exception:
            return [error_message("invalid base64", code="invalid_payload")]

        target.write_bytes(data)
        LOGGER.info("update package written to %s", target)

        try:
            with zipfile.ZipFile(target, "r") as zf:
                zf.extractall(AGENT_ROOT)
            LOGGER.info("update extracted to %s", AGENT_ROOT)
        except zipfile.BadZipFile:
            return [error_message("invalid zip", code="invalid_package")]

        # In production we restart the service but the skeleton keeps it optional.
        subprocess.Popen(["sudo", "systemctl", "restart", "ma-agent"], close_fds=True)
        return [
            Message(
                type=MessageType.ACK,
                payload={"action": MessageType.UPDATE.value},
            )
        ]

    def _on_reboot(self, _: Message) -> List[Message]:
        subprocess.Popen(["sudo", "reboot"], close_fds=True)
        return [
            Message(
                type=MessageType.ACK,
                payload={"action": MessageType.REBOOT.value},
            )
        ]

    def _on_gnss_ack(self, message: Message) -> List[Message]:
        payload = message.payload or {}
        sequence = payload.get("sequence")
        status = payload.get("status")
        timestamp = payload.get("timestamp")
        if sequence is None:
            LOGGER.warning("received GNSS_ACK without sequence: %s", payload)
            return []
        try:
            sequence_int = int(sequence)
        except (TypeError, ValueError):
            LOGGER.warning("invalid GNSS_ACK sequence %r", sequence)
            return []
        self._last_ack_sequence = sequence_int
        self._last_ack_status = status
        self._last_ack_timestamp = timestamp if isinstance(timestamp, (int, float)) else None
        self._last_heartbeat_at = self._clock()
        if self._pending_fix_sequence == sequence_int:
            self._pending_fix_sequence = None
        if self.gnss_coordinator:
            acknowledge = getattr(self.gnss_coordinator, "acknowledge_fix", None)
            if acknowledge:
                acknowledge(sequence=sequence_int, status=status or "", timestamp=self._last_ack_timestamp)
        return []

    def _on_ntrip_correction(self, message: Message) -> List[Message]:
        payload = message.payload or {}
        sequence = payload.get("sequence")
        encoded = payload.get("payload")
        format_ = payload.get("format")
        timestamp = payload.get("timestamp")
        if sequence is None or encoded is None or format_ is None:
            return [
                error_message(
                    "missing sequence/format/payload",
                    code="invalid_payload",
                )
            ]
        try:
            sequence_int = int(sequence)
        except (TypeError, ValueError):
            return [error_message("invalid sequence", code="invalid_payload")]
        try:
            correction_bytes = base64.b64decode(encoded, validate=True)
        except Exception:
            return [error_message("invalid correction payload", code="invalid_payload")]
        if self.gnss_coordinator:
            self.gnss_coordinator.handle_correction(
                sequence=sequence_int,
                payload=correction_bytes,
                format=str(format_),
                timestamp=timestamp if isinstance(timestamp, (int, float)) else None,
            )
        return [
            ntrip_correction_ack_message(
                sequence=sequence_int,
                status="accepted",
                timestamp=timestamp if isinstance(timestamp, (int, float)) else None,
            )
        ]

    # Session state helpers ---------------------------------------------
    @property
    def telemetry_subscribed(self) -> bool:
        return self._telemetry_subscribed

    @property
    def last_ack_sequence(self) -> Optional[int]:
        return self._last_ack_sequence

    @property
    def last_ack_status(self) -> Optional[str]:
        return self._last_ack_status

    @property
    def last_ack_timestamp(self) -> Optional[float]:
        return self._last_ack_timestamp

    @property
    def last_heartbeat_at(self) -> Optional[float]:
        return self._last_heartbeat_at

    @property
    def awaiting_ack(self) -> bool:
        return self._pending_fix_sequence is not None

    def mark_fix_sent(self, sequence: int) -> None:
        """Record that a GNSS fix with ``sequence`` was delivered to the monitor."""

        self._pending_fix_sequence = int(sequence)
        self._last_heartbeat_at = self._clock()

    # Transport interaction -------------------------------------------------
    def attach_sender(self, sender: Callable[[Message], None]) -> None:
        """Allow the session to push messages asynchronously to the monitor."""

        self._message_sender = sender

    def detach_sender(self) -> None:
        self._message_sender = None

    def can_stream(self) -> bool:
        return (
            self.handshake_complete
            and self.telemetry_subscribed
            and self._message_sender is not None
        )

    def send_message(self, message: Message) -> bool:
        """Push ``message`` to the monitor if the transport is ready."""

        if not self.handshake_complete:
            LOGGER.debug("ignoring outbound %s before handshake", message.type)
            return False
        if not self.telemetry_subscribed:
            LOGGER.debug(
                "ignoring outbound %s because telemetry is not subscribed",
                message.type,
            )
            return False
        if not self._message_sender:
            LOGGER.debug("no sender available; dropping %s", message.type)
            return False
        try:
            self._message_sender(message)
        except Exception:  # pragma: no cover - defensive logging
            LOGGER.exception("failed to send %s to monitor", message.type)
            return False
        if message.type is MessageType.GNSS_FIX:
            sequence = message.payload.get("sequence") if message.payload else None
            if sequence is not None:
                try:
                    self.mark_fix_sent(int(sequence))
                except (TypeError, ValueError):
                    LOGGER.debug("unable to mark fix sent for sequence %r", sequence)
        return True

__all__ = ["GatewaySession", "HandshakeError"]