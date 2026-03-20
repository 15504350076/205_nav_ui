from typing import Protocol

from models import PlatformState


class PlatformDataSource(Protocol):
    """可替换的数据源接口。"""

    def get_initial_data(self) -> list[PlatformState]:
        ...

    def get_next_frame(self) -> list[PlatformState]:
        ...

