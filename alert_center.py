"""告警中心逻辑模块：告警筛选判定与来源分组统计。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(slots=True, frozen=True)
class AlertRow:
    """告警表格的一行快照（与UI解耦）。"""

    epoch: float | None
    level: str
    source: str
    message: str
    status: str


def should_show_alert(
    row: AlertRow,
    *,
    level_filter: object,
    status_filter: object,
    time_window_sec: object,
    keyword: str,
    now_epoch: float,
) -> bool:
    if level_filter not in (None, "all") and row.level != str(level_filter):
        return False
    if status_filter not in (None, "all") and row.status != str(status_filter):
        return False
    if (
        time_window_sec is not None
        and row.epoch is not None
        and now_epoch - row.epoch > float(time_window_sec)
    ):
        return False

    normalized_keyword = keyword.strip().lower()
    if normalized_keyword:
        source_text = row.source.lower()
        message_text = row.message.lower()
        if normalized_keyword not in source_text and normalized_keyword not in message_text:
            return False
    return True


def summarize_alert_rows(
    rows: Iterable[AlertRow],
) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    summary = {
        "total": 0,
        "INFO": 0,
        "WARN": 0,
        "ERROR": 0,
        "unacked": 0,
    }
    by_source: dict[str, dict[str, int]] = {}

    for row in rows:
        summary["total"] += 1
        if row.level in ("INFO", "WARN", "ERROR"):
            summary[row.level] += 1
        if row.status == "未确认":
            summary["unacked"] += 1

        source_stats = by_source.setdefault(
            row.source,
            {"total": 0, "INFO": 0, "WARN": 0, "ERROR": 0, "unacked": 0},
        )
        source_stats["total"] += 1
        if row.level in ("INFO", "WARN", "ERROR"):
            source_stats[row.level] += 1
        if row.status == "未确认":
            source_stats["unacked"] += 1

    return summary, by_source
