from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from alert_history import (
    AlertRecord,
    export_alert_history_jsonl,
    load_alert_history,
    prune_alert_history,
    save_alert_history,
)


@dataclass(slots=True, frozen=True)
class AlertHistoryService:
    """告警历史快照读写与导出服务。"""

    export_dir: Path
    store_filename: str = ".alert_history.json"

    @property
    def store_path(self) -> Path:
        return self.export_dir / self.store_filename

    def save_snapshot(self, records: list[AlertRecord]) -> bool:
        return save_alert_history(self.store_path, records)

    def load_snapshot(self) -> list[AlertRecord]:
        return load_alert_history(self.store_path)

    def export_jsonl(self, records: list[AlertRecord]) -> Path | None:
        self.export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = self.export_dir / f"alert_history_{timestamp}.jsonl"
        if not export_alert_history_jsonl(file_path, records):
            return None
        return file_path

    def prune_records(
        self,
        records: list[AlertRecord],
        *,
        retention_days: int,
        now_epoch: float | None = None,
    ) -> tuple[list[AlertRecord], int]:
        max_age_sec = float(max(1, retention_days)) * 24.0 * 60.0 * 60.0
        pruned = prune_alert_history(records, max_age_sec, now_epoch=now_epoch)
        removed = len(records) - len(pruned)
        return pruned, removed
