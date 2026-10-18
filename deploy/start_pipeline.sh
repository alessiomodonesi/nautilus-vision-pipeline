#!/bin/bash
source /opt/ros/jazzy/setup.bash
source /home/nautilus/nautilus-vision-pipeline/ros2_ws/install/setup.bash

CONFIG_FILE="/home/nautilus/nautilus-vision-pipeline/pipeline_config.env"
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
else
    echo "Configuration file not found. Using defaults."
fi

# all'avvio partono SOLO le camere.
# la rosbag è gestita da nautilus-bag.service (separato, opzionale via ENABLE_BAG).
ros2 launch nautilus_camera stereo_camera.launch.py \
    enable_metrics:=false