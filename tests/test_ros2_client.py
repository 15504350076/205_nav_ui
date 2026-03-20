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
