from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from app import build_data_source_from_args, parse_cli_args
from fake_data import FakeDataGenerator
from platform_state import PlatformState
from replay_data_source import ReplayDataSource
from ros_bridge_adapter import MockRosLiveAdapter


def test_parse_cli_args_default_source() -> None:
    args = parse_cli_args([])
    assert args.source == "fake"
    assert args.replay_file is None


def test_parse_cli_args_replay_requires_file() -> None:
    with pytest.raises(SystemExit):
        parse_cli_args(["--source", "replay"])


def test_build_data_source_fake() -> None:
    args = Namespace(
        source="fake",
        replay_file=None,
        mock_ros_ids="UAV1,UAV2,UGV1",
        mock_ros_interval=0.1,
        mock_ros_seed=205,
    )
    source = build_data_source_from_args(args)
    assert isinstance(source, FakeDataGenerator)


def test_build_data_source_mock_ros() -> None:
    args = Namespace(
        source="mock_ros",
        replay_file=None,
        mock_ros_ids="UAV9,UGV9",
        mock_ros_interval=0.05,
        mock_ros_seed=42,
    )
    source = build_data_source_from_args(args)
    assert isinstance(source, MockRosLiveAdapter)


def test_build_data_source_replay(tmp_path: Path) -> None:
    replay_file = tmp_path / "sample.jsonl"
    frame = [PlatformState(id="U1", type="UAV", x=1.0, y=2.0, z=3.0, timestamp=1.0).to_dict()]
    replay_file.write_text(json.dumps(frame, ensure_ascii=False) + "\n", encoding="utf-8")
    args = Namespace(
        source="replay",
        replay_file=replay_file,
        mock_ros_ids="UAV1,UAV2,UGV1",
        mock_ros_interval=0.1,
        mock_ros_seed=205,
    )
    source = build_data_source_from_args(args)
    assert isinstance(source, ReplayDataSource)
    assert source.is_replay_mode

