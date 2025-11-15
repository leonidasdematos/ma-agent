"""High level orchestration for the MA gateway agent."""
from __future__ import annotations

import logging
from typing import List

from .config import AgentConfig
from .implement import ImplementProfile, load_implement_profile
from .logging_utils import setup_logging
from .session import GatewaySession
from .simulators import PlanterSimulator
from .state import STATE
from .transport.bluetooth import BluetoothServer
from .transport.tcp import TcpServer

LOGGER = logging.getLogger(__name__)


class GatewayService:
    """Bootstrap and manage the transports that talk to the monitor."""

    def __init__(
        self,
        config: AgentConfig | None = None,
        implement_profile: ImplementProfile | None = None,
        *,
        telemetry_publisher=None,
        gnss_coordinator=None,
    ) -> None:
        self.config = config or AgentConfig.from_env()
        self.implement_profile = implement_profile or load_implement_profile(
            self.config.implement_profile_path
        )
        if telemetry_publisher is None and self.config.enable_planter_simulator:
            telemetry_publisher = PlanterSimulator(
                implement_profile=self.implement_profile,
                field_length_m=self.config.simulator_field_length_m,
                headland_length_m=self.config.simulator_headland_length_m,
                speed_mps=self.config.simulator_speed_mps,
                sample_rate_hz=self.config.simulator_sample_rate_hz,
                base_lat=self.config.simulator_base_lat,
                base_lon=self.config.simulator_base_lon,
                altitude_m=self.config.simulator_altitude_m,
                passes_per_cycle=self.config.simulator_passes_per_cycle,
                loop_forever=True,
                route_file=self.config.simulator_route_file,
                route_format=self.config.simulator_route_format,
            )
        self.telemetry_publisher = telemetry_publisher
        self.gnss_coordinator = gnss_coordinator
        self._servers: List = []

    def start(self) -> None:
        setup_logging()
        LOGGER.info("starting MA gateway service")

        tcp_server = TcpServer(
            self.config,
            session_factory=lambda: GatewaySession(
                state=STATE,
                implement_profile=self.implement_profile,
                telemetry_publisher=self.telemetry_publisher,
                gnss_coordinator=self.gnss_coordinator,
            ),
        )
        tcp_server.start()
        self._servers.append(tcp_server)

        if self.config.enable_bluetooth:
            bt_server = BluetoothServer(
                self.config,
                session_factory=lambda: GatewaySession(
                    state=STATE,
                    implement_profile=self.implement_profile,
                    telemetry_publisher=self.telemetry_publisher,
                    gnss_coordinator=self.gnss_coordinator,
                ),
            )
            bt_server.start()
            self._servers.append(bt_server)
        else:
            LOGGER.info("bluetooth transport disabled by configuration")

        LOGGER.info("service started with transports: %s", [s.name for s in self._servers])


__all__ = ["GatewayService"]
