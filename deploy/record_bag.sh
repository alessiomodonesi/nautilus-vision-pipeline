#!/usr/bin/env bash
# Record a Nautilus rosbag with a sane topic set and a predictable name.
#
#   ./scripts/record_bag.sh canal_test_run3
#
# Bags are written to $NAUTILUS_BAG_DIR (default ~/nautilus_bags)
set -euo pipefail

NAME="${1:-run}"
BAG_DIR="${NAUTILUS_BAG_DIR:-$HOME/nautilus_bags}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="$BAG_DIR/${STAMP}_${NAME}"

# Keep this list in sync with docs/topics.md.
TOPICS=(
  /livox/lidar
  /livox/imu
  /scan
  /stereo_front/left/image_raw/compressed
  /stereo_front/right/image_raw/compressed
  /stereo_front/left/camera_info
  /stereo_front/right/camera_info
  /stereo_down/left/image_raw/compressed
  /stereo_down/right/image_raw/compressed
  /stereo_down/left/camera_info
  /stereo_down/right/camera_info
  /mavros/state
  /mavros/local_position/pose
  /mavros/global_position/global
  /mavros/setpoint_velocity/cmd_vel
  /arm/command
  /arm/state
  /tf
  /tf_static
)

mkdir -p "$BAG_DIR"
echo "Recording to $OUT"
echo "Ctrl-C to stop."

# mcap: better random access and smaller than sqlite3 for this kind of data.
exec ros2 bag record \
  --storage mcap \
  --output "$OUT" \
  "${TOPICS[@]}"
