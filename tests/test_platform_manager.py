from models import PlatformState
from platform_manager import PlatformManager


def make_state(
    platform_id: str,
    timestamp: float,
    *,
    online: bool = True,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
) -> PlatformState:
    return PlatformState(
        id=platform_id,
        type="UAV" if platform_id.startswith("U") else "UGV",
        x=x,
        y=y,
        z=z,
        timestamp=timestamp,
        is_online=online,
    )


def test_apply_updates_stores_latest_state_and_timestamp() -> None:
    pm = PlatformManager(stale_timeout_sec=1.0, remove_timeout_sec=5.0)

    pm.apply_updates([make_state("U1", 0.0, x=1.0)])
    pm.apply_updates([make_state("U1", 0.2, x=2.5), make_state("G1", 0.2)])

    assert pm.current_timestamp == 0.2
    assert pm.platform_states["U1"].x == 2.5
    assert sorted(pm.platform_states.keys()) == ["G1", "U1"]


def test_stale_detection_by_timeout_without_removal() -> None:
    pm = PlatformManager(stale_timeout_sec=0.5, remove_timeout_sec=10.0)

    pm.apply_updates([make_state("U1", 0.0), make_state("G1", 0.0)])
    pm.apply_updates([make_state("G1", 1.0)])

    assert pm.is_platform_stale("U1")
    assert not pm.is_platform_stale("G1")
    assert "U1" in pm.get_stale_platform_ids()


def test_explicit_offline_marks_stale_immediately() -> None:
    pm = PlatformManager(stale_timeout_sec=10.0, remove_timeout_sec=20.0)

    pm.apply_updates([make_state("U1", 0.0, online=False)])

    assert pm.is_platform_stale("U1")


def test_remove_expired_platforms_returns_removed_ids() -> None:
    pm = PlatformManager(stale_timeout_sec=0.5, remove_timeout_sec=1.0)

    pm.apply_updates([make_state("U1", 0.0), make_state("G1", 0.0)])
    removed = pm.apply_updates([make_state("G1", 1.6)])

    assert removed == ["U1"]
    assert "U1" not in pm.platform_states
    assert "G1" in pm.platform_states


def test_selected_platform_is_cleared_when_removed() -> None:
    pm = PlatformManager(stale_timeout_sec=0.5, remove_timeout_sec=1.0)

    pm.apply_updates([make_state("U1", 0.0), make_state("G1", 0.0)])
    pm.set_selected_platform("U1")
    pm.apply_updates([make_state("G1", 1.6)])

    assert pm.get_selected_platform() is None
    assert pm.selected_platform_id is None


def test_set_stale_timeout_recalculates_flags() -> None:
    pm = PlatformManager(stale_timeout_sec=2.0, remove_timeout_sec=10.0)

    pm.apply_updates([make_state("U1", 0.0), make_state("G1", 2.0)])
    assert not pm.is_platform_stale("U1")

    pm.set_stale_timeout(0.5)
    assert pm.is_platform_stale("U1")
    assert not pm.is_platform_stale("G1")


def test_set_remove_timeout_can_trigger_immediate_removal() -> None:
    pm = PlatformManager(stale_timeout_sec=5.0, remove_timeout_sec=10.0)

    pm.apply_updates([make_state("U1", 0.0), make_state("G1", 2.0)])
    removed = pm.set_remove_timeout(1.0)

    assert removed == ["U1"]
    assert "U1" not in pm.platform_states


def test_get_stale_platform_ids_returns_copy() -> None:
    pm = PlatformManager(stale_timeout_sec=0.0, remove_timeout_sec=10.0)
    pm.apply_updates([make_state("U1", 0.0)])
    pm.apply_updates([make_state("G1", 1.0)])

    stale_ids = pm.get_stale_platform_ids()
    stale_ids.clear()

    assert pm.is_platform_stale("U1")
