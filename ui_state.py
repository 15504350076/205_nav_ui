from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _as_str(value: Any, default: str) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return default
    return str(value)


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _as_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class UiState:
    """主窗口UI状态快照。"""

    platform_type_filter: str = "all"
    platform_status_filter: str = "all"
    platform_keyword: str = ""
    platform_sort_column: int = 0
    platform_sort_order: int = 0
    alert_level_filter: str = "all"
    alert_status_filter: str = "all"
    alert_time_filter_sec: float | None = None
    alert_keyword: str = ""
    follow_selected: bool = False
    follow_lock_when_enabled: bool = True
    show_tracks: bool = True
    show_labels: bool = True
    show_truth_points: bool = True
    show_truth_tracks: bool = True
    show_velocity_vectors: bool = False
    track_duration_sec: float = 12.0
    alert_trigger_enabled: bool = True
    alert_enable_planar_error: bool = True
    alert_enable_stale: bool = True
    alert_enable_recover: bool = True
    alert_enable_offline: bool = True
    alert_error_cooldown_sec: float = 1.5
    alert_error_escalate_count: int = 3
    alert_restore_history_on_start: bool = True
    alert_history_retention_days: int = 7
    alert_error_threshold: float = 4.0
    alert_use_type_threshold: bool = False
    alert_error_threshold_uav: float = 4.0
    alert_error_threshold_ugv: float = 4.0
    alert_threshold_preset_key: str = "custom"
    alert_use_id_threshold: bool = False
    alert_id_threshold_overrides: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UiState":
        state = cls()
        state.platform_type_filter = _as_str(data.get("platform_type_filter"), state.platform_type_filter)
        state.platform_status_filter = _as_str(
            data.get("platform_status_filter"),
            state.platform_status_filter,
        )
        state.platform_keyword = _as_str(data.get("platform_keyword"), state.platform_keyword)
        state.platform_sort_column = _as_int(data.get("platform_sort_column"), state.platform_sort_column)
        state.platform_sort_order = _as_int(data.get("platform_sort_order"), state.platform_sort_order)
        if state.platform_sort_order not in (0, 1):
            state.platform_sort_order = 0

        state.alert_level_filter = _as_str(data.get("alert_level_filter"), state.alert_level_filter)
        state.alert_status_filter = _as_str(data.get("alert_status_filter"), state.alert_status_filter)
        raw_time_filter = data.get("alert_time_filter_sec")
        if raw_time_filter is None:
            state.alert_time_filter_sec = None
        else:
            state.alert_time_filter_sec = _as_float(raw_time_filter, 0.0)
        state.alert_keyword = _as_str(data.get("alert_keyword"), state.alert_keyword)

        state.follow_selected = _as_bool(data.get("follow_selected"), state.follow_selected)
        state.follow_lock_when_enabled = _as_bool(
            data.get("follow_lock_when_enabled"),
            state.follow_lock_when_enabled,
        )
        state.show_tracks = _as_bool(data.get("show_tracks"), state.show_tracks)
        state.show_labels = _as_bool(data.get("show_labels"), state.show_labels)
        state.show_truth_points = _as_bool(data.get("show_truth_points"), state.show_truth_points)
        state.show_truth_tracks = _as_bool(data.get("show_truth_tracks"), state.show_truth_tracks)
        state.show_velocity_vectors = _as_bool(
            data.get("show_velocity_vectors"),
            state.show_velocity_vectors,
        )

        state.track_duration_sec = _as_float(data.get("track_duration_sec"), state.track_duration_sec)
        state.alert_trigger_enabled = _as_bool(
            data.get("alert_trigger_enabled"),
            state.alert_trigger_enabled,
        )
        state.alert_enable_planar_error = _as_bool(
            data.get("alert_enable_planar_error"),
            state.alert_enable_planar_error,
        )
        state.alert_enable_stale = _as_bool(
            data.get("alert_enable_stale"),
            state.alert_enable_stale,
        )
        state.alert_enable_recover = _as_bool(
            data.get("alert_enable_recover"),
            state.alert_enable_recover,
        )
        state.alert_enable_offline = _as_bool(
            data.get("alert_enable_offline"),
            state.alert_enable_offline,
        )
        state.alert_error_cooldown_sec = _as_float(
            data.get("alert_error_cooldown_sec"),
            state.alert_error_cooldown_sec,
        )
        state.alert_error_escalate_count = max(
            1,
            _as_int(data.get("alert_error_escalate_count"), state.alert_error_escalate_count),
        )
        state.alert_restore_history_on_start = _as_bool(
            data.get("alert_restore_history_on_start"),
            state.alert_restore_history_on_start,
        )
        state.alert_history_retention_days = max(
            1,
            _as_int(data.get("alert_history_retention_days"), state.alert_history_retention_days),
        )
        state.alert_error_threshold = _as_float(
            data.get("alert_error_threshold"),
            state.alert_error_threshold,
        )
        state.alert_use_type_threshold = _as_bool(
            data.get("alert_use_type_threshold"),
            state.alert_use_type_threshold,
        )
        state.alert_error_threshold_uav = _as_float(
            data.get("alert_error_threshold_uav"),
            state.alert_error_threshold_uav,
        )
        state.alert_error_threshold_ugv = _as_float(
            data.get("alert_error_threshold_ugv"),
            state.alert_error_threshold_ugv,
        )
        state.alert_threshold_preset_key = _as_str(
            data.get("alert_threshold_preset_key"),
            state.alert_threshold_preset_key,
        )
        state.alert_use_id_threshold = _as_bool(
            data.get("alert_use_id_threshold"),
            state.alert_use_id_threshold,
        )

        raw_overrides = data.get("alert_id_threshold_overrides", {})
        parsed_overrides: dict[str, float] = {}
        if isinstance(raw_overrides, dict):
            for platform_id, threshold in raw_overrides.items():
                if not isinstance(platform_id, str):
                    continue
                normalized_id = platform_id.strip()
                if not normalized_id:
                    continue
                parsed_overrides[normalized_id] = _as_float(threshold, 4.0)
        state.alert_id_threshold_overrides = parsed_overrides
        return state

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform_type_filter": self.platform_type_filter,
            "platform_status_filter": self.platform_status_filter,
            "platform_keyword": self.platform_keyword,
            "platform_sort_column": self.platform_sort_column,
            "platform_sort_order": self.platform_sort_order,
            "alert_level_filter": self.alert_level_filter,
            "alert_status_filter": self.alert_status_filter,
            "alert_time_filter_sec": self.alert_time_filter_sec,
            "alert_keyword": self.alert_keyword,
            "follow_selected": self.follow_selected,
            "follow_lock_when_enabled": self.follow_lock_when_enabled,
            "show_tracks": self.show_tracks,
            "show_labels": self.show_labels,
            "show_truth_points": self.show_truth_points,
            "show_truth_tracks": self.show_truth_tracks,
            "show_velocity_vectors": self.show_velocity_vectors,
            "track_duration_sec": self.track_duration_sec,
            "alert_trigger_enabled": self.alert_trigger_enabled,
            "alert_enable_planar_error": self.alert_enable_planar_error,
            "alert_enable_stale": self.alert_enable_stale,
            "alert_enable_recover": self.alert_enable_recover,
            "alert_enable_offline": self.alert_enable_offline,
            "alert_error_cooldown_sec": self.alert_error_cooldown_sec,
            "alert_error_escalate_count": self.alert_error_escalate_count,
            "alert_restore_history_on_start": self.alert_restore_history_on_start,
            "alert_history_retention_days": self.alert_history_retention_days,
            "alert_error_threshold": self.alert_error_threshold,
            "alert_use_type_threshold": self.alert_use_type_threshold,
            "alert_error_threshold_uav": self.alert_error_threshold_uav,
            "alert_error_threshold_ugv": self.alert_error_threshold_ugv,
            "alert_threshold_preset_key": self.alert_threshold_preset_key,
            "alert_use_id_threshold": self.alert_use_id_threshold,
            "alert_id_threshold_overrides": dict(self.alert_id_threshold_overrides),
        }


def load_ui_state(path: Path) -> UiState | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return UiState.from_dict(payload)


def save_ui_state(path: Path, state: UiState) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        return False
    return True
