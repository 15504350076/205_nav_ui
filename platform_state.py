from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class PlatformState:
    """统一平台状态模型。"""

    id: str
    type: str
    x: float
    y: float
    z: float
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    speed: float = 0.0
    timestamp: float = 0.0
    is_online: bool = True
    truth_x: float | None = None
    truth_y: float | None = None
    truth_z: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "vx": self.vx,
            "vy": self.vy,
            "vz": self.vz,
            "speed": self.speed,
            "timestamp": self.timestamp,
            "is_online": self.is_online,
            "truth_x": self.truth_x,
            "truth_y": self.truth_y,
            "truth_z": self.truth_z,
        }

    @classmethod
    def from_dict(cls, raw_item: object) -> PlatformState | None:
        if not isinstance(raw_item, dict):
            return None
        try:
            return cls(
                id=str(raw_item["id"]),
                type=str(raw_item["type"]),
                x=float(raw_item["x"]),
                y=float(raw_item["y"]),
                z=float(raw_item["z"]),
                vx=float(raw_item.get("vx", 0.0)),
                vy=float(raw_item.get("vy", 0.0)),
                vz=float(raw_item.get("vz", 0.0)),
                speed=float(raw_item.get("speed", 0.0)),
                timestamp=float(raw_item.get("timestamp", 0.0)),
                is_online=bool(raw_item.get("is_online", True)),
                truth_x=(
                    float(raw_item["truth_x"])
                    if raw_item.get("truth_x") is not None
                    else None
                ),
                truth_y=(
                    float(raw_item["truth_y"])
                    if raw_item.get("truth_y") is not None
                    else None
                ),
                truth_z=(
                    float(raw_item["truth_z"])
                    if raw_item.get("truth_z") is not None
                    else None
                ),
            )
        except (KeyError, TypeError, ValueError):
            return None
