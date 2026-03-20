from platform_state import PlatformState


def test_platform_state_round_trip_dict() -> None:
    state = PlatformState(
        id="U1",
        type="UAV",
        x=1.0,
        y=2.0,
        z=3.0,
        vx=0.1,
        vy=0.2,
        vz=0.3,
        speed=0.4,
        timestamp=5.0,
        is_online=False,
        truth_x=1.1,
        truth_y=2.1,
        truth_z=3.1,
    )
    restored = PlatformState.from_dict(state.to_dict())

    assert restored is not None
    assert restored == state


def test_platform_state_from_dict_invalid_returns_none() -> None:
    assert PlatformState.from_dict({"id": "U1"}) is None
    assert PlatformState.from_dict("bad") is None
