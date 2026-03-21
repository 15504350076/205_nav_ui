"""单元测试模块：覆盖 ros2_client 相关逻辑与边界行为。"""

from __future__ import annotations

from ros2_client import InMemoryRos2Client, NullRos2Client, RclpyRos2Client


def test_in_memory_ros2_client_push_and_poll() -> None:
    client = InMemoryRos2Client()
    assert client.connect()
    client.push("pose", "/swarm/UAV1/nav/pose", {"x": 1.0, "y": 2.0, "z": 3.0, "timestamp": 1.0})
    events = client.poll()
    assert len(events) == 1
    assert events[0].kind == "pose"
    assert events[0].payload["x"] == 1.0


def test_null_ros2_client_unavailable() -> None:
    client = NullRos2Client("missing runtime")
    assert client.is_available() is False
    assert client.connect() is False
    assert "missing runtime" in client.get_status_message()


def test_rclpy_client_multi_platform_subscriptions_and_poll() -> None:
    class FakePoseStamped:
        class Header:
            class Stamp:
                sec = 1
                nanosec = 0

            stamp = Stamp()

        class Pose:
            class Position:
                x = 10.0
                y = 20.0
                z = 30.0

            position = Position()

        header = Header()
        pose = Pose()

    class FakeString:
        data = '{"is_online": true, "link_state": "OK", "nav_state": "TRACKING"}'

    class FakeNode:
        def __init__(self) -> None:
            self.subscriptions: list[tuple[str, object]] = []
            self.destroyed = False

        def create_subscription(self, msg_type, topic: str, callback, qos_depth: int):
            del qos_depth
            self.subscriptions.append((topic, callback))
            return (msg_type, topic, callback)

        def destroy_node(self) -> None:
            self.destroyed = True

    class FakeRclpy:
        def __init__(self) -> None:
            self.inited = False
            self.node = FakeNode()

        def ok(self) -> bool:
            return self.inited

        def init(self, args=None) -> None:
            del args
            self.inited = True

        def create_node(self, node_name: str) -> FakeNode:
            del node_name
            return self.node

        def spin_once(self, node: FakeNode, timeout_sec: float) -> None:
            del timeout_sec
            for topic, callback in node.subscriptions:
                if topic.endswith("/health"):
                    callback(FakeString())
                else:
                    callback(FakePoseStamped())

    fake_rclpy = FakeRclpy()

    def runtime_loader():
        return {
            "rclpy": fake_rclpy,
            "PoseStamped": object(),
            "String": object(),
        }

    client = RclpyRos2Client(
        platform_ids=["UAV1", "UGV1"],
        runtime_loader=runtime_loader,
    )
    assert client.connect()
    assert len(fake_rclpy.node.subscriptions) == 6
    events = client.poll()
    assert len(events) == 6
    ids = sorted({event.payload.get("platform_id") for event in events})
    assert ids == ["UAV1", "UGV1"]
    client.disconnect()
    assert fake_rclpy.node.destroyed is True


