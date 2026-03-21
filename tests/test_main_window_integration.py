import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from main_window import MainWindow
from platform_state import PlatformState


class EmptyDataSource:
    def get_initial_data(self) -> list[PlatformState]:
        return []

    def get_next_frame(self) -> list[PlatformState]:
        return []


def make_state(platform_id: str, timestamp: float) -> PlatformState:
    return PlatformState(
        id=platform_id,
        type="UAV",
        x=timestamp,
        y=0.0,
        z=0.0,
        timestamp=timestamp,
        is_online=True,
    )


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def window(qapp: QApplication, tmp_path, monkeypatch: pytest.MonkeyPatch):
    del qapp
    monkeypatch.chdir(tmp_path)
    main = MainWindow(data_source=EmptyDataSource())
    main.timer.stop()
    main.alert_table.setRowCount(0)
    try:
        yield main
    finally:
        main.close()


def visible_rows(main: MainWindow) -> list[int]:
    rows: list[int] = []
    for row in range(main.alert_table.rowCount()):
        if not main.alert_table.isRowHidden(row):
            rows.append(row)
    return rows


def test_alert_filter_ack_and_clear_flow(window: MainWindow) -> None:
    window._append_alert("WARN", "U1", "alpha", apply_filters=False, persist_history=False)
    window._append_alert("WARN", "U2", "beta", apply_filters=False, persist_history=False)
    window._append_alert("ERROR", "U3", "gamma", apply_filters=False, persist_history=False)

    window.alert_keyword_edit.setText("U1")
    window.apply_alert_filters()
    assert len(visible_rows(window)) == 1

    window.on_ack_visible_unacked_alerts()
    assert window.alert_table.item(0, 4).text() == "已确认"
    assert window.alert_table.item(1, 4).text() == "未确认"

    window.on_clear_acknowledged_alerts()
    assert window.alert_table.rowCount() == 2

    window.alert_keyword_edit.clear()
    window.apply_alert_filters()
    window.on_clear_visible_alerts()
    assert window.alert_table.rowCount() == 0


def test_source_runtime_label_updates(window: MainWindow) -> None:
    window.on_timer_update()
    text = window.source_status_label.text()
    assert text.startswith("数据源:")
    assert "connected" in text or "not connected" in text


def test_motion_monitor_detects_dropped_pose(qapp: QApplication, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    del qapp
    monkeypatch.chdir(tmp_path)

    class RosLikeSource:
        def __init__(self) -> None:
            self._frame_count = 0
            self._counter_query_count = 0
            self._initial = [
                PlatformState(
                    id="UAV1",
                    type="UAV",
                    x=1.0,
                    y=2.0,
                    z=0.0,
                    timestamp=1.0,
                    is_online=True,
                )
            ]

        def get_initial_data(self) -> list[PlatformState]:
            self._frame_count += 1
            return list(self._initial)

        def get_runtime_counters(self) -> dict[str, int | float]:
            self._counter_query_count += 1
            if self._counter_query_count <= 1:
                return {"raw_pose": 1, "accepted": 1, "drop": 0, "invalid_ts": 0}
            return {"raw_pose": 2, "accepted": 1, "drop": 1, "invalid_ts": 1}

        def get_next_frame(self) -> list[PlatformState]:
            self._frame_count += 1
            return []

    window = MainWindow(data_source=RosLikeSource())
    window.timer.stop()
    try:
        window.on_timer_update()
        text = window.motion_monitor_label.text()
        assert "位置监视[UAV1]" in text
        assert "[ERR]" in text
        assert "时间戳回退被丢弃" in text
        assert "#b42318" in window.motion_monitor_label.styleSheet()
    finally:
        window.close()


def test_replay_mode_linkage(window: MainWindow, tmp_path: Path) -> None:
    replay_file = tmp_path / "exports" / "recordings" / "integration_replay.jsonl"
    replay_file.parent.mkdir(parents=True, exist_ok=True)
    frames = [
        [make_state("U1", 1.0).to_dict()],
        [make_state("U1", 2.0).to_dict()],
        [make_state("U1", 3.0).to_dict()],
    ]
    with replay_file.open("w", encoding="utf-8") as file:
        for frame in frames:
            file.write(json.dumps(frame, ensure_ascii=False))
            file.write("\n")

    assert window.load_replay_from_path(replay_file)
    assert window.data_source.is_replay_mode
    assert "回放" in window.replay_status_label.text()
    assert window.platform_manager.get_all_platforms()[0].timestamp == 1.0

    window.on_replay_next_frame()
    assert window.platform_manager.get_all_platforms()[0].timestamp == 2.0

    window.on_replay_prev_frame()
    assert window.platform_manager.get_all_platforms()[0].timestamp == 1.0

    window.on_replay_slider_changed(2)
    assert window.platform_manager.get_all_platforms()[0].timestamp == 3.0

    window.on_exit_replay_mode()
    assert not window.data_source.is_replay_mode
    assert window.platform_manager.get_all_platforms() == []
