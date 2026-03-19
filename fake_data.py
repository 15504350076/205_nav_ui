import math
from typing import List


class FakeDataGenerator:
    """生成用于界面原型测试的假数据。"""

    def __init__(self) -> None:
        self.t = 0.0
        self.dt = 0.08
        self.platforms = [
            {"id": "UAV1", "type": "UAV", "x": -180.0, "y": -80.0, "z": 30.0},
            {"id": "UAV2", "type": "UAV", "x": 120.0, "y": -120.0, "z": 35.0},
            {"id": "UGV1", "type": "UGV", "x": -140.0, "y": 140.0, "z": 0.0},
            {"id": "UGV2", "type": "UGV", "x": 160.0, "y": 100.0, "z": 0.0},
            {"id": "UGV3", "type": "UGV", "x": 20.0, "y": 40.0, "z": 0.0},
        ]

    def get_initial_data(self) -> List[dict]:
        initial = []
        for platform in self.platforms:
            initial.append(
                {
                    "id": platform["id"],
                    "type": platform["type"],
                    "x": platform["x"],
                    "y": platform["y"],
                    "z": platform["z"],
                    "vx": 0.0,
                    "vy": 0.0,
                    "vz": 0.0,
                    "speed": 0.0,
                    "timestamp": self.t,
                }
            )
        return initial

    def _calc_position(self, platform: dict, i: int, t: float) -> tuple[float, float, float]:
        phase = t + i * 0.7

        if platform["type"] == "UAV":
            x = platform["x"] + 12.0 * math.cos(phase)
            y = platform["y"] + 8.0 * math.sin(phase * 1.2)
            z = 30.0 + 5.0 * math.sin(phase * 0.8)
        else:
            x = platform["x"] + 6.0 * math.cos(phase * 0.7)
            y = platform["y"] + 5.0 * math.sin(phase * 0.9)
            z = 0.0

        return x, y, z

    def get_next_frame(self) -> List[dict]:
        self.t += self.dt

        updated = []
        for i, platform in enumerate(self.platforms):
            x_prev, y_prev, z_prev = self._calc_position(platform, i, self.t - self.dt)
            x, y, z = self._calc_position(platform, i, self.t)

            vx = (x - x_prev) / self.dt
            vy = (y - y_prev) / self.dt
            vz = (z - z_prev) / self.dt
            speed = math.sqrt(vx * vx + vy * vy + vz * vz)

            updated.append(
                {
                    "id": platform["id"],
                    "type": platform["type"],
                    "x": x,
                    "y": y,
                    "z": z,
                    "vx": vx,
                    "vy": vy,
                    "vz": vz,
                    "speed": speed,
                    "timestamp": self.t,
                }
            )

        return updated