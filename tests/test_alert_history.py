from pathlib import Path

from alert_history import (
    AlertRecord,
    alert_record_from_dict,
    alert_record_to_dict,
    export_alert_history_jsonl,
    load_alert_history,
    prune_alert_history,
    save_alert_history,
)


def test_alert_record_dict_round_trip() -> None:
    source = AlertRecord(
        epoch=100.0,
        level="WARN",
        source="UAV1",
        message="test",
        status="未确认",
        time_text="2026-03-20 10:00:00",
    )

    payload = alert_record_to_dict(source)
    restored = alert_record_from_dict(payload)

    assert restored.epoch == 100.0
    assert restored.level == "WARN"
    assert restored.source == "UAV1"
    assert restored.message == "test"
    assert restored.status == "未确认"
    assert restored.normalized_time_text() == "2026-03-20 10:00:00"


def test_save_and_load_alert_history(tmp_path: Path) -> None:
    path = tmp_path / "alerts.json"
    records = [
        AlertRecord(epoch=1.0, level="INFO", source="A", message="a"),
        AlertRecord(epoch=2.0, level="ERROR", source="B", message="b", status="已确认"),
    ]

    assert save_alert_history(path, records)
    loaded = load_alert_history(path)

    assert len(loaded) == 2
    assert loaded[0].level == "INFO"
    assert loaded[1].status == "已确认"


def test_export_alert_history_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "alerts.jsonl"
    records = [
        AlertRecord(epoch=1.0, level="INFO", source="A", message="a"),
        AlertRecord(epoch=2.0, level="WARN", source="B", message="b"),
    ]

    assert export_alert_history_jsonl(path, records)
    lines = path.read_text(encoding="utf-8").strip().splitlines()

    assert len(lines) == 2
    assert '"level": "INFO"' in lines[0]
    assert '"level": "WARN"' in lines[1]


def test_prune_alert_history_by_age() -> None:
    records = [
        AlertRecord(epoch=100.0, level="INFO", source="A", message="a"),
        AlertRecord(epoch=190.0, level="WARN", source="B", message="b"),
        AlertRecord(epoch=200.0, level="ERROR", source="C", message="c"),
    ]

    pruned = prune_alert_history(records, max_age_sec=20.0, now_epoch=200.0)

    assert [item.source for item in pruned] == ["B", "C"]
