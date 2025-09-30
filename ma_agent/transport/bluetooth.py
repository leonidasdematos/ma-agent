"""Bluetooth RFCOMM transport implementation."""
from __future__ import annotations

import logging
import threading
from typing import Callable

try:  # pragma: no cover - optional dependency
    from bluetooth import BluetoothError, BluetoothSocket, RFCOMM, advertise_service
    BLUETOOTH_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    BluetoothSocket = None  # type: ignore
    BluetoothError = Exception  # type: ignore
    advertise_service = None  # type: ignore
    RFCOMM = None  # type: ignore
    BLUETOOTH_AVAILABLE = False

from .base import StreamWorker, TransportServer
from ..config import AgentConfig
from ..session import GatewaySession

LOGGER = logging.getLogger(__name__)


class BluetoothServer(TransportServer):
    def __init__(self, config: AgentConfig, session_factory: Callable[[], GatewaySession]) -> None:
        super().__init__("bluetooth")
        self.config = config
        self._session_factory = session_factory
        self._thread: threading.Thread | None = None

    def start(self) -> None:  # pragma: no cover - hardware interaction
        if not BLUETOOTH_AVAILABLE:
            LOGGER.warning("PyBluez not available, bluetooth transport disabled")
            return

        if self._thread and self._thread.is_alive():
            return

        def _run() -> None:
            try:
                with BluetoothSocket(RFCOMM) as server:
                    server.bind(("", self.config.bluetooth_channel))
                    server.listen(1)
                    if advertise_service:
                        try:
                            advertise_service(
                                server,
                                self.config.service_name,
                                service_id="00001101-0000-1000-8000-00805F9B34FB",
                                service_classes=["00001101-0000-1000-8000-00805F9B34FB"],
                                profiles=[("00001101-0000-1000-8000-00805F9B34FB", 1)],
                            )
                            LOGGER.info("Bluetooth RFCOMM service advertised as %s", self.config.service_name)
                        except BluetoothError as exc:
                            LOGGER.warning("failed to advertise bluetooth service: %s", exc)
                    LOGGER.info("Bluetooth listening on RFCOMM channel %s", self.config.bluetooth_channel)
                    while True:
                        client, addr = server.accept()
                        worker = StreamWorker(
                            conn=client,
                            peer=f"bt:{addr}",
                            session_factory=self._session_factory,
                        )
                        worker.start()
            except BluetoothError as exc:
                LOGGER.error("bluetooth server error: %s", exc)

        self._thread = threading.Thread(target=_run, name="bt-server", daemon=True)
        self._thread.start()


__all__ = ["BluetoothServer", "BLUETOOTH_AVAILABLE"]