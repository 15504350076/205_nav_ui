from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


def _to_str(value: Any, default: str) -> str:
    if value is None:
        return default
    return str(value)


@dataclass(slots=True)
class AlertEvent:
    """统一告警事件模型（运行态与历史快照共用）。"""

    level: str
    source: str
    message: str
    epoch: float = 0.0
    status: str = "未确认"
    time_text: str | None = None

    def normalized_time_text(self) -> str:
        if self.time_text:
            return self.time_text
        return datetime.fromtimestamp(self.epoch).strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> dict[str, Any]:
        return {
            "epoch": float(self.epoch),
            "time": self.normalized_time_text(),
            "level": self.level,
            "source": self.source,
            "message": self.message,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AlertEvent:
        epoch_raw = payload.get("epoch")
        try:
            epoch = float(epoch_raw)
        except (TypeError, ValueError):
            epoch = 0.0
        return cls(
            level=_to_str(payload.get("level"), "INFO"),
            source=_to_str(payload.get("source"), "--"),
            message=_to_str(payload.get("message"), ""),
            epoch=epoch,
            status=_to_str(payload.get("status"), "未确认"),
            time_text=(str(payload.get("time")) if payload.get("time") is not None else None),
        )
