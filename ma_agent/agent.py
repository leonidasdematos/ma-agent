#!/usr/bin/env python3
"""Entry-point used by systemd to launch the MA gateway agent."""
from __future__ import annotations

import signal
import threading
import time

from .config import AgentConfig
from .gateway import GatewayService
from .telemetry import SimulatedTelemetryPublisher



def main() -> None:
    config = AgentConfig.from_env()
    telemetry_publisher = SimulatedTelemetryPublisher()
    service = GatewayService(config, telemetry_publisher=telemetry_publisher)
    service.start()

    # Mantém a thread principal viva enquanto os transports rodam em background.
    stop_event = threading.Event()

    def _handle_signal(signum, frame):  # pragma: no cover - signal handling
        stop_event.set()

    # registra os sinais FORA do handler
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        while not stop_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        telemetry_publisher.stop()


if __name__ == "__main__":  # pragma: no cover
    main()