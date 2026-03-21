"""数据适配器协议模块：统一实时/回放数据适配器接口。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from platform_state import PlatformState


@dataclass(slots=True, frozen=True)
class AdapterStatus:
    connected: bool
    mode: str
    source_name: str
    message: str = ""


class DataAdapter(Protocol):
    """统一数据适配器接口：主界面只依赖该接口。"""

    def connect(self) -> bool:
        ...

    def disconnect(self) -> None:
        ...

    def poll(self) -> list[PlatformState]:
        ...

    def next_frame(self) -> list[PlatformState]:
        ...

    def is_live(self) -> bool:
        ...

    def get_status(self) -> AdapterStatus:
        ...


class ReplayDataAdapter(DataAdapter, Protocol):
    """支持录制/回放控制的数据适配器接口。"""

    @property
    def is_recording(self) -> bool:
        ...

    @property
    def is_replay_mode(self) -> bool:
        ...

    @property
    def replay_total_frames(self) -> int:
        ...

    @property
    def replay_frame_index(self) -> int:
        ...

    @replay_frame_index.setter
    def replay_frame_index(self, value: int) -> None:
        ...

    def start_recording(self) -> bool:
        ...

    def stop_recording(self) -> list[list[PlatformState]]:
        ...

    def save_recording_jsonl(self, path: Path) -> bool:
        ...

    def load_replay_jsonl(self, path: Path) -> bool:
        ...

    def exit_replay_mode(self) -> None:
        ...

    def step_back_replay_cursor(self) -> bool:
        ...
