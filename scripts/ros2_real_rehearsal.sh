#!/usr/bin/env bash
set -euo pipefail

# One-platform real ROS2 rehearsal helper.
# Usage:
#   ./scripts/ros2_real_rehearsal.sh [PLATFORM_ID]

PLATFORM_ID="${1:-UAV1}"

if ! command -v ros2 >/dev/null 2>&1; then
    echo "[rehearsal] ros2 command not found. Please source ROS2 environment first."
    exit 1
fi

echo "[rehearsal] Step 1/3: topic/type checklist"
./scripts/ros2_topic_check.sh "${PLATFORM_ID}" || true

echo "[rehearsal] Step 2/3: start UI in another terminal:"
echo "  python3 app.py --source ros2 --ros2-platform-id ${PLATFORM_ID}"
echo
echo "[rehearsal] Step 3/3: start minimal publishers (current terminal)"
echo "  Press Ctrl+C to stop publishers."
./scripts/ros2_demo_publishers.sh "${PLATFORM_ID}"
