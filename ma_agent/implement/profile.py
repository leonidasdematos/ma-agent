"""Implement profile definitions and loading utilities."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, List, Optional

from ..paths import IMPLEMENT_CONFIG_FILE

LOGGER = logging.getLogger(__name__)

_DEFAULT_RESOURCE = "implement.vence_tudo.json"


# ``slots`` support for ``dataclasses`` was added in Python 3.10. Use it when
# available while staying compatible with Python 3.9.
_DATACLASS_KWARGS = {"slots": True} if sys.version_info >= (3, 10) else {}


@dataclass(**_DATACLASS_KWARGS)
class SectionProfile:
    """Metadata for a group of implement sections (e.g., seed, fertilizer)."""

    kind: str
    count: int
    supports_variable_rate: bool = False
    width_m: Optional[float] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SectionProfile":
        return cls(
            kind=data["kind"],
            count=int(data["count"]),
            supports_variable_rate=bool(data.get("supports_variable_rate", False)),
            width_m=float(data["width_m"]) if data.get("width_m") is not None else None,
        )

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "kind": self.kind,
            "count": self.count,
            "supports_variable_rate": self.supports_variable_rate,
        }
        if self.width_m is not None:
            payload["width_m"] = self.width_m
        return payload


@dataclass(**_DATACLASS_KWARGS)
class ImplementProfile:
    """Structured description of the implement attached to the gateway."""

    role: str
    name: str
    manufacturer: Optional[str]
    model: Optional[str]
    row_count: int
    row_spacing_m: float
    hitch_to_tool_m: float
    articulated: bool = False
    antenna_to_articulation_m: Optional[float] = None
    articulation_to_tool_m: Optional[float] = None
    sections: List[SectionProfile] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ImplementProfile":
        sections_data: Iterable[Dict[str, Any]] = data.get("sections", [])
        sections = [SectionProfile.from_dict(item) for item in sections_data]
        return cls(
            role=data["role"],
            name=data["name"],
            manufacturer=data.get("manufacturer"),
            model=data.get("model"),
            row_count=int(data["row_count"]),
            row_spacing_m=float(data["row_spacing_m"]),
            hitch_to_tool_m=float(data["hitch_to_tool_m"]),
            articulated=bool(data.get("articulated", False)),
            antenna_to_articulation_m=
                float(data["antenna_to_articulation_m"])
                if data.get("antenna_to_articulation_m") is not None
                else None,
            articulation_to_tool_m=
                float(data["articulation_to_tool_m"])
                if data.get("articulation_to_tool_m") is not None
                else None,
            sections=sections,
        )

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "role": self.role,
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "row_count": self.row_count,
            "row_spacing_m": self.row_spacing_m,
            "hitch_to_tool_m": self.hitch_to_tool_m,
            "sections": [section.to_payload() for section in self.sections],
        }
        payload["articulated"] = self.articulated
        if self.antenna_to_articulation_m is not None:
            payload["antenna_to_articulation_m"] = self.antenna_to_articulation_m
        if self.articulation_to_tool_m is not None:
            payload["articulation_to_tool_m"] = self.articulation_to_tool_m
        return payload


def _load_json_file(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _default_payload() -> Dict[str, Any]:
    data = resources.files("ma_agent.data").joinpath(_DEFAULT_RESOURCE).read_text(encoding="utf-8")
    return json.loads(data)


def load_implement_profile(explicit_path: Optional[str | Path] = None) -> ImplementProfile:
    """Load the implement profile, falling back to the bundled default."""

    candidates: List[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    candidates.append(IMPLEMENT_CONFIG_FILE)

    for candidate in candidates:
        if candidate and candidate.exists():
            try:
                payload = _load_json_file(candidate)
                LOGGER.info("using implement configuration from %s", candidate)
                return ImplementProfile.from_dict(payload)
            except Exception:
                LOGGER.exception("failed to load implement configuration from %s", candidate)

    LOGGER.warning(
        "implement configuration not found; falling back to bundled %s", _DEFAULT_RESOURCE
    )
    return ImplementProfile.from_dict(_default_payload())


__all__ = ["ImplementProfile", "SectionProfile", "load_implement_profile"]