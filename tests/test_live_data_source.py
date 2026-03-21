"""单元测试模块：覆盖 live_data_source 相关逻辑与边界行为。"""

from live_data_source import LiveDataSourceAdapter
from platform_state import PlatformState


class StubLiveSource:
    def __init__(self) -> None:
        self.called = 0

    def get_initial_data(self) -> list[PlatformState]:
        return [PlatformState(id="U1", type="UAV", x=0.0, y=0.0, z=0.0, timestamp=0.0)]

    def get_next_frame(self) -> list[PlatformState]:
        self.called += 1
        return [
            PlatformState(
                id="U1",
                type="UAV",
                x=float(self.called),
                y=0.0,
                z=0.0,
                timestamp=float(self.called),
            )
        ]


def test_live_adapter_connect_poll_disconnect() -> None:
    adapter = LiveDataSourceAdapter(StubLiveSource(), source_name="stub")

    assert adapter.get_status().connected is False
    assert adapter.connect()
    first = adapter.poll()
    second = adapter.next_frame()
    adapter.disconnect()

    assert first and first[0].timestamp == 0.0
    assert second and second[0].timestamp == 1.0
    assert adapter.poll() == []


def test_live_adapter_status_fields() -> None:
    adapter = LiveDataSourceAdapter(StubLiveSource(), source_name="demo")
    status = adapter.get_status()
    assert status.mode == "disconnected"
    assert status.source_name == "demo"
    adapter.connect()
    status = adapter.get_status()
    assert status.mode == "live"
    assert status.connected is True
