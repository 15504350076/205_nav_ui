from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

from platform_state import PlatformState
from ros_protocol import (
    DEFAULT_HEALTH_TOPIC_TEMPLATE,
    DEFAULT_POSE_TOPIC_TEMPLATE,
    DEFAULT_TRUTH_TOPIC_TEMPLATE,
    HEALTH_STATE_DISCONNECTED,
    HEALTH_STATE_LOST,
    HEALTH_STATE_OFFLINE,
    HEALTH_STATE_UNKNOWN,
    POSITION_UNIT,
    VELOCITY_UNIT,
    normalize_health_state,
)


@dataclass(slots=True, frozen=True)
class RosTopicConvention:
    """ROS2 Topic 到内部状态字段的约定。"""

    pose_topic: str = DEFAULT_POSE_TOPIC_TEMPLATE
    truth_topic: str = DEFAULT_TRUTH_TOPIC_TEMPLATE
    health_topic: str = DEFAULT_HEALTH_TOPIC_TEMPLATE


@dataclass(slots=True, frozen=True)
class RosTopicPayloadContract:
    """最小 ROS2 接入字段约定（用于文档与适配器约束）。"""

    pose_fields: tuple[str, ...] = ("x", "y", "z", "timestamp")
    truth_fields: tuple[str, ...] = ("x", "y", "z", "timestamp")
    health_fields: tuple[str, ...] = ("is_online", "link_state", "nav_state", "timestamp")
    position_unit: str = POSITION_UNIT
    velocity_unit: str = VELOCITY_UNIT


@dataclass(slots=True, frozen=True)
class RosTopicBindings:
    platform_id: str
    pose_topic: str
    truth_topic: str
    health_topic: str


def topic_bindings_for_platform(
    platform_id: str,
    *,
    convention: RosTopicConvention | None = None,
) -> RosTopicBindings:
    c = convention or RosTopicConvention()
    return RosTopicBindings(
        platform_id=platform_id,
        pose_topic=c.pose_topic.format(platform_id=platform_id),
        truth_topic=c.truth_topic.format(platform_id=platform_id),
        health_topic=c.health_topic.format(platform_id=platform_id),
    )


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_str(value: Any, default: str | None = None) -> str | None:
    if value is None:
        return default
    return str(value)


def _read_nested_attr(raw: Any, path: tuple[str, ...], default: Any = None) -> Any:
    current = raw
    for name in path:
        if current is None:
            return default
        current = getattr(current, name, None)
    return current if current is not None else default


def _read_first_nested_attr(
    raw: Any,
    paths: tuple[tuple[str, ...], ...],
    default: Any = None,
) -> Any:
    for path in paths:
        value = _read_nested_attr(raw, path, None)
        if value is not None:
            return value
    return default


def _stamp_to_seconds(stamp_like: Any, default: float) -> float:
    if stamp_like is None:
        return default
    sec = getattr(stamp_like, "sec", None)
    nanosec = getattr(stamp_like, "nanosec", None)
    if sec is None:
        return default
    sec_float = _as_float(sec, default)
    # Many ROS publishers leave PoseStamped.header.stamp as 0.
    # Treat zero stamp as "missing" and fallback to local receipt time.
    if nanosec is None:
        return default if sec_float == 0.0 else sec_float
    nsec_float = _as_float(nanosec, 0.0)
    if sec_float == 0.0 and nsec_float == 0.0:
        return default
    return sec_float + nsec_float / 1e9


def payload_from_ros_pose_message(
    message: Any,
    *,
    default_timestamp: float = 0.0,
    platform_type: str | None = None,
    nav_state: str | None = None,
) -> dict[str, Any]:
    """将 PoseStamped/Odometry 形态消息规范化为内部 pose payload."""

    x = _as_float(
        _read_first_nested_attr(
            message,
            (
                ("pose", "position", "x"),
                ("pose", "pose", "position", "x"),
            ),
            None,
        ),
        0.0,
    )
    y = _as_float(
        _read_first_nested_attr(
            message,
            (
                ("pose", "position", "y"),
                ("pose", "pose", "position", "y"),
            ),
            None,
        ),
        0.0,
    )
    z = _as_float(
        _read_first_nested_attr(
            message,
            (
                ("pose", "position", "z"),
                ("pose", "pose", "position", "z"),
            ),
            None,
        ),
        0.0,
    )
    vx = _as_float(_read_nested_attr(message, ("twist", "twist", "linear", "x"), None), 0.0)
    vy = _as_float(_read_nested_attr(message, ("twist", "twist", "linear", "y"), None), 0.0)
    vz = _as_float(_read_nested_attr(message, ("twist", "twist", "linear", "z"), None), 0.0)
    speed = math.sqrt(vx * vx + vy * vy + vz * vz)
    stamp_like = _read_nested_attr(message, ("header", "stamp"), None)
    timestamp = _stamp_to_seconds(stamp_like, default_timestamp)
    payload: dict[str, Any] = {
        "x": x,
        "y": y,
        "z": z,
        "vx": vx,
        "vy": vy,
        "vz": vz,
        "speed": speed,
        "timestamp": timestamp,
    }
    if platform_type:
        payload["type"] = platform_type
    if nav_state:
        payload["nav_state"] = nav_state
    return payload


