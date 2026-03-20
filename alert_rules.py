from __future__ import annotations

from dataclasses import dataclass, field


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
