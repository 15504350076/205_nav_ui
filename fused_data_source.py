from __future__ import annotations

from data_adapter import AdapterStatus, DataAdapter
from data_source import PlatformDataSource
from fusion_service import FusionConfig, PositionFusionService
from platform_state import PlatformState


class FusedPlatformDataSource(PlatformDataSource):
    """在 PlatformDataSource 之上叠加位置融合能力。"""

    def __init__(
        self,
        source: PlatformDataSource,
        *,
        fusion_config: FusionConfig | None = None,
    ) -> None:
        self.source = source
        self.fusion_service = PositionFusionService(fusion_config)

    def __getattr__(self, name: str):
        return getattr(self.source, name)

    def get_initial_data(self) -> list[PlatformState]:
        self.fusion_service.reset()
        return self.fusion_service.fuse_frame(self.source.get_initial_data())

    def get_next_frame(self) -> list[PlatformState]:
        return self.fusion_service.fuse_frame(self.source.get_next_frame())


class FusedDataAdapter(DataAdapter):
    """在 DataAdapter 之上叠加位置融合能力。"""

    def __init__(
        self,
        adapter: DataAdapter,
        *,
        fusion_config: FusionConfig | None = None,
    ) -> None:
        self.adapter = adapter
        self.fusion_service = PositionFusionService(fusion_config)

    def __getattr__(self, name: str):
        return getattr(self.adapter, name)

    def connect(self) -> bool:
        ok = self.adapter.connect()
        if ok:
            self.fusion_service.reset()
        return ok

    def disconnect(self) -> None:
        self.adapter.disconnect()

    def poll(self) -> list[PlatformState]:
        return self.fusion_service.fuse_frame(self.adapter.poll())

    def next_frame(self) -> list[PlatformState]:
        return self.fusion_service.fuse_frame(self.adapter.next_frame())

    def is_live(self) -> bool:
        return self.adapter.is_live()

    def get_status(self) -> AdapterStatus:
        status = self.adapter.get_status()
        cfg = self.fusion_service.config
        suffix = (
            f"fusion(on,meas={float(cfg.measurement_weight):.2f},"
            f"gap={float(cfg.max_prediction_gap_sec):.2f},truth={float(cfg.truth_weight):.2f})"
        )
        message = f"{status.message}; {suffix}" if status.message else suffix
        return AdapterStatus(
            connected=status.connected,
            mode=status.mode,
            source_name=f"{status.source_name}+Fusion",
            message=message,
        )
