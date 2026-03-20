import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from alert_history import load_alert_history
from main_window import MainWindow
from models import PlatformState


class EmptyDataSource:
    def get_initial_data(self) -> list[PlatformState]:
        return []

    def get_next_frame(self) -> list[PlatformState]:
        return []


def make_state(
    platform_id: str,
    timestamp: float,
    *,
    platform_type: str = "UAV",
    x: float = 0.0,
    y: float = 0.0,
    truth_x: float | None = None,
    truth_y: float | None = None,
) -> PlatformState:
    return PlatformState(
        id=platform_id,
        type=platform_type,
        x=x,
        y=y,
        z=0.0,
        timestamp=timestamp,
        truth_x=truth_x,
        truth_y=truth_y,
        truth_z=0.0 if truth_x is not None and truth_y is not None else None,
        is_online=True,
    )


def collect_alert_rows(window: MainWindow) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for row in range(window.alert_table.rowCount()):
        level = window.alert_table.item(row, 1).text()
        source = window.alert_table.item(row, 2).text()
        message = window.alert_table.item(row, 3).text()
        rows.append((level, source, message))
    return rows


def visible_rows(window: MainWindow) -> list[int]:
    rows: list[int] = []
    for row in range(window.alert_table.rowCount()):
        if not window.alert_table.isRowHidden(row):
            rows.append(row)
    return rows


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def alert_window(qapp: QApplication, tmp_path, monkeypatch: pytest.MonkeyPatch):
    del qapp
    monkeypatch.chdir(tmp_path)
    window = MainWindow(data_source=EmptyDataSource())
    window.timer.stop()
    window.alert_table.setRowCount(0)
    window.runtime_alert_engine.reset()
    try:
        yield window
    finally:
        window.close()


def test_apply_frame_update_raises_stale_and_recover_alerts(alert_window: MainWindow) -> None:
    alert_window.stale_timeout_spin.setValue(0.5)
    alert_window.remove_timeout_spin.setValue(5.0)

    alert_window._apply_frame_update(
        [make_state("U1", 0.0), make_state("G1", 0.0, platform_type="UGV")]
    )
    alert_window.alert_table.setRowCount(0)
    alert_window.runtime_alert_engine.last_stale_platform_ids = set()

    alert_window._apply_frame_update([make_state("G1", 1.0, platform_type="UGV")])
    alert_window._apply_frame_update(
        [make_state("U1", 1.1), make_state("G1", 1.1, platform_type="UGV")]
    )

    rows = collect_alert_rows(alert_window)
    assert any(level == "WARN" and source == "U1" and "超时" in message for level, source, message in rows)
    assert any(
        level == "INFO" and source == "U1" and "恢复正常" in message
        for level, source, message in rows
    )


def test_apply_frame_update_raises_offline_alert_on_removal(alert_window: MainWindow) -> None:
    alert_window.stale_timeout_spin.setValue(0.5)
    alert_window.remove_timeout_spin.setValue(1.0)

    alert_window._apply_frame_update(
        [make_state("U1", 0.0), make_state("G1", 0.0, platform_type="UGV")]
    )
    alert_window.alert_table.setRowCount(0)
    alert_window.runtime_alert_engine.last_stale_platform_ids = set()

    alert_window._apply_frame_update([make_state("G1", 1.2, platform_type="UGV")])

    rows = collect_alert_rows(alert_window)
    assert any(
        level == "ERROR" and source == "U1" and "下线" in message
        for level, source, message in rows
    )


