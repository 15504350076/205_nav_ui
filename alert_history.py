from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from alert_event import AlertEvent
AlertRecord = AlertEvent


def alert_record_from_dict(payload: dict[str, Any]) -> AlertRecord:
    return AlertRecord.from_dict(payload)


def alert_record_to_dict(record: AlertRecord) -> dict[str, Any]:
    return record.to_dict()


def load_alert_history(path: Path) -> list[AlertRecord]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    records: list[AlertRecord] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        records.append(alert_record_from_dict(item))
    return records


def save_alert_history(path: Path, records: list[AlertRecord]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [alert_record_to_dict(item) for item in records]
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        return False
    return True


def export_alert_history_jsonl(path: Path, records: list[AlertRecord]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            for record in records:
                file.write(json.dumps(alert_record_to_dict(record), ensure_ascii=False))
                file.write("\n")
    except OSError:
        return False
    return True


def prune_alert_history(
    records: list[AlertRecord],
    max_age_sec: float,
    *,
    now_epoch: float | None = None,
) -> list[AlertRecord]:
    if max_age_sec <= 0.0:
        return list(records)
    if now_epoch is None:
        from datetime import datetime

        now_epoch = datetime.now().timestamp()
    cutoff = now_epoch - max_age_sec
    return [item for item in records if item.epoch >= cutoff]
