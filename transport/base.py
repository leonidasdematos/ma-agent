"""Transport abstractions used by the gateway."""
from __future__ import annotations

import logging
import socket
import threading
from typing import Callable

from ..protocol.codec import LineCodec
from ..protocol.messages import Message, error_message
from ..session import GatewaySession

LOGGER = logging.getLogger(__name__)


class TransportServer:
    """Base class for concrete transports (TCP, Bluetooth, ...)."""

    def __init__(self, name: str) -> None:
        self.name = name

    def start(self) -> None:
        raise NotImplementedError


class StreamWorker(threading.Thread):
    """Thread that handles a single duplex byte stream."""

    daemon = True

    def __init__(self, *, conn: socket.socket, peer: str, session_factory: Callable[[], GatewaySession]) -> None:
        super().__init__(name=f"{peer}-worker")
        self.conn = conn
        self.peer = peer
        self.session_factory = session_factory

    def run(self) -> None:  # pragma: no cover - network IO
        LOGGER.info("connection opened from %s", self.peer)
        session = self.session_factory()
        try:
            buffer = b""
            while True:
                chunk = self.conn.recv(4096)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line:
                        continue
                    try:
                        message = LineCodec.decode(line)
                    except Exception as exc:
                        LOGGER.warning("failed to decode message from %s: %s", self.peer, exc)
                        self.conn.sendall(
                            LineCodec.encode(
                                error_message(
                                    "invalid message format",
                                    code="bad_json",
                                    details={"error": str(exc)},
                                )
                            )
                        )
                        continue
                    for response in session.handle_message(message):
                        self.conn.sendall(LineCodec.encode(response))
        finally:
            try:
                self.conn.close()
            finally:
                LOGGER.info("connection closed from %s", self.peer)


__all__ = ["TransportServer", "StreamWorker"]