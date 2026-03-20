from platform_state import PlatformState
from ros_topic_mapping import (
    RosTopicConvention,
    apply_health_payload,
    apply_pose_payload,
    apply_truth_payload,
    topic_bindings_for_platform,
)


def test_topic_bindings_for_platform() -> None:
    bindings = topic_bindings_for_platform("UAV1", convention=RosTopicConvention())
    assert bindings.pose_topic == "/swarm/UAV1/nav/pose"
    assert bindings.truth_topic == "/swarm/UAV1/truth/pose"
    assert bindings.health_topic == "/swarm/UAV1/health"


def test_apply_pose_truth_health_payloads() -> None:
    state = PlatformState(id="U1", type="UAV", x=0.0, y=0.0, z=0.0, timestamp=0.0, is_online=True)
    state = apply_pose_payload(
        state,
        {
            "x": 1.0,
            "y": 2.0,
            "z": 3.0,
            "vx": 0.4,
            "vy": 0.5,
            "vz": 0.6,
            "speed": 0.9,
            "timestamp": 1.0,
            "nav_state": "TRACKING",
        },
    )
    state = apply_truth_payload(
        state,
        {
            "x": 1.2,
            "y": 2.2,
            "z": 3.2,
            "timestamp": 1.0,
        },
    )
    state = apply_health_payload(
        state,
        {
            "is_online": False,
            "link_state": "LOST",
            "nav_state": "DEGRADED",
            "timestamp": 2.0,
        },
    )

    assert state.x == 1.0 and state.y == 2.0 and state.z == 3.0
    assert state.truth_x == 1.2 and state.truth_y == 2.2 and state.truth_z == 3.2
    assert state.is_online is False
    assert state.link_state == "LOST"
    assert state.nav_state == "DEGRADED"
