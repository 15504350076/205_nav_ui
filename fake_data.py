import math
from typing import List


class FakeDataGenerator:
    """生成用于界面原型测试的假数据。"""

    def __init__(self) -> None:
        self.t = 0.0
        self.platforms = [
            {"id": "UAV1", "type": "UAV", "x": -180.0, "y": -80.0, "z": 30.0},
            {"id": "UAV2", "type": "UAV", "x": 120.0, "y": -120.0, "z": 35.0},
            {"id": "UGV1", "type": "UGV", "x": -140.0, "y": 140.0, "z": 0.0},
            {"id": "UGV2", "type": "UGV", "x": 160.0, "y": 100.0, "z": 0.0},
            {"id": "UGV3", "type": "UGV", "x": 20.0, "y": 40.0, "z": 0.0},
        ]

    def get_initial_data(self) -> List[dict]:
        return [platform.copy() for platform in self.platforms]

    def get_next_frame(self) -> List[dict]:
        self.t += 0.08

        updated = []
        for i, platform in enumerate(self.platforms):
            phase = self.t + i * 0.7

            if platform["type"] == "UAV":
                x = platform["x"] + 12.0 * math.cos(phase)
                y = platform["y"] + 8.0 * math.sin(phase * 1.2)
                z = 30.0 + 5.0 * math.sin(phase * 0.8)
            else:
                x = platform["x"] + 6.0 * math.cos(phase * 0.7)
                y = platform["y"] + 5.0 * math.sin(phase * 0.9)
                z = 0.0

            updated.append(
                {
                    "id": platform["id"],
                    "type": platform["type"],
                    "x": x,
                    "y": y,
                    "z": z,
                }
            )

        return updated