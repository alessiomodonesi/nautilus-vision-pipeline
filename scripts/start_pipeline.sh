#!/bin/bash
# carica l'ambiente di ROS 2
source /opt/ros/jazzy/setup.bash
source /home/pi/nautilus-vision-pipeline/ros2_ws/install/setup.bash

# carica il file di configurazione globale
CONFIG_FILE="/home/pi/nautilus-vision-pipeline/pipeline_config.env"
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
else
    echo "Configuration file not found. Using defaults (everything enabled)."
    ENABLE_ENHANCEMENT=true
    ENABLE_DETECTION=true
fi

# lancia la pipeline completa passando gli argomenti dinamici
ros2 launch nautilus_perception pipeline.launch.py \
    enable_enhancement:=$ENABLE_ENHANCEMENT \
    enable_detection:=$ENABLE_DETECTION