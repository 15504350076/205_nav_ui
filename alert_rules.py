"""告警规则模块：阈值配置、预设、版本化读写与差异比较。"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ALERT_THRESHOLD_CONFIG_SCHEMA_VERSION = 1


@dataclass(slots=True)
class AlertThresholdConfig:
    """误差告警阈值配置。"""

    unified_threshold: float = 4.0
    use_type_threshold: bool = False
    uav_threshold: float = 4.0
    ugv_threshold: float = 4.0
    use_id_threshold: bool = False
    id_overrides: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AlertThresholdPreset:
    key: str
    label: str
    description: str
    config: AlertThresholdConfig


@dataclass(frozen=True, slots=True)
class AlertThresholdConfigFileMeta:
    schema_version: int
    preset_key: str
    exported_at: str | None = None
    migrated_from_legacy: bool = False


def _clamp_threshold(value: float, default: float = 4.0) -> float:
    if not math.isfinite(value):
        return default
    return max(0.1, min(50.0, value))


def _as_float(value: Any, default: float) -> float:
    try:
        return _clamp_threshold(float(value), default=default)
    except (TypeError, ValueError):
        return default


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


def get_default_alert_threshold_presets() -> list[AlertThresholdPreset]:
    return [
        AlertThresholdPreset(
            key="custom",
            label="自定义",
            description="保持当前阈值配置，不自动覆盖。",
            config=AlertThresholdConfig(),
        ),
        AlertThresholdPreset(
            key="balanced",
            label="均衡预设",
            description="统一阈值4.0m，适合作为默认联调配置。",
            config=AlertThresholdConfig(
                unified_threshold=4.0,
                use_type_threshold=False,
                use_id_threshold=False,
                id_overrides={},
            ),
        ),
        AlertThresholdPreset(
            key="sensitive",
            label="敏感预设",
            description="优先发现偏差，告警更灵敏。",
            config=AlertThresholdConfig(
                unified_threshold=3.0,
                use_type_threshold=True,
                uav_threshold=3.2,
                ugv_threshold=2.0,
                use_id_threshold=False,
                id_overrides={},
            ),
        ),
        AlertThresholdPreset(
            key="robust",
            label="稳健预设",
            description="减少误报，适合噪声较大场景。",
            config=AlertThresholdConfig(
                unified_threshold=5.0,
                use_type_threshold=True,
                uav_threshold=5.5,
                ugv_threshold=3.5,
                use_id_threshold=False,
                id_overrides={},
            ),
        ),
        AlertThresholdPreset(
            key="ground_focus",
            label="地面精细预设",
            description="对UGV更严格，并支持按平台ID细化覆盖。",
            config=AlertThresholdConfig(
                unified_threshold=4.0,
                use_type_threshold=True,
                uav_threshold=4.5,
                ugv_threshold=2.0,
                use_id_threshold=True,
                id_overrides={
                    "UGV1": 1.6,
                    "UGV2": 1.6,
                    "UGV3": 1.8,
                },
            ),
        ),
    ]


def alert_threshold_config_from_dict(payload: dict[str, Any]) -> AlertThresholdConfig:
    config = AlertThresholdConfig()
    config.unified_threshold = _as_float(
        payload.get("unified_threshold"),
        config.unified_threshold,
    )
    config.use_type_threshold = _as_bool(
        payload.get("use_type_threshold"),
        config.use_type_threshold,
    )
    config.uav_threshold = _as_float(payload.get("uav_threshold"), config.uav_threshold)
    config.ugv_threshold = _as_float(payload.get("ugv_threshold"), config.ugv_threshold)
    config.use_id_threshold = _as_bool(
        payload.get("use_id_threshold"),
        config.use_id_threshold,
    )

    raw_overrides = payload.get("id_overrides", {})
    parsed_overrides: dict[str, float] = {}
    if isinstance(raw_overrides, dict):
        for platform_id, threshold in raw_overrides.items():
            if not isinstance(platform_id, str):
                continue
            normalized_id = platform_id.strip()
            if not normalized_id:
                continue
            parsed_overrides[normalized_id] = _as_float(threshold, default=4.0)
    config.id_overrides = parsed_overrides
    return config


def alert_threshold_config_to_dict(config: AlertThresholdConfig) -> dict[str, Any]:
    return {
        "unified_threshold": float(config.unified_threshold),
        "use_type_threshold": bool(config.use_type_threshold),
        "uav_threshold": float(config.uav_threshold),
        "ugv_threshold": float(config.ugv_threshold),
        "use_id_threshold": bool(config.use_id_threshold),
        "id_overrides": dict(config.id_overrides),
    }


def load_alert_threshold_config(path: Path) -> AlertThresholdConfig | None:
    loaded = load_alert_threshold_config_with_meta(path)
    if loaded is None:
        return None
    config, _meta = loaded
    return config


def load_alert_threshold_config_with_meta(
    path: Path,
) -> tuple[AlertThresholdConfig, AlertThresholdConfigFileMeta] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if "config" in payload and isinstance(payload.get("config"), dict):
        config_data = payload["config"]
        schema_data = payload.get("schema", {})
        if isinstance(schema_data, dict):
            schema_version_raw = schema_data.get("version", ALERT_THRESHOLD_CONFIG_SCHEMA_VERSION)
        else:
            schema_version_raw = ALERT_THRESHOLD_CONFIG_SCHEMA_VERSION
        try:
            schema_version = int(schema_version_raw)
        except (TypeError, ValueError):
            schema_version = ALERT_THRESHOLD_CONFIG_SCHEMA_VERSION

        meta_data = payload.get("meta", {})
        if isinstance(meta_data, dict):
            preset_key_raw = meta_data.get("preset_key", "custom")
            exported_at_raw = meta_data.get("exported_at")
        else:
            preset_key_raw = "custom"
            exported_at_raw = None
        preset_key = str(preset_key_raw) if preset_key_raw is not None else "custom"
        exported_at = str(exported_at_raw) if exported_at_raw is not None else None
        meta = AlertThresholdConfigFileMeta(
            schema_version=schema_version,
            preset_key=preset_key,
            exported_at=exported_at,
            migrated_from_legacy=False,
        )
        return alert_threshold_config_from_dict(config_data), meta

    # Legacy format: raw config dict without schema/meta wrapper.
    legacy_meta = AlertThresholdConfigFileMeta(
        schema_version=0,
        preset_key="custom",
        exported_at=None,
        migrated_from_legacy=True,
    )
    return alert_threshold_config_from_dict(payload), legacy_meta


def save_alert_threshold_config(
    path: Path,
    config: AlertThresholdConfig,
    *,
    preset_key: str = "custom",
) -> bool:
    payload = {
        "schema": {
            "name": "alert_threshold_config",
            "version": ALERT_THRESHOLD_CONFIG_SCHEMA_VERSION,
        },
        "meta": {
            "preset_key": str(preset_key),
            "exported_at": datetime.now(timezone.utc).isoformat(),
        },
        "config": alert_threshold_config_to_dict(config),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        return False
    return True


def diff_alert_threshold_configs(
    current: AlertThresholdConfig,
    reference: AlertThresholdConfig,
) -> list[tuple[str, str, str]]:
    diffs: list[tuple[str, str, str]] = []

    def append_if_diff(key: str, current_value: str, reference_value: str) -> None:
        if current_value == reference_value:
            return
        diffs.append((key, current_value, reference_value))

    append_if_diff(
        "统一阈值",
        f"{current.unified_threshold:.2f}",
        f"{reference.unified_threshold:.2f}",
    )
    append_if_diff("启用类型阈值", str(current.use_type_threshold), str(reference.use_type_threshold))
    append_if_diff("UAV阈值", f"{current.uav_threshold:.2f}", f"{reference.uav_threshold:.2f}")
    append_if_diff("UGV阈值", f"{current.ugv_threshold:.2f}", f"{reference.ugv_threshold:.2f}")
    append_if_diff("启用ID阈值", str(current.use_id_threshold), str(reference.use_id_threshold))

    current_keys = set(current.id_overrides)
    reference_keys = set(reference.id_overrides)
    all_keys = sorted(current_keys | reference_keys)
    for platform_id in all_keys:
        current_threshold = current.id_overrides.get(platform_id)
        reference_threshold = reference.id_overrides.get(platform_id)
        current_text = "--" if current_threshold is None else f"{current_threshold:.2f}"
        reference_text = "--" if reference_threshold is None else f"{reference_threshold:.2f}"
        append_if_diff(f"ID:{platform_id}", current_text, reference_text)

    return diffs


def resolve_error_threshold(
    platform_id: str,
    platform_type: str,
    config: AlertThresholdConfig,
) -> tuple[float, str]:
    normalized_id = platform_id.strip()
    if config.use_id_threshold:
        id_threshold = config.id_overrides.get(normalized_id)
        if id_threshold is not None:
            return id_threshold, f"ID阈值({normalized_id})"

    normalized_type = platform_type.upper().strip()
    if config.use_type_threshold:
        if normalized_type == "UAV":
            return config.uav_threshold, "类型阈值(UAV)"
        if normalized_type == "UGV":
            return config.ugv_threshold, "类型阈值(UGV)"
        return config.unified_threshold, f"类型阈值({normalized_type or 'UNKNOWN'})"

    return config.unified_threshold, "统一阈值"
