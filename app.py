from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from PySide6.QtWidgets import QApplication

from fake_data import FakeDataGenerator
from main_window import MainWindow
from replay_data_source import ReplayDataSource
from ros_bridge_adapter import MockRosLiveAdapter


DEFAULT_MOCK_ROS_IDS = ["UAV1", "UAV2", "UGV1"]


def _parse_platform_ids(raw: str) -> list[str]:
    ids = [item.strip() for item in raw.split(",") if item.strip()]
    return ids or list(DEFAULT_MOCK_ROS_IDS)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="205_nav_ui 启动入口")
    parser.add_argument(
        "--source",
        choices=("fake", "replay", "mock_ros"),
        default="fake",
        help="数据源类型：fake（默认）/ replay（文件回放）/ mock_ros（ROS2 mock实时）",
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
    return parser


def parse_cli_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.source == "replay" and args.replay_file is None:
        parser.error("--replay-file is required when --source replay")
    return args


def build_data_source_from_args(args: argparse.Namespace):
    if args.source == "fake":
        return FakeDataGenerator()

    if args.source == "mock_ros":
        return MockRosLiveAdapter(
            platform_ids=_parse_platform_ids(args.mock_ros_ids),
            interval_sec=max(0.02, float(args.mock_ros_interval)),
            seed=int(args.mock_ros_seed),
        )

    replay_path = Path(args.replay_file)
    replay_source = ReplayDataSource(FakeDataGenerator())
    if not replay_source.load_replay_jsonl(replay_path):
        raise ValueError(f"Failed to load replay file: {replay_path}")
    return replay_source


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
