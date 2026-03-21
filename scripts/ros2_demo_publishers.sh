#!/usr/bin/env bash
set -euo pipefail

# Minimal ROS2 closed-loop publishers for 205_nav_ui.
# Usage:
#   ./scripts/ros2_demo_publishers.sh [PLATFORM_ID]
# Example:
#   ./scripts/ros2_demo_publishers.sh UAV1

PLATFORM_ID="${1:-UAV1}"
POSE_RATE="${POSE_RATE:-10}"       # Hz
TRUTH_RATE="${TRUTH_RATE:-10}"     # Hz
HEALTH_RATE="${HEALTH_RATE:-2}"    # Hz
SEED="${SEED:-205}"
SHAPE="${SHAPE:-figure8}"          # figure8 | circle

POSE_TOPIC="/swarm/${PLATFORM_ID}/nav/pose"
TRUTH_TOPIC="/swarm/${PLATFORM_ID}/truth/pose"
HEALTH_TOPIC="/swarm/${PLATFORM_ID}/health"

echo "[ros2-demo] platform_id=${PLATFORM_ID}"
echo "[ros2-demo] pose_topic=${POSE_TOPIC}"
echo "[ros2-demo] truth_topic=${TRUTH_TOPIC}"
echo "[ros2-demo] health_topic=${HEALTH_TOPIC}"
echo "[ros2-demo] rates pose=${POSE_RATE}Hz truth=${TRUTH_RATE}Hz health=${HEALTH_RATE}Hz seed=${SEED} shape=${SHAPE}"
echo "[ros2-demo] press Ctrl+C to stop."

python3 - "$PLATFORM_ID" "$POSE_RATE" "$TRUTH_RATE" "$HEALTH_RATE" "$SEED" "$SHAPE" <<'PY'
import json
import math
import random
import sys
import rclpy
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String
from rclpy.node import Node


platform_id = str(sys.argv[1])
pose_rate = max(1.0, float(sys.argv[2]))
truth_rate = max(1.0, float(sys.argv[3]))
health_rate = max(0.5, float(sys.argv[4]))
seed = int(sys.argv[5])
shape = str(sys.argv[6]).strip().lower()

is_ugv = platform_id.upper().startswith("UGV")
base_z = 0.0 if is_ugv else 30.0


def make_trajectory(t: float) -> tuple[float, float]:
    if shape == "circle":
        return 45.0 * math.cos(t * 0.6), 35.0 * math.sin(t * 0.6)
    # figure8 default
    return 50.0 * math.sin(t * 0.7), 28.0 * math.sin(t * 1.4)


class DemoPublisher(Node):
    def __init__(self) -> None:
        super().__init__("nav_ui_demo_publisher")
        self.pose_pub = self.create_publisher(PoseStamped, f"/swarm/{platform_id}/nav/pose", 10)
        self.truth_pub = self.create_publisher(PoseStamped, f"/swarm/{platform_id}/truth/pose", 10)
        self.health_pub = self.create_publisher(String, f"/swarm/{platform_id}/health", 10)

        self.rng = random.Random(seed)
        self.t = 0.0
        self.pose_dt = 1.0 / pose_rate
        self.truth_dt = 1.0 / truth_rate
        self.health_dt = 1.0 / health_rate
        self._truth_elapsed = 0.0
        self._health_elapsed = 0.0
        self.create_timer(self.pose_dt, self.on_pose_tick)

    def _build_pose(self, x: float, y: float, z: float) -> PoseStamped:
        msg = PoseStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "map"
        msg.pose.position.x = float(x)
        msg.pose.position.y = float(y)
        msg.pose.position.z = float(z)
        msg.pose.orientation.w = 1.0
        return msg

    def on_pose_tick(self) -> None:
        self.t += self.pose_dt
        self._truth_elapsed += self.pose_dt
        self._health_elapsed += self.pose_dt

        truth_x, truth_y = make_trajectory(self.t)
        truth_z = base_z if is_ugv else base_z + 2.5 * math.sin(self.t * 0.45)
        est_x = truth_x + self.rng.gauss(0.0, 0.65)
        est_y = truth_y + self.rng.gauss(0.0, 0.65)
        est_z = truth_z + self.rng.gauss(0.0, 0.2 if is_ugv else 0.5)

        self.pose_pub.publish(self._build_pose(est_x, est_y, est_z))

        if self._truth_elapsed + 1e-9 >= self.truth_dt:
            self._truth_elapsed = 0.0
            self.truth_pub.publish(self._build_pose(truth_x, truth_y, truth_z))

        if self._health_elapsed + 1e-9 >= self.health_dt:
            self._health_elapsed = 0.0
            h = String()
            h.data = json.dumps(
                {
                    "is_online": True,
                    "link_state": "OK",
                    "nav_state": "TRACKING",
                },
                ensure_ascii=False,
            )
            self.health_pub.publish(h)


def main() -> None:
    rclpy.init()
    node = DemoPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
PY
