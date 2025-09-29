"""Configuration model for the gateway agent."""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Optional


@dataclass(slots=True)
class AgentConfig:
    tcp_host: str = "0.0.0.0"
    tcp_port: int = 7777
    enable_bluetooth: bool = True
    bluetooth_channel: int = 1
    service_name: str = "MAGateway"

    @classmethod
    def from_env(cls) -> "AgentConfig":
        return cls(
            tcp_host=os.environ.get("MA_AGENT_TCP_HOST", "0.0.0.0"),
            tcp_port=int(os.environ.get("MA_AGENT_TCP_PORT", "7777")),
            enable_bluetooth=os.environ.get("MA_AGENT_ENABLE_BT", "1") not in {"0", "false", "False"},
            bluetooth_channel=int(os.environ.get("MA_AGENT_BT_CHANNEL", "1")),
            service_name=os.environ.get("MA_AGENT_SERVICE_NAME", "MAGateway"),
        )


__all__ = ["AgentConfig"]