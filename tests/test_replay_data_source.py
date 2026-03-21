"""单元测试模块：覆盖 replay_data_source 相关逻辑与边界行为。"""

from pathlib import Path

from platform_state import PlatformState
from replay_data_source import ReplayDataSource


class SequenceDataSource:
    def __init__(self, frames: list[list[PlatformState]]) -> None:
        self.frames = [list(item) for item in frames]
        self.index = 0

    def get_initial_data(self) -> list[PlatformState]:
        return []

    def get_next_frame(self) -> list[PlatformState]:
        if self.index >= len(self.frames):
            return []
        frame = self.frames[self.index]
        self.index += 1
        return list(frame)


def make_state(platform_id: str, timestamp: float) -> PlatformState:
    return PlatformState(
        id=platform_id,
        type="UAV",
        x=timestamp,
        y=0.0,
        z=0.0,
        timestamp=timestamp,
        is_online=True,
    )


def test_replay_data_source_record_save_and_load(tmp_path: Path) -> None:
    frames = [[make_state("U1", 0.1)], [make_state("U1", 0.2)]]
    replay = ReplayDataSource(SequenceDataSource(frames))

    assert replay.start_recording()
    replay.get_next_frame()
    replay.get_next_frame()
    recorded = replay.stop_recording()
    assert len(recorded) == 2

    path = tmp_path / "recordings" / "sample.jsonl"
    assert replay.save_recording_jsonl(path)
    assert path.exists()

    playback = ReplayDataSource(SequenceDataSource([]))
    assert playback.load_replay_jsonl(path)
    assert playback.is_replay_mode
    assert playback.replay_total_frames == 2
    assert playback.replay_file_path == path

    first = playback.get_next_frame()
    second = playback.get_next_frame()
    third = playback.get_next_frame()
    assert first[0].timestamp == 0.1
    assert second[0].timestamp == 0.2
    assert third == []


def test_replay_cursor_controls(tmp_path: Path) -> None:
    frames = [[make_state("U1", 1.0)], [make_state("U1", 2.0)]]
    recorder = ReplayDataSource(SequenceDataSource(frames))
    recorder.start_recording()
    recorder.get_next_frame()
    recorder.get_next_frame()
    recorder.stop_recording()
    path = tmp_path / "recordings" / "cursor.jsonl"
    assert recorder.save_recording_jsonl(path)

    replay = ReplayDataSource(SequenceDataSource([]))
    assert replay.load_replay_jsonl(path)
    replay.get_next_frame()
    replay.get_next_frame()
    assert replay.replay_frame_index == 2
    assert replay.step_back_replay_cursor()
    assert replay.replay_frame_index == 0
    replay.replay_frame_index = 999
    assert replay.replay_frame_index == replay.replay_total_frames
    replay.exit_replay_mode()
    assert not replay.is_replay_mode


def test_replay_data_source_rejects_invalid_replay_file(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text("{bad json", encoding="utf-8")

    replay = ReplayDataSource(SequenceDataSource([]))
    assert not replay.load_replay_jsonl(path)


def test_replay_data_source_status_and_lifecycle() -> None:
    replay = ReplayDataSource(SequenceDataSource([]))
    status = replay.get_status()
    assert status.mode in {"live", "disconnected"}
    assert replay.is_live() is True
    replay.disconnect()
    assert replay.get_status().connected is False
    assert replay.connect() is True
