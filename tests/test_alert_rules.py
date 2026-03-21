"""单元测试模块：覆盖 alert_rules 相关逻辑与边界行为。"""

from pathlib import Path

from alert_rules import (
    ALERT_THRESHOLD_CONFIG_SCHEMA_VERSION,
    AlertThresholdConfig,
    alert_threshold_config_from_dict,
    alert_threshold_config_to_dict,
    diff_alert_threshold_configs,
    get_default_alert_threshold_presets,
    load_alert_threshold_config,
    load_alert_threshold_config_with_meta,
    resolve_error_threshold,
    save_alert_threshold_config,
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


def test_alert_threshold_config_from_dict_handles_invalid_values() -> None:
    config = alert_threshold_config_from_dict(
        {
            "unified_threshold": "999",
            "use_type_threshold": "true",
            "uav_threshold": "nan",
            "ugv_threshold": -5,
            "use_id_threshold": 1,
            "id_overrides": {"UAV1": "3.3", "  ": "2.0", "UGV1": "nan"},
        }
    )

    assert config.unified_threshold == 50.0
    assert config.use_type_threshold is True
    assert config.uav_threshold == 4.0
    assert config.ugv_threshold == 0.1
    assert config.use_id_threshold is True
    assert config.id_overrides == {"UAV1": 3.3, "UGV1": 4.0}


def test_alert_threshold_config_round_trip_file(tmp_path: Path) -> None:
    path = tmp_path / "threshold_config.json"
    source = AlertThresholdConfig(
        unified_threshold=3.5,
        use_type_threshold=True,
        uav_threshold=3.0,
        ugv_threshold=2.2,
        use_id_threshold=True,
        id_overrides={"UAV1": 2.1, "UGV2": 1.7},
    )

    assert save_alert_threshold_config(path, source, preset_key="ground_focus")
    loaded = load_alert_threshold_config(path)

    assert loaded is not None
    assert alert_threshold_config_to_dict(loaded) == alert_threshold_config_to_dict(source)

    loaded_with_meta = load_alert_threshold_config_with_meta(path)
    assert loaded_with_meta is not None
    _loaded_config, meta = loaded_with_meta
    assert meta.schema_version == ALERT_THRESHOLD_CONFIG_SCHEMA_VERSION
    assert meta.preset_key == "ground_focus"
    assert meta.exported_at is not None
    assert meta.migrated_from_legacy is False


def test_load_alert_threshold_config_invalid_json_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "threshold_config.json"
    path.write_text("{bad", encoding="utf-8")

    assert load_alert_threshold_config(path) is None


def test_load_alert_threshold_config_legacy_format_marks_migration(tmp_path: Path) -> None:
    path = tmp_path / "legacy_threshold_config.json"
    path.write_text(
        '{"unified_threshold": 4.4, "use_type_threshold": false, "id_overrides": {"UAV1": 2.2}}',
        encoding="utf-8",
    )

    loaded = load_alert_threshold_config_with_meta(path)

    assert loaded is not None
    config, meta = loaded
    assert config.unified_threshold == 4.4
    assert config.id_overrides == {"UAV1": 2.2}
    assert meta.schema_version == 0
    assert meta.preset_key == "custom"
    assert meta.migrated_from_legacy is True


def test_diff_alert_threshold_configs_lists_changed_fields() -> None:
    reference = AlertThresholdConfig(
        unified_threshold=4.0,
        use_type_threshold=False,
        uav_threshold=4.0,
        ugv_threshold=4.0,
        use_id_threshold=False,
        id_overrides={},
    )
    current = AlertThresholdConfig(
        unified_threshold=3.0,
        use_type_threshold=True,
        uav_threshold=3.2,
        ugv_threshold=2.2,
        use_id_threshold=True,
        id_overrides={"UGV1": 1.8},
    )

    diffs = diff_alert_threshold_configs(current, reference)
    diff_keys = {item[0] for item in diffs}

    assert "统一阈值" in diff_keys
    assert "启用类型阈值" in diff_keys
    assert "UAV阈值" in diff_keys
    assert "UGV阈值" in diff_keys
    assert "启用ID阈值" in diff_keys
    assert "ID:UGV1" in diff_keys
