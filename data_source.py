from pathlib import Path
from typing import Protocol

from platform_state import PlatformState


class PlatformDataSource(Protocol):
    """可替换的数据源接口。"""

    def get_initial_data(self) -> list[PlatformState]:
        ...

    def get_next_frame(self) -> list[PlatformState]:
        ...


class ReplayCapableDataSource(PlatformDataSource, Protocol):
    """具备录制与回放能力的数据源接口。"""

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
