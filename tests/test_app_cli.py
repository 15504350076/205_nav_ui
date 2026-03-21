"""单元测试模块：覆盖 app_cli 相关逻辑与边界行为。"""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

import app
from app import build_data_source_from_args, parse_cli_args
from fake_data import FakeDataGenerator
from fused_data_source import FusedDataAdapter, FusedPlatformDataSource
from platform_state import PlatformState
from replay_data_source import ReplayDataSource
from ros_bridge_adapter import MockRosLiveAdapter, RosBridgeAdapter


def test_parse_cli_args_default_source() -> None:
    args = parse_cli_args([])
    assert args.source == "fake"
    assert args.replay_file is None
    assert args.enable_fusion is False


def test_parse_cli_args_ros2_platform_ids() -> None:
    args = parse_cli_args(["--source", "ros2", "--ros2-platform-ids", "UAV1,UGV1"])
    assert args.source == "ros2"
    assert args.ros2_platform_ids == "UAV1,UGV1"
    assert args.ros2_auto_discovery is True


def test_parse_cli_args_ros2_disable_auto_discovery() -> None:
    args = parse_cli_args(["--source", "ros2", "--ros2-no-auto-discovery"])
    assert args.ros2_auto_discovery is False


def test_parse_cli_args_ros2_convergence_options() -> None:
    args = parse_cli_args(
        [
            "--source",
            "ros2",
            "--ros2-min-messages-to-activate",
            "2",
            "--ros2-max-platforms",
            "50",
            "--ros2-max-updates-per-poll",
            "20",
        ]
    )
    assert args.ros2_min_messages_to_activate == 2
    assert args.ros2_max_platforms == 50
    assert args.ros2_max_updates_per_poll == 20


def test_parse_cli_args_fusion_options() -> None:
    args = parse_cli_args(
        [
            "--enable-fusion",
            "--fusion-measurement-weight",
            "0.6",
            "--fusion-max-gap-sec",
            "0.4",
            "--fusion-truth-weight",
            "0.2",
        ]
    )
    assert args.enable_fusion is True
    assert args.fusion_measurement_weight == 0.6
    assert args.fusion_max_gap_sec == 0.4
    assert args.fusion_truth_weight == 0.2


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
        enable_fusion=False,
        fusion_measurement_weight=0.8,
        fusion_max_gap_sec=1.0,
        fusion_truth_weight=0.0,
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
        enable_fusion=False,
        fusion_measurement_weight=0.8,
        fusion_max_gap_sec=1.0,
        fusion_truth_weight=0.0,
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
        enable_fusion=False,
        fusion_measurement_weight=0.8,
        fusion_max_gap_sec=1.0,
        fusion_truth_weight=0.0,
    )
    source = build_data_source_from_args(args)
    assert isinstance(source, ReplayDataSource)
    assert source.is_replay_mode


def test_build_data_source_ros2_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    class UnavailableClient:
        def __init__(self, **_: object) -> None:
            pass

        def is_available(self) -> bool:
            return False

        def get_status_message(self) -> str:
            return "ROS2 runtime unavailable: missing rclpy"

    monkeypatch.setattr(app, "RclpyRos2Client", UnavailableClient)
    args = Namespace(
        source="ros2",
        replay_file=None,
        mock_ros_ids="UAV1,UAV2,UGV1",
        mock_ros_interval=0.1,
        mock_ros_seed=205,
        ros2_platform_id="UAV1",
        ros2_platform_ids=None,
        ros2_node_name="nav_ui_bridge",
        ros2_auto_discovery=True,
        ros2_discovery_interval=1.0,
        ros2_min_messages_to_activate=1,
        ros2_max_platforms=120,
        ros2_max_updates_per_poll=80,
        ros2_pose_topic=None,
        ros2_truth_topic=None,
        ros2_health_topic=None,
        enable_fusion=False,
        fusion_measurement_weight=0.8,
        fusion_max_gap_sec=1.0,
        fusion_truth_weight=0.0,
    )
    with pytest.raises(ValueError):
        build_data_source_from_args(args)


def test_build_data_source_ros2_available(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class AvailableClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def is_available(self) -> bool:
            return True

        def get_status_message(self) -> str:
            return "ready"

        def connect(self) -> bool:
            return True

        def disconnect(self) -> None:
            return None

        def poll(self) -> list:
            return []

    monkeypatch.setattr(app, "RclpyRos2Client", AvailableClient)
    args = Namespace(
        source="ros2",
        replay_file=None,
        mock_ros_ids="UAV1,UAV2,UGV1",
        mock_ros_interval=0.1,
        mock_ros_seed=205,
        ros2_platform_id="UAV9",
        ros2_platform_ids="UAV9,UGV9",
        ros2_node_name="nav_ui_bridge",
        ros2_auto_discovery=True,
        ros2_discovery_interval=1.0,
        ros2_min_messages_to_activate=1,
        ros2_max_platforms=120,
        ros2_max_updates_per_poll=80,
        ros2_pose_topic="/swarm/{platform_id}/nav/pose",
        ros2_truth_topic="/swarm/{platform_id}/truth/pose",
        ros2_health_topic="/swarm/{platform_id}/health",
        enable_fusion=False,
        fusion_measurement_weight=0.8,
        fusion_max_gap_sec=1.0,
        fusion_truth_weight=0.0,
    )
    source = build_data_source_from_args(args)
    assert isinstance(source, RosBridgeAdapter)
    assert captured["platform_ids"] == ["UAV9", "UGV9"]
    assert captured["auto_discovery"] is True
    assert captured["discovery_interval_sec"] == 1.0
    assert captured["max_discovered_platforms"] == 120


def test_build_data_source_fake_with_fusion_enabled() -> None:
    args = Namespace(
        source="fake",
        replay_file=None,
        mock_ros_ids="UAV1,UAV2,UGV1",
        mock_ros_interval=0.1,
        mock_ros_seed=205,
        enable_fusion=True,
        fusion_measurement_weight=0.6,
        fusion_max_gap_sec=0.5,
        fusion_truth_weight=0.0,
    )
    source = build_data_source_from_args(args)
    assert isinstance(source, FusedPlatformDataSource)
    assert isinstance(source.source, FakeDataGenerator)


def test_build_data_source_ros2_with_fusion_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    class AvailableClient:
        def __init__(self, **_: object) -> None:
            pass

        def is_available(self) -> bool:
            return True

        def get_status_message(self) -> str:
            return "ready"

        def connect(self) -> bool:
            return True

        def disconnect(self) -> None:
            return None

        def poll(self) -> list:
            return []

        def get_runtime_metrics(self) -> dict[str, int]:
            return {}

    monkeypatch.setattr(app, "RclpyRos2Client", AvailableClient)
    args = Namespace(
        source="ros2",
        replay_file=None,
        mock_ros_ids="UAV1,UAV2,UGV1",
        mock_ros_interval=0.1,
        mock_ros_seed=205,
        ros2_platform_id="UAV1",
        ros2_platform_ids=None,
        ros2_node_name="nav_ui_bridge",
        ros2_auto_discovery=True,
        ros2_discovery_interval=1.0,
        ros2_min_messages_to_activate=1,
        ros2_max_platforms=120,
        ros2_max_updates_per_poll=80,
        ros2_pose_topic=None,
        ros2_truth_topic=None,
        ros2_health_topic=None,
        enable_fusion=True,
        fusion_measurement_weight=0.7,
        fusion_max_gap_sec=1.0,
        fusion_truth_weight=0.0,
    )
    source = build_data_source_from_args(args)
    assert isinstance(source, FusedDataAdapter)
