#!/usr/bin/env bash
set -euo pipefail

# Check topic existence/type for a platform against frozen protocol.
# Usage:
#   ./scripts/ros2_topic_check.sh [PLATFORM_ID]

PLATFORM_ID="${1:-UAV1}"
POSE_TOPIC="/swarm/${PLATFORM_ID}/nav/pose"
TRUTH_TOPIC="/swarm/${PLATFORM_ID}/truth/pose"
HEALTH_TOPIC="/swarm/${PLATFORM_ID}/health"

echo "[check] platform=${PLATFORM_ID}"
echo "[check] expecting topics:"
echo "  - ${POSE_TOPIC}"
echo "  - ${TRUTH_TOPIC}"
echo "  - ${HEALTH_TOPIC}"
echo

for topic in "${POSE_TOPIC}" "${TRUTH_TOPIC}" "${HEALTH_TOPIC}"; do
    echo "========== ${topic} =========="
    if ros2 topic info -v "${topic}" >/tmp/ros2_topic_check.$$.txt 2>/dev/null; then
        cat /tmp/ros2_topic_check.$$.txt
    else
        echo "not found"
    fi
    echo
done

rm -f /tmp/ros2_topic_check.$$.txt
