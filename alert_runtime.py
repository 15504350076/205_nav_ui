from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from models import PlatformState


@dataclass(slots=True, frozen=True)
class RuntimeAlertEvent:
    level: str
    source: str
    message: str


@dataclass(slots=True)
class RuntimeAlertEngine:
    """运行态告警规则引擎（与UI解耦）。"""

    last_stale_platform_ids: set[str] = field(default_factory=set)
    last_error_alert_timestamp_by_id: dict[str, float] = field(default_factory=dict)
    error_exceed_count_by_id: dict[str, int] = field(default_factory=dict)

    def reset(self) -> None:
        self.last_stale_platform_ids.clear()
        self.last_error_alert_timestamp_by_id.clear()
        self.error_exceed_count_by_id.clear()

    def clear_planar_error_state(self) -> None:
        self.last_error_alert_timestamp_by_id.clear()
        self.error_exceed_count_by_id.clear()

    def evaluate(
        self,
        *,
        all_platforms: list[PlatformState],
        stale_ids: set[str],
        removed_ids: list[str],
        trigger_enabled: bool,
        enable_stale: bool,
        enable_recover: bool,
        enable_offline: bool,
        enable_planar_error: bool,
        cooldown_sec: float,
        escalate_count: int,
        threshold_resolver: Callable[[str, str], tuple[float, str]],
    ) -> list[RuntimeAlertEvent]:
        events: list[RuntimeAlertEvent] = []

        if not trigger_enabled:
            self.error_exceed_count_by_id.clear()
            self.last_stale_platform_ids = set(stale_ids)
            return events

        newly_stale = stale_ids - self.last_stale_platform_ids
        recovered = self.last_stale_platform_ids - stale_ids

        if enable_stale:
            for platform_id in sorted(newly_stale):
                events.append(RuntimeAlertEvent("WARN", platform_id, "平台状态超时"))

        if enable_recover:
            for platform_id in sorted(recovered):
                events.append(RuntimeAlertEvent("INFO", platform_id, "平台恢复正常"))

        if enable_offline:
            for platform_id in removed_ids:
                events.append(RuntimeAlertEvent("ERROR", platform_id, "平台超时下线并已移除"))

        if enable_planar_error:
            active_ids = {str(state.id) for state in all_platforms}
            for platform_id in list(self.error_exceed_count_by_id):
                if platform_id not in active_ids:
                    self.error_exceed_count_by_id.pop(platform_id, None)

            for state in all_platforms:
                if state.truth_x is None or state.truth_y is None:
                    continue

                planar_error = math.hypot(state.x - state.truth_x, state.y - state.truth_y)
                platform_id = str(state.id)
                error_threshold, threshold_scope = threshold_resolver(platform_id, str(state.type))
                if planar_error <= error_threshold:
                    self.error_exceed_count_by_id[platform_id] = 0
                    continue

                exceed_count = self.error_exceed_count_by_id.get(platform_id, 0) + 1
                self.error_exceed_count_by_id[platform_id] = exceed_count

                last_alert_ts = self.last_error_alert_timestamp_by_id.get(platform_id, -1e9)
                if state.timestamp - last_alert_ts < cooldown_sec:
                    continue

                self.last_error_alert_timestamp_by_id[platform_id] = state.timestamp
                level = "ERROR" if exceed_count >= max(1, int(escalate_count)) else "WARN"
                events.append(
                    RuntimeAlertEvent(
                        level,
                        platform_id,
                        (
                            f"平面误差超阈值: {planar_error:.2f} m "
                            f"(> {error_threshold:.2f} m, {threshold_scope}, 连续{exceed_count}次)"
                        ),
                    )
                )
        else:
            self.error_exceed_count_by_id.clear()

        self.last_stale_platform_ids = set(stale_ids)
        return events
