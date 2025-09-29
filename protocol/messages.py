"""Message models exchanged between the gateway and the monitor."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, Iterator, Optional


class MessageType(str, Enum):
    HELLO = "HELLO"
    HELLO_ACK = "HELLO_ACK"
    ACK = "ACK"
    ERROR = "ERROR"
    PING = "PING"
    PONG = "PONG"
    INFO = "INFO"
    STATUS_REQUEST = "GET_STATUS"
    STATUS_RESPONSE = "STATUS"
    START_JOB = "START_JOB"
    STOP_JOB = "STOP_JOB"
    UPDATE = "UPDATE"
    REBOOT = "REBOOT"


@dataclass(slots=True)
class Message:
    type: MessageType
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type.value, "payload": self.payload}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        try:
            message_type = MessageType(data.get("type"))
        except Exception as exc:
            raise ValueError(f"unknown message type: {data!r}") from exc
        payload = data.get("payload") or {}
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        return cls(type=message_type, payload=payload)


def error_message(reason: str, *, code: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> Message:
    payload: Dict[str, Any] = {"reason": reason}
    if code:
        payload["code"] = code
    if details:
        payload["details"] = details
    return Message(type=MessageType.ERROR, payload=payload)


def hello_ack(*, version: str, capabilities: Iterable[str]) -> Message:
    return Message(
        type=MessageType.HELLO_ACK,
        payload={"version": version, "capabilities": list(capabilities)},
    )


def info_message(version: str, uptime_s: int) -> Message:
    return Message(
        type=MessageType.INFO,
        payload={"version": version, "uptime_s": uptime_s},
    )


__all__ = [
    "Message",
    "MessageType",
    "error_message",
    "hello_ack",
    "info_message",
]