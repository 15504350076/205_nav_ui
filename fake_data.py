"""假数据生成模块：提供 UAV/UGV 轨迹、真值与扰动估计数据。"""

import math
import random

from data_source import PlatformDataSource
from platform_state import PlatformState


class FakeDataGenerator(PlatformDataSource):
    """生成用于界面原型测试的假数据。"""

    def __init__(self) -> None:
        self.t = 0.0
        self.dt = 0.08
        self.packet_loss_enabled = False
        self.packet_loss_rate = 0.0
        self.rng = random.Random(205)
        self.platforms = [
            {"id": "UAV1", "type": "UAV", "x": -180.0, "y": -80.0, "z": 30.0},
            {"id": "UAV2", "type": "UAV", "x": 120.0, "y": -120.0, "z": 35.0},
            {"id": "UGV1", "type": "UGV", "x": -140.0, "y": 140.0, "z": 0.0},
            {"id": "UGV2", "type": "UGV", "x": 160.0, "y": 100.0, "z": 0.0},
            {"id": "UGV3", "type": "UGV", "x": 20.0, "y": 40.0, "z": 0.0},
        ]

    def set_packet_loss_enabled(self, enabled: bool) -> None:
        self.packet_loss_enabled = enabled

    def set_packet_loss_rate(self, rate: float) -> None:
        self.packet_loss_rate = max(0.0, min(0.95, rate))

    def _estimate_from_truth(
        self, truth_x: float, truth_y: float, truth_z: float, platform_type: str
    ) -> tuple[float, float, float]:
        if platform_type == "UAV":
            xy_std = 1.2
            z_std = 0.8
        else:
            xy_std = 0.6
            z_std = 0.2
        est_x = truth_x + self.rng.gauss(0.0, xy_std)
        est_y = truth_y + self.rng.gauss(0.0, xy_std)
        est_z = truth_z + self.rng.gauss(0.0, z_std)
        return est_x, est_y, est_z

    def get_initial_data(self) -> list[PlatformState]:
        initial: list[PlatformState] = []
        for platform in self.platforms:
            truth_x = platform["x"]
            truth_y = platform["y"]
            truth_z = platform["z"]
            est_x, est_y, est_z = self._estimate_from_truth(
                truth_x, truth_y, truth_z, platform["type"]
            )
            initial.append(
                PlatformState(
                    id=platform["id"],
                    type=platform["type"],
                    x=est_x,
                    y=est_y,
                    z=est_z,
                    vx=0.0,
                    vy=0.0,
                    vz=0.0,
                    speed=0.0,
                    timestamp=self.t,
                    is_online=True,
                    truth_x=truth_x,
                    truth_y=truth_y,
                    truth_z=truth_z,
                )
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

    def get_next_frame(self) -> list[PlatformState]:
        self.t += self.dt

        updated: list[PlatformState] = []
        for i, platform in enumerate(self.platforms):
            truth_prev_x, truth_prev_y, truth_prev_z = self._calc_position(
                platform, i, self.t - self.dt
            )
            truth_x, truth_y, truth_z = self._calc_position(platform, i, self.t)
            x, y, z = self._estimate_from_truth(
                truth_x, truth_y, truth_z, platform["type"]
            )

            vx = (truth_x - truth_prev_x) / self.dt
            vy = (truth_y - truth_prev_y) / self.dt
            vz = (truth_z - truth_prev_z) / self.dt
            speed = math.sqrt(vx * vx + vy * vy + vz * vz)

            updated.append(
                PlatformState(
                    id=platform["id"],
                    type=platform["type"],
                    x=x,
                    y=y,
                    z=z,
                    vx=vx,
                    vy=vy,
                    vz=vz,
                    speed=speed,
                    timestamp=self.t,
                    is_online=True,
                    truth_x=truth_x,
                    truth_y=truth_y,
                    truth_z=truth_z,
                )
            )

        if not self.packet_loss_enabled or self.packet_loss_rate <= 0.0:
            return updated

        transmitted = [
            frame for frame in updated if self.rng.random() >= self.packet_loss_rate
        ]

        # Keep at least one platform each frame so the map timestamp keeps advancing.
        if not transmitted and updated:
            transmitted.append(updated[self.rng.randrange(len(updated))])
        return transmitted
