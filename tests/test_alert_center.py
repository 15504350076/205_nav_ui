from alert_center import AlertRow, should_show_alert, summarize_alert_rows


def test_should_show_alert_applies_level_status_keyword_filters() -> None:
    row = AlertRow(
        epoch=100.0,
        level="WARN",
        source="UAV1",
        message="plane error high",
        status="未确认",
    )

    assert should_show_alert(
        row,
        level_filter="WARN",
        status_filter="未确认",
        time_window_sec=None,
        keyword="uav1",
        now_epoch=200.0,
    )
    assert not should_show_alert(
        row,
        level_filter="ERROR",
        status_filter="未确认",
        time_window_sec=None,
        keyword="uav1",
        now_epoch=200.0,
    )
    assert not should_show_alert(
        row,
        level_filter="WARN",
        status_filter="已确认",
        time_window_sec=None,
        keyword="uav1",
        now_epoch=200.0,
    )
    assert not should_show_alert(
        row,
        level_filter="WARN",
        status_filter="未确认",
        time_window_sec=None,
        keyword="missing",
        now_epoch=200.0,
    )


def test_should_show_alert_time_window_requires_epoch() -> None:
    with_epoch = AlertRow(
        epoch=100.0,
        level="INFO",
        source="A",
        message="x",
        status="未确认",
    )
    without_epoch = AlertRow(
        epoch=None,
        level="INFO",
        source="A",
        message="x",
        status="未确认",
    )

    assert not should_show_alert(
        with_epoch,
        level_filter="all",
        status_filter="all",
        time_window_sec=30.0,
        keyword="",
        now_epoch=200.0,
    )
    assert should_show_alert(
        without_epoch,
        level_filter="all",
        status_filter="all",
        time_window_sec=30.0,
        keyword="",
        now_epoch=200.0,
    )


def test_summarize_alert_rows_groups_by_source_and_level() -> None:
    rows = [
        AlertRow(epoch=1.0, level="INFO", source="U1", message="m1", status="未确认"),
        AlertRow(epoch=2.0, level="WARN", source="U1", message="m2", status="已确认"),
        AlertRow(epoch=3.0, level="ERROR", source="U2", message="m3", status="未确认"),
        AlertRow(epoch=4.0, level="TRACE", source="U2", message="m4", status="未确认"),
    ]

    summary, by_source = summarize_alert_rows(rows)

    assert summary == {
        "total": 4,
        "INFO": 1,
        "WARN": 1,
        "ERROR": 1,
        "unacked": 3,
    }
    assert by_source["U1"] == {
        "total": 2,
        "INFO": 1,
        "WARN": 1,
        "ERROR": 0,
        "unacked": 1,
    }
    assert by_source["U2"] == {
        "total": 2,
        "INFO": 0,
        "WARN": 0,
        "ERROR": 1,
        "unacked": 2,
    }
