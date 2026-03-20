from ros2_client import InMemoryRos2Client
from ros_bridge_adapter import MockRosLiveAdapter, MockStreamConfig, RosBridgeAdapter


def test_ros_bridge_adapter_mock_lifecycle() -> None:
    adapter = RosBridgeAdapter()
    assert adapter.get_status().connected is False

    assert adapter.connect()
    assert adapter.is_live() is True
    assert adapter.get_status().mode == "live"
    assert adapter.poll() == []

    adapter.disconnect()
    assert adapter.get_status().connected is False


def test_ros_bridge_adapter_topic_mapping_callbacks() -> None:
    adapter = RosBridgeAdapter()
    assert adapter.connect()

    assert adapter.on_pose_topic(
        "/swarm/UAV9/nav/pose",
        {"x": 1.0, "y": 2.0, "z": 3.0, "timestamp": 1.0, "type": "UAV"},
    )
    assert adapter.on_truth_topic(
        "/swarm/UAV9/truth/pose",
        {"x": 1.2, "y": 2.2, "z": 3.2, "timestamp": 1.0},
    )
    assert adapter.on_health_topic(
        "/swarm/UAV9/health",
        {"is_online": False, "link_state": "LOST", "nav_state": "DEGRADED", "timestamp": 2.0},
    )

    updates = adapter.poll()
    assert len(updates) == 1
    state = updates[0]
    assert state.id == "UAV9"
    assert state.truth_x == 1.2 and state.truth_y == 2.2
    assert state.is_online is False
    assert state.link_state == "LOST"
    assert state.nav_state == "DEGRADED"


def test_ros_bridge_adapter_mock_stream_emits_by_interval() -> None:
    now = [0.0]
    adapter = RosBridgeAdapter(clock=lambda: now[0])
    adapter.enable_mock_stream(MockStreamConfig(platform_ids=["UAV1"], interval_sec=0.1))
    assert adapter.connect()

    assert adapter.poll() == []
    now[0] = 0.11
    updates = adapter.poll()
    assert len(updates) == 1
    assert updates[0].id == "UAV1"
    assert updates[0].truth_x is not None
    assert updates[0].nav_state == "TRACKING"


def test_mock_ros_live_adapter_ready_for_ui() -> None:
    adapter = MockRosLiveAdapter(platform_ids=["UAV1"], interval_sec=0.05)
    assert adapter.connect()
    assert adapter.get_status().source_name.startswith("ROS2Bridge")


def test_ros_bridge_adapter_with_ingress_client_closed_loop() -> None:
    ingress = InMemoryRos2Client()
    adapter = RosBridgeAdapter(ros_client=ingress)
    assert adapter.connect()
    ingress.push("pose", "/swarm/UAV1/nav/pose", {"x": 10.0, "y": 20.0, "z": 30.0, "timestamp": 1.0})
    ingress.push("truth", "/swarm/UAV1/truth/pose", {"x": 10.3, "y": 20.3, "z": 30.1, "timestamp": 1.0})
    ingress.push(
        "health",
        "/swarm/UAV1/health",
        {"is_online": True, "link_state": "OK", "nav_state": "TRACKING", "timestamp": 1.0},
    )

    updates = adapter.poll()
    assert len(updates) == 1
    state = updates[0]
    assert state.id == "UAV1"
    assert state.truth_x == 10.3 and state.truth_y == 20.3
    assert state.link_state == "OK"


def test_ros_bridge_adapter_with_unavailable_client() -> None:
    class UnavailableClient:
        def connect(self) -> bool:
            return False

        def disconnect(self) -> None:
            return None

        def poll(self) -> list:
            return []

        def is_available(self) -> bool:
            return False

        def get_status_message(self) -> str:
            return "ROS2 runtime unavailable"

    adapter = RosBridgeAdapter(ros_client=UnavailableClient())
    assert adapter.connect() is False
    status = adapter.get_status()
    assert status.connected is False
    assert "unavailable" in status.message
