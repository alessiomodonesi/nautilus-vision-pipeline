#!/usr/bin/env bash
# registra i due flussi stereo compressi su MCAP.
# va fermato con SIGINT (Ctrl-C o systemctl stop) per finalizzare il file.

# --- ambiente ROS 2 ---
# necessario sia per l'invocazione da systemd (no ~/.bashrc) sia per il
# run manuale da shell pulita. Path hardcoded come nel resto della pipeline.
# NB: i setup di ROS 2/colcon leggono variabili che possono non essere
# definite; `set -u` va quindi attivato DOPO i source, non prima.
source /opt/ros/jazzy/setup.bash
source /home/nautilus/nautilus-vision-pipeline/ros2_ws/install/setup.bash

# --- configurazione globale ---
# fa sì che anche i run manuali usino ROS_DOMAIN_ID, RMW_IMPLEMENTATION,
# CYCLONEDDS_URI e NAUTILUS_BAG_DIR corretti (stessi valori di systemd).
CONFIG_FILE="/home/nautilus/nautilus-vision-pipeline/pipeline_config.env"
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
fi

# ora che l'ambiente è caricato, attiva strict mode
set -euo pipefail

NAME="${1:-stereo}"
BAG_DIR="${NAUTILUS_BAG_DIR:-/home/nautilus/nautilus_bags}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="$BAG_DIR/${STAMP}_${NAME}"
QOS_YAML="/home/nautilus/nautilus-vision-pipeline/deploy/bag_qos.yaml"

mkdir -p "$BAG_DIR"

exec ros2 bag record \
  --storage mcap \
  --compression-mode none \
  --max-bag-duration 300 \
  --max-bag-size 2147483648 \
  --qos-profile-overrides "$QOS_YAML" \
  --output "$OUT" \
  /stereo/lx/camera/image_raw/compressed \
  /stereo/rx/camera/image_raw/compressed \
  /stereo/lx/camera/camera_info \
  /stereo/rx/camera/camera_info