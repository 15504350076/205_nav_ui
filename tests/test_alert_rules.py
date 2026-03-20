from alert_rules import (
    AlertThresholdConfig,
    get_default_alert_threshold_presets,
    resolve_error_threshold,
)


def test_resolve_error_threshold_prefers_id_override() -> None:
    config = AlertThresholdConfig(
        unified_threshold=4.0,
        use_type_threshold=True,
        uav_threshold=3.0,
        ugv_threshold=2.0,
        use_id_threshold=True,
        id_overrides={"UAV1": 1.5},
    )

    threshold, scope = resolve_error_threshold("UAV1", "UAV", config)

    assert threshold == 1.5
    assert scope == "ID阈值(UAV1)"


def test_resolve_error_threshold_uses_type_when_no_id_override() -> None:
    config = AlertThresholdConfig(
        unified_threshold=4.0,
        use_type_threshold=True,
        uav_threshold=3.2,
        ugv_threshold=2.2,
        use_id_threshold=True,
        id_overrides={},
    )

    threshold, scope = resolve_error_threshold("UAV9", "UAV", config)

    assert threshold == 3.2
    assert scope == "类型阈值(UAV)"


def test_resolve_error_threshold_falls_back_to_unified() -> None:
    config = AlertThresholdConfig(
        unified_threshold=5.0,
        use_type_threshold=False,
        use_id_threshold=False,
    )

    threshold, scope = resolve_error_threshold("X1", "UNKNOWN", config)

    assert threshold == 5.0
    assert scope == "统一阈值"


def test_default_presets_contain_expected_keys() -> None:
    presets = get_default_alert_threshold_presets()
    keys = [item.key for item in presets]

    assert "custom" in keys
    assert "balanced" in keys
    assert "sensitive" in keys
    assert "robust" in keys
    assert "ground_focus" in keys
