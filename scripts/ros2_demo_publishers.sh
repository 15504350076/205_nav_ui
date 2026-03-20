#!/usr/bin/env bash
set -euo pipefail

# Minimal ROS2 closed-loop publishers for 205_nav_ui.
# Usage:
#   ./scripts/ros2_demo_publishers.sh [PLATFORM_ID]
# Example:
#   ./scripts/ros2_demo_publishers.sh UAV1

PLATFORM_ID="${1:-UAV1}"
POSE_RATE="${POSE_RATE:-10}"
TRUTH_RATE="${TRUTH_RATE:-10}"
HEALTH_RATE="${HEALTH_RATE:-2}"

POSE_TOPIC="/swarm/${PLATFORM_ID}/nav/pose"
TRUTH_TOPIC="/swarm/${PLATFORM_ID}/truth/pose"
HEALTH_TOPIC="/swarm/${PLATFORM_ID}/health"

PIDS=()

cleanup() {
    for pid in "${PIDS[@]:-}"; do
        if kill -0 "$pid" >/dev/null 2>&1; then
            kill "$pid" >/dev/null 2>&1 || true
        fi
    done
}

trap cleanup EXIT INT TERM

echo "[ros2-demo] platform_id=${PLATFORM_ID}"
echo "[ros2-demo] pose_topic=${POSE_TOPIC}"
echo "[ros2-demo] truth_topic=${TRUTH_TOPIC}"
echo "[ros2-demo] health_topic=${HEALTH_TOPIC}"
echo "[ros2-demo] rates pose=${POSE_RATE}Hz truth=${TRUTH_RATE}Hz health=${HEALTH_RATE}Hz"
echo "[ros2-demo] press Ctrl+C to stop."

ros2 topic pub -r "${POSE_RATE}" "${POSE_TOPIC}" geometry_msgs/msg/PoseStamped \
  "{pose: {position: {x: 10.0, y: 20.0, z: 30.0}, orientation: {w: 1.0}}}" >/dev/null &
PIDS+=("$!")

ros2 topic pub -r "${TRUTH_RATE}" "${TRUTH_TOPIC}" geometry_msgs/msg/PoseStamped \
  "{pose: {position: {x: 10.3, y: 20.3, z: 30.1}, orientation: {w: 1.0}}}" >/dev/null &
PIDS+=("$!")

ros2 topic pub -r "${HEALTH_RATE}" "${HEALTH_TOPIC}" std_msgs/msg/String \
  "{data: '{\"is_online\": true, \"link_state\": \"OK\", \"nav_state\": \"TRACKING\"}'}" >/dev/null &
PIDS+=("$!")

wait
