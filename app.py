from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from PySide6.QtWidgets import QApplication

from fake_data import FakeDataGenerator
from fusion_service import FusionConfig
from fused_data_source import FusedDataAdapter, FusedPlatformDataSource
from main_window import MainWindow
from replay_data_source import ReplayDataSource
from ros2_client import RclpyRos2Client
from ros_bridge_adapter import MockRosLiveAdapter, RosBridgeAdapter
from ros_topic_mapping import RosTopicConvention


DEFAULT_MOCK_ROS_IDS = ["UAV1", "UAV2", "UGV1"]


def _parse_platform_ids(raw: str, default_ids: list[str]) -> list[str]:
    ids = [item.strip() for item in raw.split(",") if item.strip()]
    return ids or list(default_ids)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="205_nav_ui 启动入口")
    parser.add_argument(
        "--source",
        choices=("fake", "replay", "mock_ros", "ros2"),
        default="fake",
        help="数据源类型：fake（默认）/ replay（文件回放）/ mock_ros（ROS2 mock实时）/ ros2（真实ROS2）",
    )
    parser.add_argument(
        "--replay-file",
        type=Path,
        default=None,
        help="当 --source replay 时使用的 JSONL 回放文件路径",
    )
    parser.add_argument(
        "--mock-ros-ids",
        default=",".join(DEFAULT_MOCK_ROS_IDS),
        help="mock_ros 平台ID列表，逗号分隔，例如 UAV1,UAV2,UGV1",
    )
    parser.add_argument(
        "--mock-ros-interval",
        type=float,
        default=0.1,
        help="mock_ros 推流周期（秒），默认 0.1",
    )
    parser.add_argument(
        "--mock-ros-seed",
        type=int,
        default=205,
        help="mock_ros 随机种子，默认 205",
    )
    parser.add_argument(
        "--ros2-platform-id",
        default="UAV1",
        help="ros2 模式默认平台ID（兼容单平台参数）",
    )
    parser.add_argument(
        "--ros2-platform-ids",
        default=None,
        help="ros2 模式平台ID列表，逗号分隔；填写后优先于 --ros2-platform-id",
    )
    parser.add_argument(
        "--ros2-node-name",
        default="nav_ui_bridge",
        help="ros2 模式节点名",
    )
    parser.add_argument(
        "--ros2-auto-discovery",
        action="store_true",
        default=True,
        help="启用 ROS2 topic 自动发现（默认开启）",
    )
    parser.add_argument(
        "--ros2-no-auto-discovery",
        dest="ros2_auto_discovery",
        action="store_false",
        help="关闭 ROS2 topic 自动发现，仅订阅显式平台列表",
    )
    parser.add_argument(
        "--ros2-discovery-interval",
        type=float,
        default=1.0,
        help="自动发现扫描周期（秒），默认 1.0",
    )
    parser.add_argument(
        "--ros2-min-messages-to-activate",
        type=int,
        default=1,
        help="平台最小激活消息数（达到后才推送到 UI），默认 1",
    )
    parser.add_argument(
        "--ros2-max-platforms",
        type=int,
        default=120,
        help="ROS2 接入平台上限保护，默认 120",
    )
    parser.add_argument(
        "--ros2-max-updates-per-poll",
        type=int,
        default=80,
        help="单次 poll 推送给 UI 的平台更新上限，默认 80",
    )
    parser.add_argument(
        "--ros2-pose-topic",
        default=None,
        help="ros2 估计位姿 topic（可选覆盖，支持模板或固定值）",
    )
    parser.add_argument(
        "--ros2-truth-topic",
        default=None,
        help="ros2 真值位姿 topic（可选覆盖，支持模板或固定值）",
    )
    parser.add_argument(
        "--ros2-health-topic",
        default=None,
        help="ros2 健康状态 topic（可选覆盖，支持模板或固定值）",
    )
    parser.add_argument(
        "--enable-fusion",
        action="store_true",
        default=False,
        help="启用位置融合算法模块（默认关闭）",
    )
    parser.add_argument(
        "--fusion-measurement-weight",
        type=float,
        default=0.8,
        help="融合参数：测量权重 0~1，越大越信任输入位置，默认 0.8",
    )
    parser.add_argument(
        "--fusion-max-gap-sec",
        type=float,
        default=1.0,
        help="融合参数：预测允许的最大时间间隔（秒），默认 1.0",
    )
    parser.add_argument(
        "--fusion-truth-weight",
        type=float,
        default=0.0,
        help="融合参数：真值辅助权重 0~1（联调用，可保持 0），默认 0.0",
    )
    return parser


