from dataclasses import dataclass


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

    def to_dict(self) -> dict:
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