def test_rclpy_client_auto_discovers_new_platform_topics() -> None:
    class FakePoseStamped:
        class Header:
            class Stamp:
                sec = 2
                nanosec = 0

            stamp = Stamp()

        class Pose:
            class Position:
                x = 1.0
                y = 2.0
                z = 3.0

            position = Position()

        header = Header()
        pose = Pose()

    class FakeString:
        data = '{"is_online": true, "link_state": "OK", "nav_state": "TRACKING"}'

    class FakeNode:
        def __init__(self) -> None:
            self.subscriptions: list[tuple[str, object]] = []

        def create_subscription(self, msg_type, topic: str, callback, qos_depth: int):
            del msg_type, qos_depth
            self.subscriptions.append((topic, callback))
            return topic

        def get_topic_names_and_types(self):
            return [
                ("/swarm/UGV2/nav/pose", ["geometry_msgs/msg/PoseStamped"]),
                ("/swarm/UGV2/truth/pose", ["geometry_msgs/msg/PoseStamped"]),
                ("/swarm/UGV2/health", ["std_msgs/msg/String"]),
            ]

        def destroy_node(self) -> None:
            return None

    class FakeRclpy:
        def __init__(self) -> None:
            self.inited = False
            self.node = FakeNode()

        def ok(self) -> bool:
            return self.inited

        def init(self, args=None) -> None:
            del args
            self.inited = True

        def create_node(self, node_name: str) -> FakeNode:
            del node_name
            return self.node

        def spin_once(self, node: FakeNode, timeout_sec: float) -> None:
            del timeout_sec
            for topic, callback in node.subscriptions:
                if topic.endswith("/health"):
                    callback(FakeString())
                else:
                    callback(FakePoseStamped())

    fake_rclpy = FakeRclpy()

    def runtime_loader():
        return {"rclpy": fake_rclpy, "PoseStamped": object(), "String": object()}

    client = RclpyRos2Client(
        platform_ids=["UAV1"],
        auto_discovery=True,
        runtime_loader=runtime_loader,
    )
    assert client.connect()
    topics = [topic for topic, _ in fake_rclpy.node.subscriptions]
    assert "/swarm/UGV2/nav/pose" in topics
    events = client.poll()
    discovered_ids = {event.payload.get("platform_id") for event in events}
    assert "UGV2" in discovered_ids


def test_rclpy_client_topic_type_mismatch_counted() -> None:
    class FakeNode:
        def __init__(self) -> None:
            self.subscriptions: list[tuple[str, object]] = []

        def create_subscription(self, msg_type, topic: str, callback, qos_depth: int):
            del msg_type, callback, qos_depth
            self.subscriptions.append((topic, None))
            return topic

        def get_topic_names_and_types(self):
            return [("/swarm/UAV1/nav/pose", ["custom_msgs/msg/Foo"])]

        def destroy_node(self) -> None:
            return None

    class FakeRclpy:
        def __init__(self) -> None:
            self.node = FakeNode()

        def ok(self) -> bool:
            return True

        def init(self, args=None) -> None:
            del args
            return None

        def create_node(self, node_name: str) -> FakeNode:
            del node_name
            return self.node

        def spin_once(self, node: FakeNode, timeout_sec: float) -> None:
            del node, timeout_sec
            return None

    def runtime_loader():
        return {"rclpy": FakeRclpy(), "PoseStamped": object(), "String": object()}

    client = RclpyRos2Client(platform_ids=["UAV1"], runtime_loader=runtime_loader)
    assert client.connect()
    metrics = client.get_runtime_metrics()
    assert metrics["unsupported_topic_type"] >= 1


def test_rclpy_client_discovery_platform_limit_protection() -> None:
    class FakeNode:
        def __init__(self) -> None:
            self.subscriptions: list[tuple[str, object]] = []

        def create_subscription(self, msg_type, topic: str, callback, qos_depth: int):
            del msg_type, callback, qos_depth
            self.subscriptions.append((topic, None))
            return topic

        def get_topic_names_and_types(self):
            return [
                ("/swarm/UAV1/nav/pose", ["geometry_msgs/msg/PoseStamped"]),
                ("/swarm/UAV1/truth/pose", ["geometry_msgs/msg/PoseStamped"]),
                ("/swarm/UAV1/health", ["std_msgs/msg/String"]),
                ("/swarm/UAV2/nav/pose", ["geometry_msgs/msg/PoseStamped"]),
                ("/swarm/UAV2/truth/pose", ["geometry_msgs/msg/PoseStamped"]),
                ("/swarm/UAV2/health", ["std_msgs/msg/String"]),
            ]

        def destroy_node(self) -> None:
            return None

    class FakeRclpy:
        def __init__(self) -> None:
            self.node = FakeNode()

        def ok(self) -> bool:
            return True

        def init(self, args=None) -> None:
            del args
            return None

        def create_node(self, node_name: str) -> FakeNode:
            del node_name
            return self.node

        def spin_once(self, node: FakeNode, timeout_sec: float) -> None:
            del node, timeout_sec
            return None

    def runtime_loader():
        return {"rclpy": FakeRclpy(), "PoseStamped": object(), "String": object()}

    client = RclpyRos2Client(
        platform_ids=[],
        auto_discovery=True,
        max_discovered_platforms=1,
        runtime_loader=runtime_loader,
    )
    assert client.connect()
    metrics = client.get_runtime_metrics()
    assert metrics["discovery_rejected_platform"] >= 1


