from __future__ import annotations

import math
import random
import re
import time
from dataclasses import dataclass
from typing import Callable

from data_adapter import AdapterStatus, DataAdapter
from platform_state import PlatformState
from ros2_client import RosInboundMessage, RosIngressClient
from ros_topic_mapping import (
    RosTopicConvention,
    apply_health_payload,
    apply_pose_payload,
    apply_truth_payload,
)


_TOPIC_PLATFORM_ID_PATTERN = re.compile(r"/swarm/([^/]+)/")


@dataclass(slots=True)
class MockStreamConfig:
    platform_ids: list[str]
    interval_sec: float = 0.1
    seed: int = 205


class RosBridgeAdapter(DataAdapter):
    """ROS2 桥接适配器（默认提供 mock 实时订阅流）。"""

    def __init__(
        self,
        *,
        source_name: str = "ROS2Bridge",
        topic_convention: RosTopicConvention | None = None,
        clock: Callable[[], float] | None = None,
        ros_client: RosIngressClient | None = None,
    ) -> None:
        self.source_name = source_name
        self.topic_convention = topic_convention or RosTopicConvention()
        self._clock = clock or time.monotonic
        self._ros_client = ros_client
        self._connected = False
        self._mock_enabled = False
        self._mock_interval_sec = 0.1
        self._last_emit_ts = 0.0
        self._mock_time = 0.0
        self._rng = random.Random(205)
        self._platform_states: dict[str, PlatformState] = {}
        self._dirty_platform_ids: set[str] = set()
        self._mock_phase_by_id: dict[str, float] = {}
        self._received_message_count = 0
        self._last_message_monotonic_sec: float | None = None

    def connect(self) -> bool:
        if self._ros_client is not None:
            self._connected = self._ros_client.connect()
        else:
            self._connected = True
        self._last_emit_ts = self._clock()
        return self._connected

    def disconnect(self) -> None:
        if self._ros_client is not None:
            self._ros_client.disconnect()
        self._connected = False
        self._dirty_platform_ids.clear()

    def poll(self) -> list[PlatformState]:
        if not self._connected:
            return []
        if self._ros_client is not None:
            for message in self._ros_client.poll():
                self._apply_ros_inbound_message(message)
        now = self._clock()
        if self._mock_enabled and now - self._last_emit_ts >= self._mock_interval_sec:
            self._last_emit_ts = now
            self._emit_mock_tick()
        return self._flush_dirty_updates()

    def next_frame(self) -> list[PlatformState]:
        return self.poll()

    def is_live(self) -> bool:
        return True

    def get_status(self) -> AdapterStatus:
        mode = "live" if self._connected else "disconnected"
        message_stats = self._build_message_stats()
        if self._ros_client is not None:
            message = self._ros_client.get_status_message()
            if self._mock_enabled:
                message = f"{message}; mock stream active"
            if message_stats:
                message = f"{message}; {message_stats}"
        elif self._mock_enabled:
            message = "mock stream active" if self._connected else "mock stream idle"
            if message_stats:
                message = f"{message}; {message_stats}"
        else:
            message = "awaiting ROS2 subscriptions" if self._connected else "adapter idle"
            if message_stats:
                message = f"{message}; {message_stats}"
        return AdapterStatus(
            connected=self._connected,
            mode=mode,
            source_name=self.source_name,
            message=message,
        )

    @property
    def ros_runtime_available(self) -> bool:
        if self._ros_client is None:
            return True
        return self._ros_client.is_available()

    # -------- ROS-style topic callbacks / mapping --------
    def on_pose_topic(self, topic: str, payload: dict) -> bool:
        platform_id = self._platform_id_from_topic(topic, payload=payload)
        if platform_id is None:
            return False
        current = self._platform_states.get(platform_id, self._new_state(platform_id))
        updated = apply_pose_payload(current, payload)
        self._platform_states[platform_id] = updated
        self._dirty_platform_ids.add(platform_id)
        self._mark_message_received()
        return True

    def on_truth_topic(self, topic: str, payload: dict) -> bool:
        platform_id = self._platform_id_from_topic(topic, payload=payload)
        if platform_id is None:
            return False
        current = self._platform_states.get(platform_id, self._new_state(platform_id))
        updated = apply_truth_payload(current, payload)
        self._platform_states[platform_id] = updated
        self._dirty_platform_ids.add(platform_id)
        self._mark_message_received()
        return True

    def on_health_topic(self, topic: str, payload: dict) -> bool:
        platform_id = self._platform_id_from_topic(topic, payload=payload)
        if platform_id is None:
            return False
        current = self._platform_states.get(platform_id, self._new_state(platform_id))
        updated = apply_health_payload(current, payload)
        self._platform_states[platform_id] = updated
        self._dirty_platform_ids.add(platform_id)
        self._mark_message_received()
        return True

    def _apply_ros_inbound_message(self, message: RosInboundMessage) -> None:
        if message.kind == "pose":
            self.on_pose_topic(message.topic, message.payload)
            return
        if message.kind == "truth":
            self.on_truth_topic(message.topic, message.payload)
            return
        if message.kind == "health":
            self.on_health_topic(message.topic, message.payload)

    # -------- Mock live stream controls --------
    def enable_mock_stream(self, config: MockStreamConfig) -> None:
        self._mock_enabled = True
        self._mock_interval_sec = max(0.02, float(config.interval_sec))
        self._mock_time = 0.0
        self._rng = random.Random(config.seed)
        self._mock_phase_by_id = {}
        for index, platform_id in enumerate(config.platform_ids):
            self._platform_states.setdefault(platform_id, self._new_state(platform_id))
            self._mock_phase_by_id[platform_id] = index * 0.7
        self._last_emit_ts = self._clock()

    def disable_mock_stream(self) -> None:
        self._mock_enabled = False

    # -------- Helpers --------
    def _platform_id_from_topic(self, topic: str, *, payload: dict | None = None) -> str | None:
        match = _TOPIC_PLATFORM_ID_PATTERN.search(topic)
        if match is None:
            if payload is None:
                return None
            raw_platform_id = payload.get("platform_id")
            if raw_platform_id is None:
                return None
            platform_id = str(raw_platform_id).strip()
            return platform_id or None
        return match.group(1)

    def _mark_message_received(self) -> None:
        self._received_message_count += 1
        self._last_message_monotonic_sec = self._clock()

    def _build_message_stats(self) -> str:
        platform_count = len(self._platform_states)
        if self._last_message_monotonic_sec is None:
            freshness = "data=none"
        else:
            age_sec = max(0.0, self._clock() - self._last_message_monotonic_sec)
            freshness = f"last={age_sec:.1f}s"
        return (
            f"platforms={platform_count}, msgs={self._received_message_count}, {freshness}"
        )

    def _new_state(self, platform_id: str) -> PlatformState:
        platform_type = "UAV" if platform_id.upper().startswith("UAV") else "UGV"
        return PlatformState(
            id=platform_id,
            type=platform_type,
            x=0.0,
            y=0.0,
            z=30.0 if platform_type == "UAV" else 0.0,
            timestamp=0.0,
            is_online=True,
            link_state="OK",
            nav_state="INIT",
        )

    def _flush_dirty_updates(self) -> list[PlatformState]:
        if not self._dirty_platform_ids:
            return []
        updates = [
            self._platform_states[platform_id]
            for platform_id in sorted(self._dirty_platform_ids)
            if platform_id in self._platform_states
        ]
        self._dirty_platform_ids.clear()
        return updates

    def _emit_mock_tick(self) -> None:
        if not self._mock_phase_by_id:
            return
        self._mock_time += self._mock_interval_sec
        for platform_id, phase0 in self._mock_phase_by_id.items():
            phase = self._mock_time + phase0
            current = self._platform_states.get(platform_id, self._new_state(platform_id))
            if current.type == "UAV":
                truth_x = 80.0 * math.cos(phase)
                truth_y = 60.0 * math.sin(phase * 0.9)
                truth_z = 28.0 + 4.0 * math.sin(phase * 0.7)
            else:
                truth_x = 40.0 * math.cos(phase * 0.6)
                truth_y = 35.0 * math.sin(phase * 0.7)
                truth_z = 0.0

            pose_payload = {
                "type": current.type,
                "x": truth_x + self._rng.gauss(0.0, 0.8),
                "y": truth_y + self._rng.gauss(0.0, 0.8),
                "z": truth_z + self._rng.gauss(0.0, 0.2),
                "timestamp": self._mock_time,
                "nav_state": "TRACKING",
            }
            truth_payload = {
                "x": truth_x,
                "y": truth_y,
                "z": truth_z,
                "timestamp": self._mock_time,
            }
            health_payload = {
                "is_online": True,
                "link_state": "OK",
                "nav_state": "TRACKING",
                "timestamp": self._mock_time,
            }

            pose_topic = self.topic_convention.pose_topic.format(platform_id=platform_id)
            truth_topic = self.topic_convention.truth_topic.format(platform_id=platform_id)
            health_topic = self.topic_convention.health_topic.format(platform_id=platform_id)

            self.on_pose_topic(pose_topic, pose_payload)
            self.on_truth_topic(truth_topic, truth_payload)
            self.on_health_topic(health_topic, health_payload)


class MockRosLiveAdapter(RosBridgeAdapter):
    """可直接用于 UI 联调的 mock 实时 ROS 适配器。"""

    def __init__(
        self,
        *,
        platform_ids: list[str] | None = None,
        interval_sec: float = 0.1,
        seed: int = 205,
        source_name: str = "ROS2Bridge(Mock)",
        topic_convention: RosTopicConvention | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        super().__init__(
            source_name=source_name,
            topic_convention=topic_convention,
            clock=clock,
        )
        ids = platform_ids or ["UAV1", "UAV2", "UGV1"]
        self.enable_mock_stream(
            MockStreamConfig(
                platform_ids=ids,
                interval_sec=interval_sec,
                seed=seed,
            )
        )
