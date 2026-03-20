from __future__ import annotations

from data_adapter import AdapterStatus, DataAdapter
from platform_state import PlatformState


class RosBridgeAdapter(DataAdapter):
    """ROS2 桥接适配器骨架（当前为 mock 壳实现）。"""

    def __init__(self, *, source_name: str = "ROS2Bridge") -> None:
        self.source_name = source_name
        self._connected = False

    def connect(self) -> bool:
        # TODO: 接入 ROS2 节点/订阅器初始化。
        self._connected = True
        return True

    def disconnect(self) -> None:
        # TODO: 释放 ROS2 句柄、线程与订阅资源。
        self._connected = False

    def poll(self) -> list[PlatformState]:
        # TODO: 从 ROS2 消息缓冲区提取并映射到 PlatformState。
        if not self._connected:
            return []
        return []

    def next_frame(self) -> list[PlatformState]:
        return self.poll()

    def is_live(self) -> bool:
        return True

    def get_status(self) -> AdapterStatus:
        mode = "live" if self._connected else "disconnected"
        message = "mock adapter ready" if self._connected else "mock adapter idle"
        return AdapterStatus(
            connected=self._connected,
            mode=mode,
            source_name=self.source_name,
            message=message,
        )
