from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import re
import time
from typing import Any, Callable, Literal, Protocol

from ros_topic_mapping import (
    RosTopicConvention,
    payload_from_ros_health_message,
    payload_from_ros_pose_message,
    topic_bindings_for_platform,
)


RosInboundKind = Literal["pose", "truth", "health"]


@dataclass(slots=True, frozen=True)
class RosInboundMessage:
    kind: RosInboundKind
    topic: str
    payload: dict[str, Any]


class RosIngressClient(Protocol):
    """ROS2 入站客户端接口：负责订阅并输出统一 topic/payload 事件。"""

    def connect(self) -> bool:
        ...

    def disconnect(self) -> None:
        ...

    def poll(self) -> list[RosInboundMessage]:
        ...

    def is_available(self) -> bool:
        ...

    def get_status_message(self) -> str:
        ...


class NullRos2Client(RosIngressClient):
    """ROS2 不可用时的占位客户端。"""

    def __init__(self, reason: str = "ROS2 runtime unavailable") -> None:
        self._reason = reason

    def connect(self) -> bool:
        return False

    def disconnect(self) -> None:
        return None

    def poll(self) -> list[RosInboundMessage]:
        return []

    def is_available(self) -> bool:
        return False

    def get_status_message(self) -> str:
        return self._reason


class InMemoryRos2Client(RosIngressClient):
    """内存队列版 ROS2 客户端（测试/骨架联调）。"""

    def __init__(self, *, initial_connected: bool = False) -> None:
        self._connected = initial_connected
        self._queue: deque[RosInboundMessage] = deque()

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False
        self._queue.clear()

    def poll(self) -> list[RosInboundMessage]:
        if not self._connected or not self._queue:
            return []
        events = list(self._queue)
        self._queue.clear()
        return events

    def is_available(self) -> bool:
        return True

    def get_status_message(self) -> str:
        return "in-memory ROS2 client"

    def push(self, kind: RosInboundKind, topic: str, payload: dict[str, Any]) -> None:
        self._queue.append(RosInboundMessage(kind=kind, topic=topic, payload=dict(payload)))


