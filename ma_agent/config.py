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
    enable_planter_simulator: bool = True
    simulator_field_length_m: float = 300.0
    simulator_headland_length_m: float = 20.0
    simulator_speed_mps: float = 2.5
    simulator_sample_rate_hz: float = 2.0
    simulator_passes_per_cycle: int = 8
    simulator_base_lat: float = -22.000000
    simulator_base_lon: float = -47.000000
    simulator_altitude_m: float = 550.0

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
            enable_planter_simulator=os.environ.get("MA_AGENT_ENABLE_SIMULATOR", "1")
                                     not in {"0", "false", "False"},
            simulator_field_length_m=float(
                os.environ.get("MA_AGENT_SIM_FIELD_LENGTH_M", "300.0")
            ),
            simulator_headland_length_m=float(
                os.environ.get("MA_AGENT_SIM_HEADLAND_M", "20.0")
            ),
            simulator_speed_mps=float(os.environ.get("MA_AGENT_SIM_SPEED_MPS", "2.5")),
            simulator_sample_rate_hz=float(
                os.environ.get("MA_AGENT_SIM_SAMPLE_HZ", "2.0")
            ),
            simulator_passes_per_cycle=int(
                os.environ.get("MA_AGENT_SIM_PASSES_PER_CYCLE", "8")
            ),
            simulator_base_lat=float(os.environ.get("MA_AGENT_SIM_BASE_LAT", "-22.0")),
            simulator_base_lon=float(os.environ.get("MA_AGENT_SIM_BASE_LON", "-47.0")),
            simulator_altitude_m=float(os.environ.get("MA_AGENT_SIM_ALTITUDE_M", "550.0")),
        )


__all__ = ["AgentConfig"]