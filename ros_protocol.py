from __future__ import annotations

from dataclasses import dataclass
from typing import Final

ROS_PROTOCOL_VERSION: Final[str] = "v1.0.0"
ROS_PROTOCOL_FINGERPRINT: Final[str] = (
    "pose:/swarm/{platform_id}/nav/pose|truth:/swarm/{platform_id}/truth/pose|"
    "health:/swarm/{platform_id}/health|"
    "pose_types:geometry_msgs/msg/PoseStamped,nav_msgs/msg/Odometry|"
    "truth_types:geometry_msgs/msg/PoseStamped,nav_msgs/msg/Odometry|"
    "health_types:std_msgs/msg/String|"
    "platform_id:topic>payload|timestamp:header>payload>local|health:OK,TRACKING,DEGRADED,LOST,OFFLINE,DISCONNECTED,UNKNOWN"
)


DEFAULT_POSE_TOPIC_TEMPLATE: Final[str] = "/swarm/{platform_id}/nav/pose"
DEFAULT_TRUTH_TOPIC_TEMPLATE: Final[str] = "/swarm/{platform_id}/truth/pose"
DEFAULT_HEALTH_TOPIC_TEMPLATE: Final[str] = "/swarm/{platform_id}/health"

SUPPORTED_POSE_MSG_TYPES: Final[tuple[str, ...]] = (
    "geometry_msgs/msg/PoseStamped",
    "nav_msgs/msg/Odometry",
)
SUPPORTED_TRUTH_MSG_TYPES: Final[tuple[str, ...]] = (
    "geometry_msgs/msg/PoseStamped",
    "nav_msgs/msg/Odometry",
)
SUPPORTED_HEALTH_MSG_TYPES: Final[tuple[str, ...]] = ("std_msgs/msg/String",)

PLATFORM_ID_PRIORITY: Final[tuple[str, ...]] = (
    "topic_template:{platform_id}",
    "payload.platform_id",
)
TIMESTAMP_PRIORITY: Final[tuple[str, ...]] = (
    "header.stamp",
    "payload.timestamp",
    "local_receive_time",
)

COORDINATE_FRAME_CONVENTION: Final[str] = "ENU"
POSITION_UNIT: Final[str] = "meter"
VELOCITY_UNIT: Final[str] = "meter_per_second"

HEALTH_STATE_OK: Final[str] = "OK"
HEALTH_STATE_TRACKING: Final[str] = "TRACKING"
HEALTH_STATE_DEGRADED: Final[str] = "DEGRADED"
HEALTH_STATE_LOST: Final[str] = "LOST"
HEALTH_STATE_OFFLINE: Final[str] = "OFFLINE"
HEALTH_STATE_DISCONNECTED: Final[str] = "DISCONNECTED"
HEALTH_STATE_UNKNOWN: Final[str] = "UNKNOWN"

HEALTH_STATES: Final[tuple[str, ...]] = (
    HEALTH_STATE_OK,
    HEALTH_STATE_TRACKING,
    HEALTH_STATE_DEGRADED,
    HEALTH_STATE_LOST,
    HEALTH_STATE_OFFLINE,
    HEALTH_STATE_DISCONNECTED,
    HEALTH_STATE_UNKNOWN,
)

DISCOVERY_MAX_PLATFORMS_DEFAULT: Final[int] = 120
DISCOVERY_MIN_MESSAGES_FOR_PLATFORM_DEFAULT: Final[int] = 1
NO_DATA_WARN_SEC_DEFAULT: Final[float] = 2.0


@dataclass(slots=True, frozen=True)
class RosProtocolSpec:
    version: str = ROS_PROTOCOL_VERSION
    fingerprint: str = ROS_PROTOCOL_FINGERPRINT
    pose_topic_template: str = DEFAULT_POSE_TOPIC_TEMPLATE
    truth_topic_template: str = DEFAULT_TRUTH_TOPIC_TEMPLATE
    health_topic_template: str = DEFAULT_HEALTH_TOPIC_TEMPLATE
    pose_msg_types: tuple[str, ...] = SUPPORTED_POSE_MSG_TYPES
    truth_msg_types: tuple[str, ...] = SUPPORTED_TRUTH_MSG_TYPES
    health_msg_types: tuple[str, ...] = SUPPORTED_HEALTH_MSG_TYPES
    platform_id_priority: tuple[str, ...] = PLATFORM_ID_PRIORITY
    timestamp_priority: tuple[str, ...] = TIMESTAMP_PRIORITY
    coordinate_frame: str = COORDINATE_FRAME_CONVENTION
    position_unit: str = POSITION_UNIT
    velocity_unit: str = VELOCITY_UNIT
    health_states: tuple[str, ...] = HEALTH_STATES


def normalize_health_state(raw: str | None) -> str:
    if raw is None:
        return HEALTH_STATE_UNKNOWN
    value = str(raw).strip().upper()
    if not value:
        return HEALTH_STATE_UNKNOWN
    aliases = {
        "GOOD": HEALTH_STATE_OK,
        "NOMINAL": HEALTH_STATE_OK,
        "WARN": HEALTH_STATE_DEGRADED,
        "WARNING": HEALTH_STATE_DEGRADED,
        "BAD": HEALTH_STATE_DEGRADED,
        "DROP": HEALTH_STATE_LOST,
        "DISCONNECT": HEALTH_STATE_DISCONNECTED,
    }
    normalized = aliases.get(value, value)
    if normalized in HEALTH_STATES:
        return normalized
    return HEALTH_STATE_UNKNOWN
