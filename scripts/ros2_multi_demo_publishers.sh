#!/usr/bin/env bash
set -euo pipefail

# Multi-platform minimal publishers (2~3 platforms) for stability rehearsal.
# Usage:
#   ./scripts/ros2_multi_demo_publishers.sh [PLATFORM_IDS]
# Example:
#   ./scripts/ros2_multi_demo_publishers.sh UAV1,UAV2,UGV1

IDS_RAW="${1:-UAV1,UAV2,UGV1}"
IFS=',' read -r -a PLATFORM_IDS <<<"${IDS_RAW}"

PIDS=()

cleanup() {
    for pid in "${PIDS[@]:-}"; do
        if kill -0 "$pid" >/dev/null 2>&1; then
            kill "$pid" >/dev/null 2>&1 || true
        fi
    done
}
trap cleanup EXIT INT TERM

echo "[multi-demo] platforms=${IDS_RAW}"
echo "[multi-demo] press Ctrl+C to stop."

index=0
for platform_id in "${PLATFORM_IDS[@]}"; do
    platform_id="$(echo "${platform_id}" | xargs)"
    if [[ -z "${platform_id}" ]]; then
        continue
    fi
    pose_topic="/swarm/${platform_id}/nav/pose"
    truth_topic="/swarm/${platform_id}/truth/pose"
    health_topic="/swarm/${platform_id}/health"
    pose_rate=$((10 + index * 5))
    truth_rate=$((5 + index * 3))
    health_rate=2
    base_x=$((10 + index * 15))
    base_y=$((20 + index * 10))
    base_z=$((index == 2 ? 0 : 30))

    echo "[multi-demo] ${platform_id} pose=${pose_rate}Hz truth=${truth_rate}Hz health=${health_rate}Hz"

    ros2 topic pub -r "${pose_rate}" "${pose_topic}" geometry_msgs/msg/PoseStamped \
      "{pose: {position: {x: ${base_x}.0, y: ${base_y}.0, z: ${base_z}.0}, orientation: {w: 1.0}}}" >/dev/null &
    PIDS+=("$!")

    ros2 topic pub -r "${truth_rate}" "${truth_topic}" geometry_msgs/msg/PoseStamped \
      "{pose: {position: {x: ${base_x}.4, y: ${base_y}.4, z: ${base_z}.0}, orientation: {w: 1.0}}}" >/dev/null &
    PIDS+=("$!")

    ros2 topic pub -r "${health_rate}" "${health_topic}" std_msgs/msg/String \
      "{data: '{\"is_online\": true, \"link_state\": \"OK\", \"nav_state\": \"TRACKING\"}'}" >/dev/null &
    PIDS+=("$!")

    index=$((index + 1))
done

wait
