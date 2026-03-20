from pathlib import Path

from ui_state import UiState, load_ui_state, save_ui_state


def test_from_dict_parses_basic_fields() -> None:
    payload = {
        "platform_type_filter": "UGV",
        "platform_status_filter": "超时",
        "platform_keyword": "UGV",
        "platform_sort_column": 3,
        "platform_sort_order": 1,
        "show_velocity_vectors": True,
        "track_duration_sec": 25.5,
        "alert_use_type_threshold": True,
        "alert_error_threshold_uav": 3.5,
        "alert_error_threshold_ugv": 2.0,
    }

    state = UiState.from_dict(payload)

    assert state.platform_type_filter == "UGV"
    assert state.platform_status_filter == "超时"
    assert state.platform_sort_column == 3
    assert state.platform_sort_order == 1
    assert state.show_velocity_vectors is True
    assert state.track_duration_sec == 25.5
    assert state.alert_use_type_threshold is True
    assert state.alert_error_threshold_uav == 3.5
    assert state.alert_error_threshold_ugv == 2.0


def test_from_dict_handles_invalid_values_with_defaults() -> None:
    payload = {
        "platform_sort_column": "bad",
        "platform_sort_order": 9,
        "track_duration_sec": "oops",
        "show_tracks": "false",
        "alert_error_threshold": None,
    }

    state = UiState.from_dict(payload)

    assert state.platform_sort_column == 0
    assert state.platform_sort_order == 0
    assert state.track_duration_sec == 12.0
    assert state.show_tracks is False
    assert state.alert_error_threshold == 4.0


def test_ui_state_round_trip_file(tmp_path: Path) -> None:
    path = tmp_path / ".ui_state.json"
    source = UiState(
        platform_type_filter="UAV",
        platform_sort_column=2,
        platform_sort_order=1,
        show_velocity_vectors=True,
        alert_use_type_threshold=True,
        alert_error_threshold_uav=4.2,
    )

    assert save_ui_state(path, source)
    loaded = load_ui_state(path)

    assert loaded is not None
    assert loaded.to_dict() == source.to_dict()


def test_load_ui_state_handles_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / ".ui_state.json"
    path.write_text("{bad json", encoding="utf-8")

    assert load_ui_state(path) is None
