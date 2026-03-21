"""单元测试模块：覆盖 alert_runtime 相关逻辑与边界行为。"""

from alert_runtime import RuntimeAlertEngine
from platform_state import PlatformState


def make_state(
    platform_id: str,
    timestamp: float,
    *,
    platform_type: str = "UAV",
    x: float = 0.0,
    y: float = 0.0,
    truth_x: float | None = None,
    truth_y: float | None = None,
) -> PlatformState:
    return PlatformState(
        id=platform_id,
        type=platform_type,
        x=x,
        y=y,
        z=0.0,
        timestamp=timestamp,
        truth_x=truth_x,
        truth_y=truth_y,
        truth_z=0.0 if truth_x is not None and truth_y is not None else None,
        is_online=True,
    )


def constant_threshold(_platform_id: str, _platform_type: str) -> tuple[float, str]:
    return 1.0, "统一阈值"


def test_runtime_engine_emits_stale_recover_and_offline_events() -> None:
    engine = RuntimeAlertEngine()

    events = engine.evaluate(
        all_platforms=[make_state("U1", 0.0), make_state("G1", 0.0, platform_type="UGV")],
        stale_ids={"U1"},
        removed_ids=[],
        trigger_enabled=True,
        enable_stale=True,
        enable_recover=True,
        enable_offline=True,
        enable_planar_error=False,
        cooldown_sec=0.0,
        escalate_count=2,
        threshold_resolver=constant_threshold,
    )
    assert [(item.level, item.source) for item in events] == [("WARN", "U1")]

    events = engine.evaluate(
        all_platforms=[make_state("U1", 1.0), make_state("G1", 1.0, platform_type="UGV")],
        stale_ids=set(),
        removed_ids=["G1"],
        trigger_enabled=True,
        enable_stale=True,
        enable_recover=True,
        enable_offline=True,
        enable_planar_error=False,
        cooldown_sec=0.0,
        escalate_count=2,
        threshold_resolver=constant_threshold,
    )
    assert [(item.level, item.source) for item in events] == [("INFO", "U1"), ("ERROR", "G1")]


def test_runtime_engine_emits_planar_error_escalation_with_cooldown() -> None:
    engine = RuntimeAlertEngine()
    platforms = [make_state("U1", 1.0, x=4.0, truth_x=0.0, truth_y=0.0)]

    events = engine.evaluate(
        all_platforms=platforms,
        stale_ids=set(),
        removed_ids=[],
        trigger_enabled=True,
        enable_stale=True,
        enable_recover=True,
        enable_offline=True,
        enable_planar_error=True,
        cooldown_sec=0.0,
        escalate_count=2,
        threshold_resolver=constant_threshold,
    )
    assert [item.level for item in events] == ["WARN"]

    platforms = [make_state("U1", 2.0, x=4.0, truth_x=0.0, truth_y=0.0)]
    events = engine.evaluate(
        all_platforms=platforms,
        stale_ids=set(),
        removed_ids=[],
        trigger_enabled=True,
        enable_stale=True,
        enable_recover=True,
        enable_offline=True,
        enable_planar_error=True,
        cooldown_sec=0.0,
        escalate_count=2,
        threshold_resolver=constant_threshold,
    )
    assert [item.level for item in events] == ["ERROR"]

    platforms = [make_state("U1", 2.2, x=4.0, truth_x=0.0, truth_y=0.0)]
    events = engine.evaluate(
        all_platforms=platforms,
        stale_ids=set(),
        removed_ids=[],
        trigger_enabled=True,
        enable_stale=True,
        enable_recover=True,
        enable_offline=True,
        enable_planar_error=True,
        cooldown_sec=1.0,
        escalate_count=2,
        threshold_resolver=constant_threshold,
    )
    assert not events


def test_runtime_engine_trigger_disabled_updates_stale_state_without_emitting() -> None:
    engine = RuntimeAlertEngine()
    engine.last_stale_platform_ids = {"U1"}
    engine.error_exceed_count_by_id = {"U1": 3}

    events = engine.evaluate(
        all_platforms=[make_state("U1", 3.0)],
        stale_ids={"U1"},
        removed_ids=[],
        trigger_enabled=False,
        enable_stale=True,
        enable_recover=True,
        enable_offline=True,
        enable_planar_error=True,
        cooldown_sec=0.0,
        escalate_count=2,
        threshold_resolver=constant_threshold,
    )

    assert not events
    assert engine.last_stale_platform_ids == {"U1"}
    assert engine.error_exceed_count_by_id == {}
