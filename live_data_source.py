"""实时数据源适配模块：把 PlatformDataSource 适配为 DataAdapter。"""

from __future__ import annotations

from data_adapter import AdapterStatus, DataAdapter
from data_source import PlatformDataSource
from platform_state import PlatformState


class LiveDataSourceAdapter(DataAdapter):
    """将实时数据源适配为统一 DataAdapter 接口。"""

    def __init__(self, source: PlatformDataSource, *, source_name: str | None = None) -> None:
        self.source = source
        self.source_name = source_name or source.__class__.__name__
        self._connected = False
        self._initialized = False

    def __getattr__(self, name: str):
        return getattr(self.source, name)

    def connect(self) -> bool:
        self._connected = True
        self._initialized = False
        return True

    def disconnect(self) -> None:
        self._connected = False
        self._initialized = False

    def poll(self) -> list[PlatformState]:
        if not self._connected:
            return []
        if not self._initialized:
            self._initialized = True
            return self.source.get_initial_data()
        return self.source.get_next_frame()

    def next_frame(self) -> list[PlatformState]:
        return self.poll()

    def is_live(self) -> bool:
        return True

    def get_status(self) -> AdapterStatus:
        mode = "live" if self._connected else "disconnected"
        message = "connected" if self._connected else "not connected"
        return AdapterStatus(
            connected=self._connected,
            mode=mode,
            source_name=self.source_name,
            message=message,
        )
