"""High level orchestration for the MA gateway agent."""
from __future__ import annotations

import logging
from typing import List

from .config import AgentConfig
from implement import ImplementProfile, load_implement_profile
from logging_utils import setup_logging
from session import GatewaySession
from state import STATE
from transport.bluetooth import BluetoothServer
from transport.tcp import TcpServer

LOGGER = logging.getLogger(__name__)


class GatewayService:
    """Bootstrap and manage the transports that talk to the monitor."""

    def __init__(
        self,
        config: AgentConfig | None = None,
        implement_profile: ImplementProfile | None = None,
    ) -> None:
        self.config = config or AgentConfig.from_env()
        self.implement_profile = implement_profile or load_implement_profile(
            self.config.implement_profile_path
        )
        self._servers: List = []

    def start(self) -> None:
        setup_logging()
        LOGGER.info("starting MA gateway service")

        tcp_server = TcpServer(
            self.config,
            session_factory=lambda: GatewaySession(state=STATE, implement_profile=self.implement_profile),
        )
        tcp_server.start()
        self._servers.append(tcp_server)

        if self.config.enable_bluetooth:
            bt_server = BluetoothServer(
                self.config,
                session_factory=lambda: GatewaySession(
                    state=STATE, implement_profile=self.implement_profile
                ),
            )
            bt_server.start()
            self._servers.append(bt_server)
        else:
            LOGGER.info("bluetooth transport disabled by configuration")

        LOGGER.info("service started with transports: %s", [s.name for s in self._servers])


__all__ = ["GatewayService"]