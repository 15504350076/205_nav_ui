from __future__ import annotations

from collections import deque
from dataclasses import dataclass
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
    """最小真实 ROS2 客户端：单平台 pose/truth/health 订阅闭环。"""

    def __init__(
        self,
        *,
        platform_id: str,
        topic_convention: RosTopicConvention | None = None,
        node_name: str = "nav_ui_bridge",
        qos_depth: int = 10,
        clock: Callable[[], float] | None = None,
        runtime_loader: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.platform_id = platform_id
        self.topic_convention = topic_convention or RosTopicConvention()
        self.node_name = node_name
        self.qos_depth = max(1, int(qos_depth))
        self._clock = clock or time.time
        self._queue: deque[RosInboundMessage] = deque()
        self._connected = False
        self._node: Any = None
        self._subscriptions: list[Any] = []
        self._runtime_error: str | None = None

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
        pose_msg_type = self._runtime["PoseStamped"]
        health_msg_type = self._runtime["String"]

        if not rclpy.ok():
            rclpy.init(args=None)
        self._node = rclpy.create_node(self.node_name)
        bindings = topic_bindings_for_platform(self.platform_id, convention=self.topic_convention)
        self._subscriptions = [
            self._node.create_subscription(
                pose_msg_type,
                bindings.pose_topic,
                lambda msg, topic=bindings.pose_topic: self._on_pose(topic, msg),
                self.qos_depth,
            ),
            self._node.create_subscription(
                pose_msg_type,
                bindings.truth_topic,
                lambda msg, topic=bindings.truth_topic: self._on_truth(topic, msg),
                self.qos_depth,
            ),
            self._node.create_subscription(
                health_msg_type,
                bindings.health_topic,
                lambda msg, topic=bindings.health_topic: self._on_health(topic, msg),
                self.qos_depth,
            ),
        ]
        self._connected = True
        return True

    def disconnect(self) -> None:
        if self._node is not None:
            self._node.destroy_node()
        self._node = None
        self._subscriptions = []
        self._queue.clear()
        self._connected = False

    def poll(self) -> list[RosInboundMessage]:
        if not self._connected or self._runtime is None or self._node is None:
            return []
        rclpy = self._runtime["rclpy"]
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
        if self._connected:
            return f"subscribed pose/truth/health for {self.platform_id}"
        return f"ROS2 runtime ready for {self.platform_id}"

    def _on_pose(self, topic: str, message: Any) -> None:
        payload = payload_from_ros_pose_message(
            message,
            default_timestamp=self._clock(),
            platform_type="UAV" if self.platform_id.upper().startswith("UAV") else "UGV",
            nav_state="TRACKING",
        )
        self._queue.append(RosInboundMessage(kind="pose", topic=topic, payload=payload))

    def _on_truth(self, topic: str, message: Any) -> None:
        payload = payload_from_ros_pose_message(
            message,
            default_timestamp=self._clock(),
        )
        self._queue.append(RosInboundMessage(kind="truth", topic=topic, payload=payload))

    def _on_health(self, topic: str, message: Any) -> None:
        payload = payload_from_ros_health_message(
            message,
            default_timestamp=self._clock(),
        )
        self._queue.append(RosInboundMessage(kind="health", topic=topic, payload=payload))


def _load_ros2_runtime() -> dict[str, Any]:
    import rclpy
    from geometry_msgs.msg import PoseStamped
    from std_msgs.msg import String

    return {
        "rclpy": rclpy,
        "PoseStamped": PoseStamped,
        "String": String,
    }
