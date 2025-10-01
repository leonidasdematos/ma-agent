"""Bluetooth RFCOMM transport implementation."""
from __future__ import annotations

import logging
import socket
import threading
from typing import Callable

try:  # pragma: no cover - optional dependency
    from bluetooth import (
        BluetoothSocket,
        PORT_ANY,
        RFCOMM,
        SERIAL_PORT_CLASS,
        SERIAL_PORT_PROFILE,
        advertise_service,
        btcommon,
    )
    BluetoothError = btcommon.BluetoothError
    BLUETOOTH_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    BluetoothSocket = None  # type: ignore[assignment]
    PORT_ANY = None  # type: ignore[assignment]
    RFCOMM = None  # type: ignore[assignment]
    SERIAL_PORT_CLASS = None  # type: ignore[assignment]
    SERIAL_PORT_PROFILE = None  # type: ignore[assignment]
    advertise_service = None  # type: ignore[assignment]
    btcommon = None  # type: ignore[assignment]
    BluetoothError = Exception  # type: ignore[assignment]
    BLUETOOTH_AVAILABLE = False

from .base import StreamWorker, TransportServer
from ..config import AgentConfig
from ..session import GatewaySession

LOGGER = logging.getLogger("ma_agent.transport.bluetooth")


class BluetoothServer(TransportServer):
    def __init__(self, config: AgentConfig, session_factory: Callable[[], GatewaySession]) -> None:
        super().__init__("bluetooth")
        self.config = config
        self._session_factory = session_factory
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._server_socket: BluetoothSocket | None = None


    def start(self) -> None:  # pragma: no cover - hardware interaction
        if not BLUETOOTH_AVAILABLE:
            LOGGER.warning("PyBluez not available, bluetooth transport disabled")
            return

        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        thread = threading.Thread(target=self._run, name="bt-server", daemon=True)
        self._thread = thread
        thread.start()

        def stop(self) -> None:  # pragma: no cover - hardware interaction
            self._stop_event.set()
            if self._server_socket is not None:
                try:
                    self._server_socket.close()
                except Exception:
                    pass
                if self._thread and self._thread.is_alive():
                    self._thread.join(timeout=5.0)
                self._thread = None

                def _run(self) -> None:  # pragma: no cover - hardware interaction
                    try:
                        server = BluetoothSocket(RFCOMM)
                    except Exception as exc:
                        LOGGER.error("failed to create BluetoothSocket: %s", exc)
                        return

                    self._server_socket = server
                    try:
                        channel = getattr(self.config, "bluetooth_channel", None)
                        bind_channel = channel if channel is not None else PORT_ANY
                        server.bind(("", bind_channel))
                        server.listen(1)
                        server.settimeout(1.0)
                        port = server.getsockname()[1]
                        LOGGER.info("RFCOMM listening on channel %s", port)

                        service_uuid = getattr(self.config, "service_uuid", None) or SERIAL_PORT_CLASS

                        if advertise_service and SERIAL_PORT_CLASS and SERIAL_PORT_PROFILE:
                            try:
                                advertise_service(
                                    server,
                                    getattr(self.config, "service_name", "MAGateway"),
                                    service_id=service_uuid,
                                    service_classes=[service_uuid, SERIAL_PORT_CLASS],
                                    profiles=[SERIAL_PORT_PROFILE],
                                )
                                LOGGER.info("SDP service advertised")
                            except Exception as exc:  # pragma: no cover - optional dependency
                                LOGGER.warning("SDP advertise failed: %s", exc)

                        while not self._stop_event.is_set():
                            try:
                                client_sock, client_info = server.accept()
                            except socket.timeout:
                                continue
                            except BluetoothError as exc:
                                if self._stop_event.is_set():
                                    break
                                if "timed out" in str(exc).lower():
                                    continue
                                LOGGER.warning("Bluetooth accept failed: %s", exc)
                                continue
                            except OSError as exc:
                                if self._stop_event.is_set():
                                    break
                                LOGGER.warning("Bluetooth accept failed: %s", exc)
                                continue

                            LOGGER.info("accepted bluetooth connection from %s", client_info)
                            client_thread = threading.Thread(
                                target=self._handle_client,
                                args=(client_sock, client_info),
                                name=self._client_thread_name(client_info),
                                daemon=True,
                            )
                            client_thread.start()
                    except BluetoothError as exc:
                        if not self._stop_event.is_set():
                            LOGGER.error("bluetooth server error: %s", exc)
                    except Exception as exc:  # pragma: no cover - defensive
                        LOGGER.exception("unexpected bluetooth server error: %s", exc)
                    finally:
                        try:
                            server.close()
                        except Exception:
                            pass
                        self._server_socket = None
                        LOGGER.info("Bluetooth RFCOMM server stopped")

        def _handle_client(self, client_sock, client_info) -> None:  # pragma: no cover - hardware interaction
            peer = self._format_peer(client_info)
            try:
                worker = StreamWorker(
                    conn=client_sock,
                    peer=peer,
                    session_factory=self._session_factory,
                )
                worker.run()
            except Exception as exc:
                LOGGER.warning("bluetooth client handler error for %s: %s", peer, exc)
            finally:
                try:
                    client_sock.close()
                except Exception:
                    pass

        def _client_thread_name(self, client_info) -> str:
            peer = self._format_peer(client_info)
            return f"bt-client-{peer.split(':', 1)[-1]}"

        @staticmethod
        def _format_peer(client_info) -> str:
            if isinstance(client_info, (list, tuple)) and client_info:
                return f"bt:{client_info[0]}"
            return f"bt:{client_info}"


__all__ = ["BluetoothServer", "BLUETOOTH_AVAILABLE"]