from evaluation_service import (
    EvaluationService,
    compute_planar_error_from_state,
    extract_ground_truth,
    extract_navigation_estimate,
)
from platform_state import PlatformState


def make_state(
    platform_id: str,
    timestamp: float,
    *,
    x: float = 0.0,
    y: float = 0.0,
    truth_x: float | None = None,
    truth_y: float | None = None,
    truth_z: float | None = 0.0,
) -> PlatformState:
    return PlatformState(
        id=platform_id,
        type="UAV",
        x=x,
        y=y,
        z=0.0,
        timestamp=timestamp,
        truth_x=truth_x,
        truth_y=truth_y,
        truth_z=truth_z if truth_x is not None and truth_y is not None else None,
        is_online=True,
    )


def test_extract_estimate_truth_and_error() -> None:
    state = make_state("U1", 1.0, x=3.0, y=4.0, truth_x=0.0, truth_y=0.0)
    estimate = extract_navigation_estimate(state)
    truth = extract_ground_truth(state)
    error = compute_planar_error_from_state(state)

    assert estimate.platform_id == "U1"
    assert truth is not None
    assert truth.platform_id == "U1"
    assert error == 5.0


def test_evaluation_service_metrics_and_window_trim() -> None:
    service = EvaluationService(history_duration_sec=2.0)
    service.update([make_state("U1", 0.0, x=3.0, y=4.0, truth_x=0.0, truth_y=0.0)])
    service.update([make_state("U1", 1.0, x=6.0, y=8.0, truth_x=0.0, truth_y=0.0)])
    service.update([make_state("U1", 4.0, x=3.0, y=4.0, truth_x=0.0, truth_y=0.0)])

    series = service.get_error_series("U1")
    metrics = service.get_metrics("U1")

    # First sample is trimmed by duration window (4.0 - 2.0 cutoff).
    assert series == [10.0, 5.0]
    assert metrics is not None
    assert metrics.planar_error == 5.0
    assert metrics.sample_count == 2
    assert metrics.rms_planar_error is not None


def test_evaluation_service_clear_histories_keeps_current_point() -> None:
    service = EvaluationService(history_duration_sec=10.0)
    s1 = make_state("U1", 1.0, x=3.0, y=4.0, truth_x=0.0, truth_y=0.0)
    s2 = make_state("U1", 2.0, x=6.0, y=8.0, truth_x=0.0, truth_y=0.0)
    service.update([s1])
    service.update([s2])
    assert service.get_error_series("U1") == [5.0, 10.0]

    service.clear_histories([s2])
    assert service.get_error_series("U1") == [10.0]
