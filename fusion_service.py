from __future__ import annotations

import math
from dataclasses import dataclass

from platform_state import PlatformState


def _clamp_ratio(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass(slots=True, frozen=True)
class FusionConfig:
    """融合参数：测量权重 + 预测窗口 + 可选真值辅助权重。"""

    measurement_weight: float = 0.8
    max_prediction_gap_sec: float = 1.0
    truth_weight: float = 0.0


class PositionFusionService:
    """位置融合服务：融合当前测量与上一帧运动预测。"""

    def __init__(self, config: FusionConfig | None = None) -> None:
        self.config = config or FusionConfig()
        self._history_by_platform_id: dict[str, PlatformState] = {}

    def reset(self) -> None:
        self._history_by_platform_id.clear()

    def fuse_frame(self, states: list[PlatformState]) -> list[PlatformState]:
        return [self.fuse_state(state) for state in states]

    def fuse_state(self, state: PlatformState) -> PlatformState:
        prev = self._history_by_platform_id.get(state.id)
        fused_x = float(state.x)
        fused_y = float(state.y)
        fused_z = float(state.z)

        if prev is not None:
            dt = float(state.timestamp) - float(prev.timestamp)
            if dt > 0.0 and dt <= max(0.05, float(self.config.max_prediction_gap_sec)):
                predicted_x = float(prev.x) + float(state.vx) * dt
                predicted_y = float(prev.y) + float(state.vy) * dt
                predicted_z = float(prev.z) + float(state.vz) * dt
                w = _clamp_ratio(self.config.measurement_weight)
                fused_x = w * fused_x + (1.0 - w) * predicted_x
                fused_y = w * fused_y + (1.0 - w) * predicted_y
                fused_z = w * fused_z + (1.0 - w) * predicted_z

        truth_w = _clamp_ratio(self.config.truth_weight)
        if truth_w > 0.0:
            if state.truth_x is not None:
                fused_x = (1.0 - truth_w) * fused_x + truth_w * float(state.truth_x)
            if state.truth_y is not None:
                fused_y = (1.0 - truth_w) * fused_y + truth_w * float(state.truth_y)
            if state.truth_z is not None:
                fused_z = (1.0 - truth_w) * fused_z + truth_w * float(state.truth_z)

        # Guard against invalid numeric propagation.
        if not math.isfinite(fused_x):
            fused_x = float(state.x)
        if not math.isfinite(fused_y):
            fused_y = float(state.y)
        if not math.isfinite(fused_z):
            fused_z = float(state.z)

        fused_state = PlatformState(
            id=state.id,
            type=state.type,
            x=fused_x,
            y=fused_y,
            z=fused_z,
            vx=state.vx,
            vy=state.vy,
            vz=state.vz,
            speed=state.speed,
            timestamp=state.timestamp,
            is_online=state.is_online,
            link_state=state.link_state,
            nav_state=state.nav_state,
            truth_x=state.truth_x,
            truth_y=state.truth_y,
            truth_z=state.truth_z,
        )
        self._history_by_platform_id[state.id] = fused_state
        return fused_state
