from ros_bridge_adapter import RosBridgeAdapter


def test_ros_bridge_adapter_mock_lifecycle() -> None:
    adapter = RosBridgeAdapter()
    assert adapter.get_status().connected is False

    assert adapter.connect()
    assert adapter.is_live() is True
    assert adapter.get_status().mode == "live"
    assert adapter.poll() == []

    adapter.disconnect()
    assert adapter.get_status().connected is False
