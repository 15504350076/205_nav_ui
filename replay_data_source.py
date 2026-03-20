from __future__ import annotations

import json
from pathlib import Path

from data_source import PlatformDataSource
from models import PlatformState


class ReplayDataSource(PlatformDataSource):
    """在实时数据源之上叠加录制与回放能力。"""

    def __init__(self, live_source: PlatformDataSource) -> None:
        self.live_source = live_source
        self._recording = False
        self._recorded_frames: list[list[dict]] = []
        self._replay_frames: list[list[PlatformState]] = []
        self._replay_index = 0
        self._replay_file_path: Path | None = None

    def __getattr__(self, name: str):
        return getattr(self.live_source, name)

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def is_replay_mode(self) -> bool:
        return bool(self._replay_frames)

    @property
    def replay_total_frames(self) -> int:
        return len(self._replay_frames)

    @property
    def replay_frame_index(self) -> int:
        return self._replay_index

    @replay_frame_index.setter
    def replay_frame_index(self, value: int) -> None:
        if not self._replay_frames:
            self._replay_index = 0
            return
        self._replay_index = max(0, min(int(value), len(self._replay_frames)))

    @property
    def replay_file_path(self) -> Path | None:
        return self._replay_file_path

    @property
    def recorded_frame_count(self) -> int:
        return len(self._recorded_frames)

    def get_initial_data(self) -> list[PlatformState]:
        return self.live_source.get_initial_data()

    def get_next_frame(self) -> list[PlatformState]:
        if self.is_replay_mode:
            if self._replay_index >= len(self._replay_frames):
                return []
            frame = self._replay_frames[self._replay_index]
            self._replay_index += 1
            return frame

        frame = self.live_source.get_next_frame()
        if self._recording:
            self._recorded_frames.append([state.to_dict() for state in frame])
        return frame

    def start_recording(self) -> bool:
        if self.is_replay_mode:
            return False
        self._recorded_frames = []
        self._recording = True
        return True

    def stop_recording(self) -> list[list[dict]]:
        self._recording = False
        return [list(frame) for frame in self._recorded_frames]

    def save_recording_jsonl(self, path: Path) -> bool:
        if not self._recorded_frames:
            return False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as file:
                for frame in self._recorded_frames:
                    file.write(json.dumps(frame, ensure_ascii=False))
                    file.write("\n")
        except OSError:
            return False
        return True

    def load_replay_jsonl(self, path: Path) -> bool:
        loaded_frames: list[list[PlatformState]] = []
        try:
            with path.open("r", encoding="utf-8") as file:
                for line in file:
                    line = line.strip()
                    if not line:
                        continue
                    raw_frame = json.loads(line)
                    if not isinstance(raw_frame, list):
                        continue
                    frame_states: list[PlatformState] = []
                    for item in raw_frame:
                        state = self._state_from_dict(item)
                        if state is not None:
                            frame_states.append(state)
                    loaded_frames.append(frame_states)
        except (OSError, json.JSONDecodeError):
            return False

        if not loaded_frames:
            return False

        self._recording = False
        self._replay_frames = loaded_frames
        self._replay_index = 0
        self._replay_file_path = path
        return True

    def exit_replay_mode(self) -> None:
        self._replay_frames = []
        self._replay_index = 0
        self._replay_file_path = None

    def step_back_replay_cursor(self) -> bool:
        if self._replay_index <= 1:
            return False
        self._replay_index -= 2
        return True

    @staticmethod
    def _state_from_dict(raw_item: object) -> PlatformState | None:
        if not isinstance(raw_item, dict):
            return None
        try:
            return PlatformState(
                id=str(raw_item["id"]),
                type=str(raw_item["type"]),
                x=float(raw_item["x"]),
                y=float(raw_item["y"]),
                z=float(raw_item["z"]),
                vx=float(raw_item.get("vx", 0.0)),
                vy=float(raw_item.get("vy", 0.0)),
                vz=float(raw_item.get("vz", 0.0)),
                speed=float(raw_item.get("speed", 0.0)),
                timestamp=float(raw_item.get("timestamp", 0.0)),
                is_online=bool(raw_item.get("is_online", True)),
                truth_x=(
                    float(raw_item["truth_x"])
                    if raw_item.get("truth_x") is not None
                    else None
                ),
                truth_y=(
                    float(raw_item["truth_y"])
                    if raw_item.get("truth_y") is not None
                    else None
                ),
                truth_z=(
                    float(raw_item["truth_z"])
                    if raw_item.get("truth_z") is not None
                    else None
                ),
            )
        except (KeyError, TypeError, ValueError):
            return None