def payload_from_ros_health_message(
    message: Any,
    *,
    default_timestamp: float = 0.0,
) -> dict[str, Any]:
    """将 health topic 消息规范化为内部 health payload.

    兼容两种输入：
    1) `std_msgs/String`：`data` 为 JSON 字符串。
    2) 纯字符串：如 `OK` / `LOST`。
    """

    raw_text = getattr(message, "data", message)
    if isinstance(raw_text, str):
        text = raw_text.strip()
        if text:
            try:
                raw_json = json.loads(text)
            except json.JSONDecodeError:
                normalized = normalize_health_state(text)
                return {
                    "is_online": normalized
                    not in {HEALTH_STATE_LOST, HEALTH_STATE_OFFLINE, HEALTH_STATE_DISCONNECTED},
                    "link_state": normalized,
                    "nav_state": None,
                    "timestamp": default_timestamp,
                }
            if isinstance(raw_json, dict):
                normalized_state = normalize_health_state(_as_str(raw_json.get("link_state"), None))
                is_online_value = raw_json.get("is_online")
                if is_online_value is None:
                    resolved_is_online = normalized_state not in {
                        HEALTH_STATE_LOST,
                        HEALTH_STATE_OFFLINE,
                        HEALTH_STATE_DISCONNECTED,
                    }
                else:
                    resolved_is_online = bool(is_online_value)
                return {
                    "is_online": resolved_is_online,
                    "link_state": normalized_state,
                    "nav_state": _as_str(raw_json.get("nav_state"), None),
                    "timestamp": _as_float(raw_json.get("timestamp"), default_timestamp),
                }
    return {
        "is_online": True,
        "link_state": HEALTH_STATE_UNKNOWN,
        "nav_state": None,
        "timestamp": default_timestamp,
    }


def apply_pose_payload(
    state: PlatformState,
    payload: dict[str, Any],
) -> PlatformState:
    """pose topic -> PlatformState.position / velocity / time."""

    return PlatformState(
        id=state.id,
        type=_as_str(payload.get("type"), state.type) or state.type,
        x=_as_float(payload.get("x"), state.x),
        y=_as_float(payload.get("y"), state.y),
        z=_as_float(payload.get("z"), state.z),
        vx=_as_float(payload.get("vx"), state.vx),
        vy=_as_float(payload.get("vy"), state.vy),
        vz=_as_float(payload.get("vz"), state.vz),
        speed=_as_float(payload.get("speed"), state.speed),
        timestamp=_as_float(payload.get("timestamp"), state.timestamp),
        is_online=bool(payload.get("is_online", state.is_online)),
        link_state=_as_str(payload.get("link_state"), state.link_state),
        nav_state=_as_str(payload.get("nav_state"), state.nav_state),
        truth_x=state.truth_x,
        truth_y=state.truth_y,
        truth_z=state.truth_z,
    )


def apply_truth_payload(
    state: PlatformState,
    payload: dict[str, Any],
) -> PlatformState:
    """truth topic -> PlatformState.truth_position."""

    return PlatformState(
        id=state.id,
        type=state.type,
        x=state.x,
        y=state.y,
        z=state.z,
        vx=state.vx,
        vy=state.vy,
        vz=state.vz,
        speed=state.speed,
        timestamp=max(state.timestamp, _as_float(payload.get("timestamp"), state.timestamp)),
        is_online=state.is_online,
        link_state=state.link_state,
        nav_state=state.nav_state,
        truth_x=_as_float(payload.get("truth_x", payload.get("x")), state.truth_x or 0.0)
        if payload.get("truth_x", payload.get("x")) is not None
        else state.truth_x,
        truth_y=_as_float(payload.get("truth_y", payload.get("y")), state.truth_y or 0.0)
        if payload.get("truth_y", payload.get("y")) is not None
        else state.truth_y,
        truth_z=_as_float(payload.get("truth_z", payload.get("z")), state.truth_z or 0.0)
        if payload.get("truth_z", payload.get("z")) is not None
        else state.truth_z,
    )


def apply_health_payload(
    state: PlatformState,
    payload: dict[str, Any],
) -> PlatformState:
    """health topic -> PlatformState.is_online / link_state / nav_state."""

    return PlatformState(
        id=state.id,
        type=state.type,
        x=state.x,
        y=state.y,
        z=state.z,
        vx=state.vx,
        vy=state.vy,
        vz=state.vz,
        speed=state.speed,
        timestamp=max(state.timestamp, _as_float(payload.get("timestamp"), state.timestamp)),
        is_online=bool(payload.get("is_online", state.is_online)),
        link_state=_as_str(payload.get("link_state"), state.link_state),
        nav_state=_as_str(payload.get("nav_state"), state.nav_state),
        truth_x=state.truth_x,
        truth_y=state.truth_y,
        truth_z=state.truth_z,
    )
