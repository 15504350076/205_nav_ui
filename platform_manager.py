from models import PlatformState


class PlatformManager:
    """集中管理平台状态、超时告警与移除。"""

    def __init__(self, stale_timeout_sec: float = 0.6, remove_timeout_sec: float = 3.0) -> None:
        self.platform_states: dict[str, PlatformState] = {}
        self.stale_platform_ids: set[str] = set()
        self.selected_platform_id: str | None = None
        self.stale_timeout_sec = max(0.0, stale_timeout_sec)
        self.remove_timeout_sec = max(0.0, remove_timeout_sec)
        self.current_timestamp = 0.0

    def apply_updates(self, platform_list: list[PlatformState]) -> list[str]:
        if platform_list:
            self.current_timestamp = max(item.timestamp for item in platform_list)

        for item in platform_list:
            self.platform_states[item.id] = item

        self._refresh_stale_flags()
        return self._remove_expired_platforms()

    def set_selected_platform(self, platform_id: str | None) -> None:
        self.selected_platform_id = platform_id

    def get_selected_platform(self) -> PlatformState | None:
        if self.selected_platform_id is None:
            return None
        return self.platform_states.get(self.selected_platform_id)

    def set_stale_timeout(self, timeout_sec: float) -> None:
        self.stale_timeout_sec = max(0.0, timeout_sec)
        self._refresh_stale_flags()

    def set_remove_timeout(self, timeout_sec: float) -> list[str]:
        self.remove_timeout_sec = max(0.0, timeout_sec)
        return self._remove_expired_platforms()

    def get_all_platforms(self) -> list[PlatformState]:
        return list(self.platform_states.values())

    def get_stale_platform_ids(self) -> set[str]:
        return set(self.stale_platform_ids)

    def is_platform_stale(self, platform_id: str) -> bool:
        return platform_id in self.stale_platform_ids

    def _refresh_stale_flags(self) -> None:
        stale_ids: set[str] = set()
        for platform_id, state in self.platform_states.items():
            is_stale = (not state.is_online) or (
                self.current_timestamp - state.timestamp > self.stale_timeout_sec
            )
            if is_stale:
                stale_ids.add(platform_id)
        self.stale_platform_ids = stale_ids

    def _remove_expired_platforms(self) -> list[str]:
        removed_ids: list[str] = []
        for platform_id, state in list(self.platform_states.items()):
            if self.current_timestamp - state.timestamp <= self.remove_timeout_sec:
                continue
            self.platform_states.pop(platform_id, None)
            self.stale_platform_ids.discard(platform_id)
            removed_ids.append(platform_id)
            if self.selected_platform_id == platform_id:
                self.selected_platform_id = None
        return removed_ids

