from platform_state import PlatformState
from ros_topic_mapping import (
    RosTopicConvention,
    apply_health_payload,
    apply_pose_payload,
    apply_truth_payload,
    payload_from_ros_health_message,
    payload_from_ros_pose_message,
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


def test_payload_from_ros_pose_message() -> None:
    class Stamp:
        sec = 10
        nanosec = 500_000_000

    class Header:
        stamp = Stamp()

    class Position:
        x = 1.0
        y = 2.0
        z = 3.0

    class Pose:
        position = Position()

    class PoseStampedLike:
        header = Header()
        pose = Pose()

    payload = payload_from_ros_pose_message(PoseStampedLike(), default_timestamp=0.0, platform_type="UAV")
    assert payload["x"] == 1.0 and payload["y"] == 2.0 and payload["z"] == 3.0
    assert payload["timestamp"] == 10.5
    assert payload["type"] == "UAV"


def test_payload_from_ros_pose_message_falls_back_on_zero_stamp() -> None:
    class Stamp:
        sec = 0
        nanosec = 0

    class Header:
        stamp = Stamp()

    class Position:
        x = 5.0
        y = 6.0
        z = 7.0

    class Pose:
        position = Position()

    class PoseStampedLike:
        header = Header()
        pose = Pose()

    payload = payload_from_ros_pose_message(PoseStampedLike(), default_timestamp=123.0)
    assert payload["timestamp"] == 123.0


def test_payload_from_ros_health_message_with_json() -> None:
    class StringLike:
        data = '{"is_online": false, "link_state": "LOST", "nav_state": "DEGRADED", "timestamp": 9.0}'

    payload = payload_from_ros_health_message(StringLike(), default_timestamp=1.0)
    assert payload["is_online"] is False
    assert payload["link_state"] == "LOST"
    assert payload["nav_state"] == "DEGRADED"
    assert payload["timestamp"] == 9.0


def test_payload_from_ros_odometry_like_message() -> None:
    class Stamp:
        sec = 3
        nanosec = 0

    class Header:
        stamp = Stamp()

    class Position:
        x = 4.0
        y = 5.0
        z = 6.0

    class PoseInner:
        position = Position()

    class Pose:
        pose = PoseInner()

    class Linear:
        x = 0.3
        y = 0.4
        z = 0.0

    class TwistInner:
        linear = Linear()

    class Twist:
        twist = TwistInner()

    class OdometryLike:
        header = Header()
        pose = Pose()
        twist = Twist()

    payload = payload_from_ros_pose_message(OdometryLike(), default_timestamp=0.0)
    assert payload["x"] == 4.0 and payload["y"] == 5.0 and payload["z"] == 6.0
    assert payload["vx"] == 0.3 and payload["vy"] == 0.4 and payload["vz"] == 0.0
    assert payload["speed"] == 0.5