def test_planar_error_alert_escalates_to_error(alert_window: MainWindow) -> None:
    alert_window.alert_error_threshold_spin.setValue(1.0)
    alert_window.alert_error_cooldown_spin.setValue(0.0)
    alert_window.alert_error_escalate_count_spin.setValue(2)
    alert_window.alert_use_type_threshold_checkbox.setChecked(False)
    alert_window.alert_use_id_threshold_checkbox.setChecked(False)

    alert_window._apply_frame_update(
        [make_state("U1", 1.0, x=5.0, y=0.0, truth_x=0.0, truth_y=0.0)]
    )
    alert_window._apply_frame_update(
        [make_state("U1", 2.0, x=5.0, y=0.0, truth_x=0.0, truth_y=0.0)]
    )

    rows = collect_alert_rows(alert_window)
    levels = [level for level, source, message in rows if source == "U1" and "误差超阈值" in message]
    assert levels == ["WARN", "ERROR"]


def test_alert_time_window_filter_hides_expired_rows(alert_window: MainWindow) -> None:
    now_epoch = datetime.now().timestamp()
    alert_window._append_alert(
        "INFO",
        "U1",
        "old",
        timestamp_epoch=now_epoch - 1200.0,
        apply_filters=False,
        persist_history=False,
    )
    alert_window._append_alert(
        "INFO",
        "U2",
        "recent",
        timestamp_epoch=now_epoch - 120.0,
        apply_filters=False,
        persist_history=False,
    )

    ten_min_index = alert_window.alert_time_filter_combo.findData(10 * 60)
    assert ten_min_index >= 0
    alert_window.alert_time_filter_combo.setCurrentIndex(ten_min_index)
    alert_window.apply_alert_filters()

    visible_sources = {
        alert_window.alert_table.item(row, 2).text()
        for row in visible_rows(alert_window)
    }
    assert visible_sources == {"U2"}


def test_ack_visible_unacked_only_affects_visible_rows(alert_window: MainWindow) -> None:
    alert_window._append_alert("WARN", "U1", "alpha", apply_filters=False, persist_history=False)
    alert_window._append_alert("WARN", "U2", "beta", apply_filters=False, persist_history=False)
    alert_window.alert_keyword_edit.setText("U1")
    alert_window.apply_alert_filters()

    alert_window.on_ack_visible_unacked_alerts()

    status_u1 = alert_window.alert_table.item(0, 4).text()
    status_u2 = alert_window.alert_table.item(1, 4).text()
    assert status_u1 == "已确认"
    assert status_u2 == "未确认"


def test_alert_history_persist_and_manual_reload(
    qapp: QApplication,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del qapp
    monkeypatch.chdir(tmp_path)

    first = MainWindow(data_source=EmptyDataSource())
    first.timer.stop()
    first.alert_table.setRowCount(0)
    first._append_alert("ERROR", "U9", "persist me", apply_filters=False, persist_history=True)
    first.close()

    history_path = Path.cwd() / "exports" / "alerts" / ".alert_history.json"
    records = load_alert_history(history_path)
    assert len(records) == 1
    assert records[0].source == "U9"

    second = MainWindow(data_source=EmptyDataSource())
    second.timer.stop()
    second.alert_restore_history_checkbox.setChecked(False)
    second.alert_table.setRowCount(0)
    second.on_load_alert_history_snapshot()
    try:
        assert second.alert_table.rowCount() == 1
        assert second.alert_table.item(0, 2).text() == "U9"
    finally:
        second.close()


def test_prune_alert_history_removes_expired_rows(alert_window: MainWindow) -> None:
    now_epoch = datetime.now().timestamp()
    alert_window._append_alert(
        "WARN",
        "U1",
        "expired",
        timestamp_epoch=now_epoch - 3.0 * 24.0 * 3600.0,
        apply_filters=False,
        persist_history=False,
    )
    alert_window._append_alert(
        "WARN",
        "U2",
        "kept",
        timestamp_epoch=now_epoch - 0.2 * 24.0 * 3600.0,
        apply_filters=False,
        persist_history=False,
    )
    alert_window.alert_history_retention_days_spin.setValue(1)

    alert_window.on_prune_alert_history()

    rows = collect_alert_rows(alert_window)
    assert len(rows) == 1
    assert rows[0][1] == "U2"
