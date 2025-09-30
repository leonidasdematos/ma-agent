"""Runtime state for the gateway service."""
from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time
from typing import Any, Dict, Optional

from .versioning import read_version


@dataclass
class AgentState:
    """Thread-safe store with the gateway runtime information."""

    job_running: bool = False
    uptime_start: float = field(default_factory=time.time)
    last_command: Optional[Dict[str, Any]] = None

    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def mark_command(self, command: Dict[str, Any]) -> None:
        with self._lock:
            self.last_command = command

    def set_job_running(self, running: bool) -> None:
        with self._lock:
            self.job_running = running

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "job_running": self.job_running,
                "uptime_s": int(time.time() - self.uptime_start),
                "last_command": self.last_command,
            }


STATE = AgentState()
VERSION = read_version()

__all__ = ["AgentState", "STATE", "VERSION"]