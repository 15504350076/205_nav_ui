from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from platform_state import PlatformState


@dataclass(slots=True, frozen=True)
class RosTopicConvention:
    """ROS2 Topic 到内部状态字段的约定。"""

    pose_topic: str = "/swarm/{platform_id}/nav/pose"
    truth_topic: str = "/swarm/{platform_id}/truth/pose"
    health_topic: str = "/swarm/{platform_id}/health"


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
