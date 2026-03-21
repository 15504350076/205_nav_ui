"""评估模块：计算平面误差、RMS 与误差历史序列。"""

from __future__ import annotations

import math
from dataclasses import dataclass

from platform_state import PlatformState


@dataclass(slots=True, frozen=True)
class NavigationEstimate:
    platform_id: str
    platform_type: str
    x: float
    y: float
    z: float
    timestamp: float


@dataclass(slots=True, frozen=True)
class GroundTruth:
    platform_id: str
    x: float
    y: float
    z: float
    timestamp: float


@dataclass(slots=True, frozen=True)
class EvaluationResult:
    platform_id: str
    planar_error: float | None
    rms_planar_error: float | None
    sample_count: int


def extract_navigation_estimate(state: PlatformState) -> NavigationEstimate:
    return NavigationEstimate(
        platform_id=str(state.id),
        platform_type=str(state.type),
        x=float(state.x),
        y=float(state.y),
        z=float(state.z),
        timestamp=float(state.timestamp),
    )


def extract_ground_truth(state: PlatformState) -> GroundTruth | None:
    if state.truth_x is None or state.truth_y is None or state.truth_z is None:
        return None
    return GroundTruth(
        platform_id=str(state.id),
        x=float(state.truth_x),
        y=float(state.truth_y),
        z=float(state.truth_z),
        timestamp=float(state.timestamp),
    )


def compute_planar_error(
    estimate: NavigationEstimate,
    truth: GroundTruth | None,
) -> float | None:
    if truth is None:
        return None
    return math.hypot(estimate.x - truth.x, estimate.y - truth.y)


def compute_planar_error_from_state(state: PlatformState) -> float | None:
    estimate = extract_navigation_estimate(state)
    truth = extract_ground_truth(state)
    return compute_planar_error(estimate, truth)


class EvaluationService:
    """聚合导航估计/真值并产出误差评估结果。"""

    def __init__(self, history_duration_sec: float = 12.0, max_samples: int = 2000) -> None:
        self.history_duration_sec = max(0.1, float(history_duration_sec))
        self.max_samples = max(20, int(max_samples))
        self.latest_estimate_by_id: dict[str, NavigationEstimate] = {}
        self.latest_truth_by_id: dict[str, GroundTruth] = {}
        self.error_series_by_id: dict[str, list[float]] = {}
        self.error_timestamps_by_id: dict[str, list[float]] = {}

    def reset(self) -> None:
        self.latest_estimate_by_id.clear()
        self.latest_truth_by_id.clear()
        self.error_series_by_id.clear()
        self.error_timestamps_by_id.clear()

    def clear_histories(self, platform_states: list[PlatformState]) -> None:
        """清空历史，但保留当前时刻的最新评估点。"""
        self.error_series_by_id.clear()
        self.error_timestamps_by_id.clear()
        for state in platform_states:
            estimate = extract_navigation_estimate(state)
            truth = extract_ground_truth(state)
            platform_id = estimate.platform_id
            self.latest_estimate_by_id[platform_id] = estimate
            if truth is None:
                self.latest_truth_by_id.pop(platform_id, None)
                continue
            self.latest_truth_by_id[platform_id] = truth
            planar_error = compute_planar_error(estimate, truth)
            if planar_error is None:
                continue
            self.error_series_by_id[platform_id] = [planar_error]
            self.error_timestamps_by_id[platform_id] = [estimate.timestamp]

    def set_history_duration(self, duration_sec: float) -> None:
        self.history_duration_sec = max(0.1, float(duration_sec))
        for platform_id in list(self.error_series_by_id):
            self._trim_history(platform_id)

    def remove_platforms(self, platform_ids: list[str]) -> None:
        for platform_id in platform_ids:
            self.latest_estimate_by_id.pop(platform_id, None)
            self.latest_truth_by_id.pop(platform_id, None)
            self.error_series_by_id.pop(platform_id, None)
            self.error_timestamps_by_id.pop(platform_id, None)

    def update(self, platform_states: list[PlatformState]) -> None:
        for state in platform_states:
            estimate = extract_navigation_estimate(state)
            self.latest_estimate_by_id[estimate.platform_id] = estimate
            truth = extract_ground_truth(state)
            if truth is not None:
                self.latest_truth_by_id[truth.platform_id] = truth

            planar_error = compute_planar_error(estimate, truth)
            if planar_error is None:
                continue
            platform_id = estimate.platform_id
            series = self.error_series_by_id.setdefault(platform_id, [])
            timestamps = self.error_timestamps_by_id.setdefault(platform_id, [])
            series.append(planar_error)
            timestamps.append(estimate.timestamp)
            self._trim_history(platform_id)

    def get_error_series(self, platform_id: str) -> list[float]:
        return list(self.error_series_by_id.get(platform_id, []))

    def get_metrics(self, platform_id: str) -> EvaluationResult | None:
        estimate = self.latest_estimate_by_id.get(platform_id)
        if estimate is None:
            return None
        truth = self.latest_truth_by_id.get(platform_id)
        current_planar_error = compute_planar_error(estimate, truth)
        series = self.error_series_by_id.get(platform_id, [])
        if series:
            mean_sq = sum(item * item for item in series) / len(series)
            rms_error = math.sqrt(mean_sq)
        else:
            rms_error = None
        return EvaluationResult(
            platform_id=platform_id,
            planar_error=current_planar_error,
            rms_planar_error=rms_error,
            sample_count=len(series),
        )

    def _trim_history(self, platform_id: str) -> None:
        series = self.error_series_by_id.get(platform_id)
        timestamps = self.error_timestamps_by_id.get(platform_id)
        if series is None or timestamps is None:
            return
        if not series or not timestamps:
            return

        min_len = min(len(series), len(timestamps))
        series[:] = series[-min_len:]
        timestamps[:] = timestamps[-min_len:]

        while len(series) > self.max_samples:
            series.pop(0)
            timestamps.pop(0)

        cutoff_time = timestamps[-1] - self.history_duration_sec
        while len(timestamps) > 1 and timestamps[1] < cutoff_time:
            timestamps.pop(0)
            series.pop(0)
