"""单元测试模块：覆盖 alert_event 相关逻辑与边界行为。"""

from alert_event import AlertEvent


def test_alert_event_to_from_dict() -> None:
    event = AlertEvent(
        level="WARN",
        source="U1",
        message="m",
        epoch=100.0,
        status="已确认",
        time_text="2026-03-20 10:00:00",
    )
    restored = AlertEvent.from_dict(event.to_dict())

    assert restored.level == "WARN"
    assert restored.source == "U1"
    assert restored.message == "m"
    assert restored.epoch == 100.0
    assert restored.status == "已确认"
    assert restored.normalized_time_text() == "2026-03-20 10:00:00"


def test_alert_event_from_dict_defaults() -> None:
    restored = AlertEvent.from_dict({})

    assert restored.level == "INFO"
    assert restored.source == "--"
    assert restored.message == ""
    assert restored.status == "未确认"
