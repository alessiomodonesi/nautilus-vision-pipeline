#!/bin/bash
# lock_cameras.sh — imposta i parametri di lock fotometrico su entrambe le camere
# Uso: ./lock_cameras.sh   (DOPO aver lanciato stereo_camera.launch.py)

source /opt/ros/jazzy/setup.bash
source "$HOME/nautilus-vision-pipeline/ros2_ws/install/setup.bash"

echo "Waiting for node discovery..."

# LensPosition diverso per lx e rx: lenti fisiche con offset meccanico diverso
declare -A LENS_POS
LENS_POS[lx]=3.0
LENS_POS[rx]=1.0

# attende fino a 30 s che entrambe le camere siano visibili
for i in $(seq 1 30); do
  if ros2 node list 2>/dev/null | grep -q "^/stereo/lx/camera$" && \
     ros2 node list 2>/dev/null | grep -q "^/stereo/rx/camera$"; then
    break
  fi
  sleep 1
done

for ns in lx rx; do
  node="/stereo/${ns}/camera"

  if ! ros2 node list 2>/dev/null | grep -q "^${node}$"; then
    echo "[ERROR] Node $node not found after 30s. Are the cameras active?"
    exit 1
  fi

  echo "Locking $node (LensPosition=${LENS_POS[$ns]})"
  ros2 param set "$node" AeEnable     false               || echo "  [WARN] AeEnable"
  ros2 param set "$node" AwbEnable    false               || echo "  [WARN] AwbEnable"
  ros2 param set "$node" ExposureTime 20000               || echo "  [WARN] ExposureTime"
  ros2 param set "$node" ColourGains  "[1.5, 1.5]"        || echo "  [WARN] ColourGains"
  ros2 param set "$node" AfMode       0                   || echo "  [WARN] AfMode"
  ros2 param set "$node" LensPosition "${LENS_POS[$ns]}"  || echo "  [WARN] LensPosition"
  # ros2 param set "$node" AnalogueGain 1.0               || echo "  [WARN] AnalogueGain"

  echo "[OK] $node"
done