from pathlib import Path

from alert_history import AlertRecord
from alert_history_service import AlertHistoryService


def test_alert_history_service_save_load_and_export(tmp_path: Path) -> None:
    service = AlertHistoryService(tmp_path / "exports" / "alerts")
    records = [
        AlertRecord(epoch=1.0, level="INFO", source="A", message="a"),
        AlertRecord(epoch=2.0, level="WARN", source="B", message="b", status="已确认"),
    ]

    assert service.save_snapshot(records)
    loaded = service.load_snapshot()
    assert len(loaded) == 2
    assert loaded[1].status == "已确认"

    exported = service.export_jsonl(records)
    assert exported is not None
    assert exported.exists()
    assert exported.suffix == ".jsonl"


def test_alert_history_service_prune_records(tmp_path: Path) -> None:
    service = AlertHistoryService(tmp_path / "exports" / "alerts")
    records = [
        AlertRecord(epoch=100.0, level="INFO", source="A", message="a"),
        AlertRecord(epoch=190.0, level="WARN", source="B", message="b"),
        AlertRecord(epoch=180000.0, level="ERROR", source="C", message="c"),
    ]

    pruned, removed = service.prune_records(
        records,
        retention_days=1,
        now_epoch=200000.0,
    )

    assert removed == 2
    assert [item.source for item in pruned] == ["C"]