def test_rclpy_client_discovery_flap_does_not_duplicate_subscriptions() -> None:
    now = [0.0]

    class FakeNode:
        def __init__(self) -> None:
            self.subscriptions: list[tuple[str, object]] = []
            self.query_count = 0

        def create_subscription(self, msg_type, topic: str, callback, qos_depth: int):
            del msg_type, callback, qos_depth
            self.subscriptions.append((topic, None))
            return topic

        def get_topic_names_and_types(self):
            self.query_count += 1
            if self.query_count % 2 == 1:
                return [
                    ("/swarm/UAV9/nav/pose", ["geometry_msgs/msg/PoseStamped"]),
                    ("/swarm/UAV9/truth/pose", ["geometry_msgs/msg/PoseStamped"]),
                    ("/swarm/UAV9/health", ["std_msgs/msg/String"]),
                ]
            return []

        def destroy_node(self) -> None:
            return None

    class FakeRclpy:
        def __init__(self) -> None:
            self.node = FakeNode()

        def ok(self) -> bool:
            return True

        def init(self, args=None) -> None:
            del args
            return None

        def create_node(self, node_name: str) -> FakeNode:
            del node_name
            return self.node

        def spin_once(self, node: FakeNode, timeout_sec: float) -> None:
            del node, timeout_sec
            return None

    def runtime_loader():
        return {"rclpy": FakeRclpy(), "PoseStamped": object(), "String": object()}

    client = RclpyRos2Client(
        platform_ids=[],
        auto_discovery=True,
        discovery_interval_sec=0.2,
        clock=lambda: now[0],
        runtime_loader=runtime_loader,
    )
    assert client.connect()
    now[0] = 1.0
    _ = client.poll()
    now[0] = 2.0
    _ = client.poll()
    runtime = client._runtime["rclpy"]  # type: ignore[index]
    assert len(runtime.node.subscriptions) == 3


def test_rclpy_client_topics_exist_but_no_messages() -> None:
    class FakeNode:
        def create_subscription(self, msg_type, topic: str, callback, qos_depth: int):
            del msg_type, topic, callback, qos_depth
            return object()

        def get_topic_names_and_types(self):
            return [
                ("/swarm/UAV1/nav/pose", ["geometry_msgs/msg/PoseStamped"]),
                ("/swarm/UAV1/truth/pose", ["geometry_msgs/msg/PoseStamped"]),
                ("/swarm/UAV1/health", ["std_msgs/msg/String"]),
            ]

        def destroy_node(self) -> None:
            return None

    class FakeRclpy:
        def __init__(self) -> None:
            self.node = FakeNode()

        def ok(self) -> bool:
            return True

        def init(self, args=None) -> None:
            del args
            return None

        def create_node(self, node_name: str) -> FakeNode:
            del node_name
            return self.node

        def spin_once(self, node: FakeNode, timeout_sec: float) -> None:
            del node, timeout_sec
            return None

    def runtime_loader():
        return {"rclpy": FakeRclpy(), "PoseStamped": object(), "String": object()}

    client = RclpyRos2Client(platform_ids=["UAV1"], runtime_loader=runtime_loader)
    assert client.connect()
    _ = client.poll()
    metrics = client.get_runtime_metrics()
    assert metrics["raw_total"] == 0
    assert metrics["raw_last_pose_age_sec"] == -1.0
