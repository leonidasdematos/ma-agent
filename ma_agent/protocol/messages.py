"""Message models exchanged between the gateway and the monitor."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import sys
from typing import Any, Dict, Iterable, Optional

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
    GNSS_FIX = "GNSS_FIX"  # latitude, longitude, altitude, accuracy, sequence, timestamp, rtk_state
    GNSS_ACK = "GNSS_ACK"  # sequence, status, timestamp
    NTRIP_CORRECTION = "NTRIP_CORRECTION"  # sequence, format, payload, timestamp
    NTRIP_CORRECTION_ACK = "NTRIP_CORRECTION_ACK"  # sequence, status, timestamp


# ``slots`` support for ``dataclasses`` arrived in Python 3.10. Prefer slots
# when available but remain compatible with Python 3.9.
_DATACLASS_KWARGS = {"slots": True} if sys.version_info >= (3, 10) else {}


@dataclass(**_DATACLASS_KWARGS)
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


def info_message(
    version: str,
    uptime_s: int,
    *,
    implement: Optional[Dict[str, Any]] = None,
) -> Message:
    payload: Dict[str, Any] = {"version": version, "uptime_s": uptime_s}
    if implement:
        payload["implement"] = implement
    return Message(type=MessageType.INFO, payload=payload)


def gnss_fix_message(
    *,
    latitude: float,
    longitude: float,
    altitude: float,
    accuracy: Optional[float] = None,
    sequence: Optional[int] = None,
    timestamp: Optional[float] = None,
    rtk_state: Optional[str] = None,
) -> Message:
    """Build a :class:`MessageType.GNSS_FIX` message.

    The payload follows the convention agreed with the mobile client and
    transports a GNSS fix sample:

    * ``latitude`` (float): decimal degrees using WGS84.
    * ``longitude`` (float): decimal degrees using WGS84.
    * ``altitude`` (float): altitude in meters above sea level.
    * ``accuracy`` (float, optional): estimated horizontal accuracy in meters.
    * ``sequence`` (int, optional): monotonic sequence number for ordering.
    * ``timestamp`` (float, optional): POSIX timestamp (seconds).
    * ``rtk_state`` (str, optional): textual RTK fix state (ex.: ``FLOAT``).
    """

    payload: Dict[str, Any] = {
        "latitude": latitude,
        "longitude": longitude,
        "altitude": altitude,
    }
    if accuracy is not None:
        payload["accuracy"] = accuracy
    if sequence is not None:
        payload["sequence"] = sequence
    if timestamp is not None:
        payload["timestamp"] = timestamp
    if rtk_state is not None:
        payload["rtk_state"] = rtk_state
    return Message(type=MessageType.GNSS_FIX, payload=payload)


def gnss_ack_message(
    *, sequence: int, status: str, timestamp: Optional[float] = None
) -> Message:
    """Build a :class:`MessageType.GNSS_ACK` message acknowledging a GNSS fix."""

    payload: Dict[str, Any] = {"sequence": sequence, "status": status}
    if timestamp is not None:
        payload["timestamp"] = timestamp
    return Message(type=MessageType.GNSS_ACK, payload=payload)


def ntrip_correction_message(
    *,
    sequence: int,
    payload: str,
    format: str,
    timestamp: Optional[float] = None,
) -> Message:
    """Build a :class:`MessageType.NTRIP_CORRECTION` message.

    The payload contains the following fields:

    * ``sequence`` (int): sequence number matching the related GNSS fix.
    * ``format`` (str): payload encoding (ex.: ``RTCM3``).
    * ``payload`` (str): correction data (typically base64 encoded RTCM bytes).
    * ``timestamp`` (float, optional): POSIX timestamp (seconds).
    """

    message_payload: Dict[str, Any] = {
        "sequence": sequence,
        "payload": payload,
        "format": format,
    }
    if timestamp is not None:
        message_payload["timestamp"] = timestamp
    return Message(type=MessageType.NTRIP_CORRECTION, payload=message_payload)


def ntrip_correction_ack_message(
    *, sequence: int, status: str, timestamp: Optional[float] = None
) -> Message:
    """Build a :class:`MessageType.NTRIP_CORRECTION_ACK` message."""

    payload: Dict[str, Any] = {"sequence": sequence, "status": status}
    if timestamp is not None:
        payload["timestamp"] = timestamp
    return Message(type=MessageType.NTRIP_CORRECTION_ACK, payload=payload)



__all__ = [
    "Message",
    "MessageType",
    "error_message",
    "hello_ack",
    "info_message",
    "gnss_fix_message",
    "gnss_ack_message",
    "ntrip_correction_message",
    "ntrip_correction_ack_message",
]