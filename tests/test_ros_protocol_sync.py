"""单元测试模块：覆盖 ros_protocol_sync 相关逻辑与边界行为。"""

from __future__ import annotations

from pathlib import Path

from ros_protocol import ROS_PROTOCOL_FINGERPRINT, ROS_PROTOCOL_VERSION


def test_ros_protocol_doc_contains_version_and_fingerprint() -> None:
    content = Path("docs/ros2_min_protocol.md").read_text(encoding="utf-8")
    assert ROS_PROTOCOL_VERSION in content
    assert ROS_PROTOCOL_FINGERPRINT in content
    assert "协议变更门槛" in content
    assert "兼容旧数据源/旧录制文件" in content


def test_pr_template_contains_protocol_change_checklist() -> None:
    content = Path(".github/PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")
    assert "ROS2 协议变更检查" in content
    assert "已同步更新 `docs/ros2_min_protocol.md`" in content
    assert "已说明是否兼容旧数据源/旧录制文件" in content
