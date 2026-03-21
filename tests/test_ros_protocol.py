from ros_protocol import (
    RosProtocolSpec,
    HEALTH_STATE_DEGRADED,
    HEALTH_STATE_OK,
    HEALTH_STATE_UNKNOWN,
    normalize_health_state,
)


def test_ros_protocol_spec_defaults() -> None:
    spec = RosProtocolSpec()
    assert spec.pose_topic_template.startswith("/swarm/")
    assert "geometry_msgs/msg/PoseStamped" in spec.pose_msg_types
    assert "nav_msgs/msg/Odometry" in spec.truth_msg_types
    assert "std_msgs/msg/String" in spec.health_msg_types


def test_normalize_health_state_alias_and_unknown() -> None:
    assert normalize_health_state("good") == HEALTH_STATE_OK
    assert normalize_health_state("warning") == HEALTH_STATE_DEGRADED
    assert normalize_health_state("???") == HEALTH_STATE_UNKNOWN
