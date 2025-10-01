"""Configuration model for the gateway agent."""
from __future__ import annotations

from dataclasses import dataclass
import os
import sys
from typing import Optional


# ``slots`` support for ``dataclasses`` was added in Python 3.10. Keep using
# slots where available, but remain compatible with Python 3.9.
_DATACLASS_KWARGS = {"slots": True} if sys.version_info >= (3, 10) else {}


@dataclass(**_DATACLASS_KWARGS)
class AgentConfig:
    tcp_host: str = "0.0.0.0"
    tcp_port: int = 7777
    enable_bluetooth: bool = True
    bluetooth_channel: int = 1
    service_name: str = "MAGateway"
    service_uuid: Optional[str] = None
    implement_profile_path: Optional[str] = None

    @classmethod
    def from_env(cls) -> "AgentConfig":
        return cls(
            tcp_host=os.environ.get("MA_AGENT_TCP_HOST", "0.0.0.0"),
            tcp_port=int(os.environ.get("MA_AGENT_TCP_PORT", "7777")),
            enable_bluetooth=os.environ.get("MA_AGENT_ENABLE_BT", "1") not in {"0", "false", "False"},
            bluetooth_channel=int(os.environ.get("MA_AGENT_BT_CHANNEL", "1")),
            service_name=os.environ.get("MA_AGENT_SERVICE_NAME", "MAGateway"),
            service_uuid=os.environ.get("MA_AGENT_BT_SERVICE_UUID"),
            implement_profile_path=os.environ.get("MA_AGENT_IMPLEMENT_CONFIG"),
        )


__all__ = ["AgentConfig"]