#!/bin/bash
# carica l'ambiente di ROS 2
source /opt/ros/jazzy/setup.bash
source /home/pi/nautilus-vision-pipeline/ros2_ws/install/setup.bash

# carica il file di configurazione globale
CONFIG_FILE="/home/pi/nautilus-vision-pipeline/pipeline_config.env"
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
else
    echo "Configuration file not found. Using defaults (saving enabled)."
    ENABLE_ENHANCEMENT=false
    ENABLE_DETECTION=false
    ENABLE_SAVING=true
fi

# lancia la pipeline passando gli argomenti dinamici
ros2 launch nautilus_camera stereo_camera.launch.py \
    enable_saving:=${ENABLE_SAVING:-true} \
    enable_metrics:=${ENABLE_METRICS:-true}
  