"""TCP transport implementation."""
from __future__ import annotations

import logging
import socket
import threading

from .base import StreamWorker, TransportServer
from ..config import AgentConfig
from ..session import GatewaySession

LOGGER = logging.getLogger(__name__)


class TcpServer(TransportServer):
    def __init__(self, config: AgentConfig, session_factory):
        super().__init__("tcp")
        self.config = config
        self._session_factory = session_factory
        self._thread: threading.Thread | None = None

    def start(self) -> None:  # pragma: no cover - network IO
        if self._thread and self._thread.is_alive():
            return

        def _run() -> None:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.bind((self.config.tcp_host, self.config.tcp_port))
                server.listen(5)
                LOGGER.info("TCP listening on %s:%s", self.config.tcp_host, self.config.tcp_port)
                while True:
                    conn, addr = server.accept()
                    worker = StreamWorker(
                        conn=conn,
                        peer=f"tcp:{addr[0]}:{addr[1]}",
                        session_factory=self._session_factory,
                    )
                    worker.start()

        self._thread = threading.Thread(target=_run, name="tcp-server", daemon=True)
        self._thread.start()


__all__ = ["TcpServer"]