class RclpyRos2Client(RosIngressClient):
    """最小真实 ROS2 客户端：支持单/多平台 pose/truth/health 订阅闭环。"""

    def __init__(
        self,
        *,
        platform_id: str | None = None,
        platform_ids: list[str] | tuple[str, ...] | None = None,
        topic_convention: RosTopicConvention | None = None,
        node_name: str = "nav_ui_bridge",
        qos_depth: int = 10,
        auto_discovery: bool = True,
        discovery_interval_sec: float = 1.0,
        clock: Callable[[], float] | None = None,
        runtime_loader: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        resolved_platform_ids = self._resolve_platform_ids(platform_id, platform_ids)
        self.platform_ids = tuple(resolved_platform_ids)
        self.platform_id = self.platform_ids[0]
        self.topic_convention = topic_convention or RosTopicConvention()
        self.node_name = node_name
        self.qos_depth = max(1, int(qos_depth))
        self.auto_discovery = auto_discovery
        self.discovery_interval_sec = max(0.2, float(discovery_interval_sec))
        self._clock = clock or time.time
        self._queue: deque[RosInboundMessage] = deque()
        self._connected = False
        self._node: Any = None
        self._subscriptions: list[Any] = []
        self._subscription_keys: set[tuple[str, RosInboundKind]] = set()
        self._subscribed_platform_ids: set[str] = set()
        self._last_discovery_ts = 0.0
        self._runtime_error: str | None = None
        self._topic_patterns = {
            "pose": self._template_to_topic_regex(self.topic_convention.pose_topic),
            "truth": self._template_to_topic_regex(self.topic_convention.truth_topic),
            "health": self._template_to_topic_regex(self.topic_convention.health_topic),
        }

        self._runtime_loader = runtime_loader or _load_ros2_runtime
        self._runtime: dict[str, Any] | None = None
        try:
            self._runtime = self._runtime_loader()
        except Exception as exc:
            self._runtime_error = str(exc)

    def connect(self) -> bool:
        if self._runtime is None:
            return False
        if self._connected:
            return True

        rclpy = self._runtime["rclpy"]
        health_msg_type = self._runtime["String"]

        if not rclpy.ok():
            rclpy.init(args=None)
        self._node = rclpy.create_node(self.node_name)
        topic_types_by_name = self._load_topic_types_by_name()
        self._subscriptions = []
        self._subscription_keys.clear()
        self._subscribed_platform_ids.clear()
        for platform_id in self.platform_ids:
            self._bind_platform_channels(
                platform_id,
                topic_types_by_name=topic_types_by_name,
                health_msg_type=health_msg_type,
            )
        self._refresh_discovered_subscriptions(force=True)
        self._connected = True
        return True

    def disconnect(self) -> None:
        if self._node is not None:
            self._node.destroy_node()
        self._node = None
        self._subscriptions = []
        self._subscription_keys.clear()
        self._subscribed_platform_ids.clear()
        self._queue.clear()
        self._connected = False

    def poll(self) -> list[RosInboundMessage]:
        if not self._connected or self._runtime is None or self._node is None:
            return []
        rclpy = self._runtime["rclpy"]
        self._refresh_discovered_subscriptions(force=False)
        rclpy.spin_once(self._node, timeout_sec=0.0)
        if not self._queue:
            return []
        messages = list(self._queue)
        self._queue.clear()
        return messages

    def is_available(self) -> bool:
        return self._runtime is not None

    def get_status_message(self) -> str:
        if self._runtime_error:
            return f"ROS2 runtime unavailable: {self._runtime_error}"
        target_ids = sorted(self._subscribed_platform_ids or set(self.platform_ids))
        target = ",".join(target_ids) if target_ids else "-"
        discovery_suffix = " + auto-discovery" if self.auto_discovery else ""
        if self._connected:
            return f"subscribed pose/truth/health for [{target}]{discovery_suffix}"
        return f"ROS2 runtime ready for [{target}]{discovery_suffix}"

    def _on_pose(self, platform_id: str, topic: str, message: Any) -> None:
        payload = payload_from_ros_pose_message(
            message,
            default_timestamp=self._clock(),
            platform_type="UAV" if platform_id.upper().startswith("UAV") else "UGV",
            nav_state="TRACKING",
        )
        payload["platform_id"] = platform_id
        self._queue.append(RosInboundMessage(kind="pose", topic=topic, payload=payload))

    def _on_truth(self, platform_id: str, topic: str, message: Any) -> None:
        payload = payload_from_ros_pose_message(
            message,
            default_timestamp=self._clock(),
        )
        payload["platform_id"] = platform_id
        self._queue.append(RosInboundMessage(kind="truth", topic=topic, payload=payload))

    def _on_health(self, platform_id: str, topic: str, message: Any) -> None:
        payload = payload_from_ros_health_message(
            message,
            default_timestamp=self._clock(),
        )
        payload["platform_id"] = platform_id
        self._queue.append(RosInboundMessage(kind="health", topic=topic, payload=payload))

    def _bind_platform_channels(
        self,
        platform_id: str,
        *,
        topic_types_by_name: dict[str, list[str]],
        health_msg_type: Any,
    ) -> None:
        bindings = topic_bindings_for_platform(platform_id, convention=self.topic_convention)
        pose_topic_types = topic_types_by_name.get(bindings.pose_topic)
        truth_topic_types = topic_types_by_name.get(bindings.truth_topic)
        self._bind_subscription(
            platform_id=platform_id,
            kind="pose",
            topic=bindings.pose_topic,
            msg_type=self._select_pose_msg_type(pose_topic_types),
            callback=lambda msg, topic=bindings.pose_topic, pid=platform_id: self._on_pose(
                pid, topic, msg
            ),
        )
        self._bind_subscription(
            platform_id=platform_id,
            kind="truth",
            topic=bindings.truth_topic,
            msg_type=self._select_pose_msg_type(truth_topic_types),
            callback=lambda msg, topic=bindings.truth_topic, pid=platform_id: self._on_truth(
                pid, topic, msg
            ),
        )
        self._bind_subscription(
            platform_id=platform_id,
            kind="health",
            topic=bindings.health_topic,
            msg_type=health_msg_type,
            callback=lambda msg, topic=bindings.health_topic, pid=platform_id: self._on_health(
                pid, topic, msg
            ),
        )

    def _bind_subscription(
        self,
        *,
        platform_id: str,
        kind: RosInboundKind,
        topic: str,
        msg_type: Any,
        callback: Callable[[Any], None],
    ) -> None:
        if self._node is None:
            return
        key = (platform_id, kind)
        if key in self._subscription_keys:
            return
        subscription = self._node.create_subscription(
            msg_type,
            topic,
            callback,
            self.qos_depth,
        )
        self._subscriptions.append(subscription)
        self._subscription_keys.add(key)
        self._subscribed_platform_ids.add(platform_id)

    def _refresh_discovered_subscriptions(self, *, force: bool) -> None:
        if not self.auto_discovery or self._runtime is None or self._node is None:
            return
        now = self._clock()
        if not force and now - self._last_discovery_ts < self.discovery_interval_sec:
            return
        self._last_discovery_ts = now

        getter = getattr(self._node, "get_topic_names_and_types", None)
        if getter is None:
            return
        try:
            topic_rows = getter()
        except Exception:
            return

        health_msg_type = self._runtime["String"]

        for row in topic_rows:
            if not isinstance(row, (tuple, list)) or not row:
                continue
            topic = str(row[0])
            match_result = self._match_discovery_topic(topic)
            if match_result is None:
                continue
            kind, platform_id = match_result
            if kind == "health":
                callback = (
                    lambda msg, t=topic, pid=platform_id: self._on_health(pid, t, msg)
                )
                self._bind_subscription(
                    platform_id=platform_id,
                    kind=kind,
                    topic=topic,
                    msg_type=health_msg_type,
                    callback=callback,
                )
            elif kind == "pose":
                callback = (
                    lambda msg, t=topic, pid=platform_id: self._on_pose(pid, t, msg)
                )
                self._bind_subscription(
                    platform_id=platform_id,
                    kind=kind,
                    topic=topic,
                    msg_type=self._select_pose_msg_type(row[1] if len(row) > 1 else None),
                    callback=callback,
                )
            else:
                callback = (
                    lambda msg, t=topic, pid=platform_id: self._on_truth(pid, t, msg)
                )
                self._bind_subscription(
                    platform_id=platform_id,
                    kind=kind,
                    topic=topic,
                    msg_type=self._select_pose_msg_type(row[1] if len(row) > 1 else None),
                    callback=callback,
                )

    def _match_discovery_topic(self, topic: str) -> tuple[RosInboundKind, str] | None:
        for kind in ("pose", "truth", "health"):
            pattern = self._topic_patterns[kind]
            if pattern is None:
                continue
            matched = pattern.match(topic)
            if matched is None:
                continue
            platform_id = matched.group("platform_id").strip()
            if not platform_id:
                continue
            return kind, platform_id
        return None

    def _load_topic_types_by_name(self) -> dict[str, list[str]]:
        if self._node is None:
            return {}
        getter = getattr(self._node, "get_topic_names_and_types", None)
        if getter is None:
            return {}
        try:
            topic_rows = getter()
        except Exception:
            return {}
        mapping: dict[str, list[str]] = {}
        for row in topic_rows:
            if not isinstance(row, (tuple, list)) or not row:
                continue
            topic = str(row[0])
            type_names = row[1] if len(row) > 1 else []
            normalized_types = [str(type_name) for type_name in type_names]
            mapping[topic] = normalized_types
        return mapping

    def _select_pose_msg_type(self, topic_type_names: list[str] | tuple[str, ...] | None) -> Any:
        pose_stamped_type = self._runtime["PoseStamped"] if self._runtime is not None else None
        odometry_type = self._runtime.get("Odometry") if self._runtime is not None else None
        if not topic_type_names:
            return pose_stamped_type
        normalized = {str(name) for name in topic_type_names}
        if "nav_msgs/msg/Odometry" in normalized and odometry_type is not None:
            return odometry_type
        if "geometry_msgs/msg/PoseStamped" in normalized:
            return pose_stamped_type
        return pose_stamped_type

    @staticmethod
    def _template_to_topic_regex(template: str) -> re.Pattern[str] | None:
        marker = "{platform_id}"
        if marker not in template:
            return None
        escaped = re.escape(template).replace(re.escape(marker), r"(?P<platform_id>[^/]+)")
        return re.compile(rf"^{escaped}$")

    @staticmethod
    def _resolve_platform_ids(
        platform_id: str | None,
        platform_ids: list[str] | tuple[str, ...] | None,
    ) -> list[str]:
        candidates = list(platform_ids) if platform_ids else []
        if platform_id:
            candidates.insert(0, platform_id)
        normalized: list[str] = []
        for item in candidates:
            pid = str(item).strip()
            if not pid or pid in normalized:
                continue
            normalized.append(pid)
        if not normalized:
            normalized.append("UAV1")
        return normalized


def _load_ros2_runtime() -> dict[str, Any]:
    import rclpy
    from geometry_msgs.msg import PoseStamped
    try:
        from nav_msgs.msg import Odometry
    except Exception:
        Odometry = None
    from std_msgs.msg import String

    return {
        "rclpy": rclpy,
        "PoseStamped": PoseStamped,
        "Odometry": Odometry,
        "String": String,
    }
