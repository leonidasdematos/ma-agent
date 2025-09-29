"""Session handling and business logic for monitor communication."""
from __future__ import annotations

import base64
import logging
import subprocess
import zipfile
from pathlib import Path
from typing import Iterable, List

from .paths import AGENT_ROOT, UPDATES_DIR
from .protocol.messages import (
    Message,
    MessageType,
    error_message,
    hello_ack,
    info_message,
)
from .state import AgentState, STATE, VERSION

LOGGER = logging.getLogger(__name__)


class HandshakeError(Exception):
    """Raised when the monitor fails to perform the mandatory handshake."""


class GatewaySession:
    """Encapsulates one logical conversation with the monitor."""

    CAPABILITIES: Iterable[str] = (
        "telemetry/basic",
        "implement/management",
        "update/zip",
    )

    def __init__(self, *, state: AgentState | None = None) -> None:
        self.state = state or STATE
        self.handshake_complete = False

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

    # Message handlers ---------------------------------------------------
    def _on_hello(self, _: Message) -> List[Message]:
        self.handshake_complete = True
        LOGGER.info("handshake completed")
        return [hello_ack(version=VERSION, capabilities=self.CAPABILITIES)]

    def _on_ping(self, _: Message) -> List[Message]:
        return [Message(type=MessageType.PONG)]

    def _on_info_request(self, _: Message) -> List[Message]:
        snapshot = self.state.snapshot()
        return [info_message(version=VERSION, uptime_s=snapshot["uptime_s"])]

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


__all__ = ["GatewaySession", "HandshakeError"]