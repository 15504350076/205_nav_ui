from __future__ import annotations

from data_adapter import AdapterStatus
from fusion_service import FusionConfig, PositionFusionService
from fused_data_source import FusedDataAdapter, FusedPlatformDataSource
from platform_state import PlatformState


def _state(
    x: float,
    y: float,
    z: float,
    *,
    timestamp: float,
    vx: float = 0.0,
    vy: float = 0.0,
    vz: float = 0.0,
    truth_x: float | None = None,
    truth_y: float | None = None,
    truth_z: float | None = None,
) -> PlatformState:
    return PlatformState(
        id="UAV1",
        type="UAV",
        x=x,
        y=y,
        z=z,
        vx=vx,
        vy=vy,
        vz=vz,
        speed=0.0,
        timestamp=timestamp,
        is_online=True,
        truth_x=truth_x,
        truth_y=truth_y,
        truth_z=truth_z,
    )


def test_position_fusion_service_blends_measurement_and_prediction() -> None:
    service = PositionFusionService(
        FusionConfig(measurement_weight=0.5, max_prediction_gap_sec=1.0, truth_weight=0.0)
    )
    first = service.fuse_state(_state(0.0, 0.0, 0.0, timestamp=0.0))
    second = service.fuse_state(_state(10.0, 0.0, 0.0, timestamp=1.0, vx=2.0))

    assert first.x == 0.0
    # prediction=2.0, measurement=10.0, 50/50 => 6.0
    assert second.x == 6.0


def test_position_fusion_service_can_use_truth_assist() -> None:
    service = PositionFusionService(
        FusionConfig(measurement_weight=1.0, max_prediction_gap_sec=1.0, truth_weight=0.25)
    )
    fused = service.fuse_state(
        _state(8.0, 4.0, 2.0, timestamp=1.0, truth_x=4.0, truth_y=0.0, truth_z=0.0)
    )
    assert fused.x == 7.0
    assert fused.y == 3.0
    assert fused.z == 1.5


def test_fused_platform_data_source_keeps_optional_source_methods() -> None:
    class Source:
        def __init__(self) -> None:
            self._frame = 0

        def get_initial_data(self) -> list[PlatformState]:
            return [_state(0.0, 0.0, 0.0, timestamp=0.0)]

        def get_next_frame(self) -> list[PlatformState]:
            self._frame += 1
            return [_state(1.0 + self._frame, 0.0, 0.0, timestamp=float(self._frame), vx=1.0)]

        def set_packet_loss_enabled(self, enabled: bool) -> None:
            self.enabled = enabled

    wrapped = FusedPlatformDataSource(Source())
    wrapped.set_packet_loss_enabled(True)
    first = wrapped.get_initial_data()
    second = wrapped.get_next_frame()
    assert first[0].id == "UAV1"
    assert second[0].x != 0.0


def test_fused_data_adapter_delegates_and_decorates_status() -> None:
    class Adapter:
        def __init__(self) -> None:
            self.connected = False
            self._frame = 0

        def connect(self) -> bool:
            self.connected = True
            return True

        def disconnect(self) -> None:
            self.connected = False

        def poll(self) -> list[PlatformState]:
            self._frame += 1
            return [_state(float(self._frame), 0.0, 0.0, timestamp=float(self._frame), vx=1.0)]

        def next_frame(self) -> list[PlatformState]:
            return self.poll()

        def is_live(self) -> bool:
            return True

        def get_status(self) -> AdapterStatus:
            return AdapterStatus(
                connected=self.connected,
                mode="live",
                source_name="Dummy",
                message="connected" if self.connected else "not connected",
            )

    wrapped = FusedDataAdapter(Adapter())
    assert wrapped.connect()
    _ = wrapped.poll()
    status = wrapped.get_status()
    assert status.connected is True
    assert status.source_name.endswith("+Fusion")
    assert "fusion(on" in status.message