def parse_cli_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.source == "replay" and args.replay_file is None:
        parser.error("--replay-file is required when --source replay")
    return args


def _build_fusion_config(args: argparse.Namespace) -> FusionConfig:
    return FusionConfig(
        measurement_weight=float(getattr(args, "fusion_measurement_weight", 0.8)),
        max_prediction_gap_sec=float(getattr(args, "fusion_max_gap_sec", 1.0)),
        truth_weight=float(getattr(args, "fusion_truth_weight", 0.0)),
    )


def _maybe_wrap_with_fusion(source: object, args: argparse.Namespace):
    if not bool(getattr(args, "enable_fusion", False)):
        return source
    fusion_config = _build_fusion_config(args)
    if all(hasattr(source, name) for name in ("get_initial_data", "get_next_frame")):
        return FusedPlatformDataSource(source, fusion_config=fusion_config)  # type: ignore[arg-type]
    if all(
        hasattr(source, name)
        for name in ("connect", "disconnect", "poll", "next_frame", "is_live", "get_status")
    ):
        return FusedDataAdapter(source, fusion_config=fusion_config)  # type: ignore[arg-type]
    return source


def build_data_source_from_args(args: argparse.Namespace):
    if args.source == "fake":
        return _maybe_wrap_with_fusion(FakeDataGenerator(), args)

    if args.source == "mock_ros":
        source = MockRosLiveAdapter(
            platform_ids=_parse_platform_ids(args.mock_ros_ids, DEFAULT_MOCK_ROS_IDS),
            interval_sec=max(0.02, float(args.mock_ros_interval)),
            seed=int(args.mock_ros_seed),
        )
        return _maybe_wrap_with_fusion(source, args)

    if args.source == "ros2":
        ros2_platform_ids = (
            _parse_platform_ids(args.ros2_platform_ids, [str(args.ros2_platform_id)])
            if args.ros2_platform_ids is not None
            else [str(args.ros2_platform_id)]
        )
        default_convention = RosTopicConvention()
        topic_convention = RosTopicConvention(
            pose_topic=args.ros2_pose_topic or default_convention.pose_topic,
            truth_topic=args.ros2_truth_topic or default_convention.truth_topic,
            health_topic=args.ros2_health_topic or default_convention.health_topic,
        )
        ros_client = RclpyRos2Client(
            platform_ids=ros2_platform_ids,
            topic_convention=topic_convention,
            node_name=str(args.ros2_node_name),
            auto_discovery=bool(args.ros2_auto_discovery),
            discovery_interval_sec=float(args.ros2_discovery_interval),
            max_discovered_platforms=int(args.ros2_max_platforms),
        )
        if not ros_client.is_available():
            raise ValueError(
                f"{ros_client.get_status_message()}。可先使用 --source mock_ros 继续联调。"
            )
        source = RosBridgeAdapter(
            source_name=f"ROS2Bridge(Live:{','.join(ros2_platform_ids)})",
            topic_convention=topic_convention,
            ros_client=ros_client,
            min_messages_to_activate=int(args.ros2_min_messages_to_activate),
            max_platforms=int(args.ros2_max_platforms),
            max_updates_per_poll=int(args.ros2_max_updates_per_poll),
        )
        return _maybe_wrap_with_fusion(source, args)

    replay_path = Path(args.replay_file)
    replay_source = ReplayDataSource(FakeDataGenerator())
    if not replay_source.load_replay_jsonl(replay_path):
        raise ValueError(f"Failed to load replay file: {replay_path}")
    return _maybe_wrap_with_fusion(replay_source, args)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_cli_args(argv)
    try:
        data_source = build_data_source_from_args(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    app = QApplication([sys.argv[0]])
    window = MainWindow(data_source=data_source)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
