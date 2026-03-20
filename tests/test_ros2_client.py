from __future__ import annotations

from ros2_client import InMemoryRos2Client, NullRos2Client


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
