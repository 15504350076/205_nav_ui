from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AlertRecord:
    epoch: float
    level: str
    source: str
    message: str
    status: str = "未确认"
    time_text: str | None = None

    def normalized_time_text(self) -> str:
        if self.time_text:
            return self.time_text
        return datetime.fromtimestamp(self.epoch).strftime("%Y-%m-%d %H:%M:%S")


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_str(value: Any, default: str) -> str:
    if value is None:
        return default
    return str(value)


def alert_record_from_dict(payload: dict[str, Any]) -> AlertRecord:
    epoch = _to_float(payload.get("epoch"), 0.0)
    return AlertRecord(
        epoch=epoch,
        level=_to_str(payload.get("level"), "INFO"),
        source=_to_str(payload.get("source"), "--"),
        message=_to_str(payload.get("message"), ""),
        status=_to_str(payload.get("status"), "未确认"),
        time_text=_to_str(payload.get("time"), "") or None,
    )


def alert_record_to_dict(record: AlertRecord) -> dict[str, Any]:
    return {
        "epoch": float(record.epoch),
        "time": record.normalized_time_text(),
        "level": record.level,
        "source": record.source,
        "message": record.message,
        "status": record.status,
    }


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
        now_epoch = datetime.now().timestamp()
    cutoff = now_epoch - max_age_sec
    return [item for item in records if item.epoch >= cutoff]
