#!/usr/bin/env python3
"""Entry-point used by systemd to launch the MA gateway agent."""
from __future__ import annotations

import signal
import threading
import time

from .config import AgentConfig
from .gateway import GatewayService
from .implement import load_implement_profile
from .simulators import PlanterSimulator


def main() -> None:
    config = AgentConfig.from_env()
    telemetry_publisher = None
    if config.enable_planter_simulator:
        implement_profile = load_implement_profile(config.implement_profile_path)
        telemetry_publisher = PlanterSimulator(
            implement_profile=implement_profile,
            field_length_m=config.simulator_field_length_m,
            headland_length_m=config.simulator_headland_length_m,
            speed_mps=config.simulator_speed_mps,
            sample_rate_hz=config.simulator_sample_rate_hz,
            base_lat=config.simulator_base_lat,
            base_lon=config.simulator_base_lon,
            altitude_m=config.simulator_altitude_m,
            passes_per_cycle=config.simulator_passes_per_cycle,
            loop_forever=True,
            route_file=config.simulator_route_file,
            route_format=config.simulator_route_format,
        )

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
        telemetry_publisher = getattr(service, "telemetry_publisher", None)
        stop = getattr(telemetry_publisher, "stop", None)
        if callable(stop):
            stop()

if __name__ == "__main__":  # pragma: no cover
    main()