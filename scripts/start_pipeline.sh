#!/bin/bash
# carica l'ambiente di ROS 2
source /opt/ros/jazzy/setup.bash
source /home/pi/nautilus-vision-pipeline/ros2_ws/install/setup.bash

# lancia la pipeline completa
ros2 launch nautilus_perception pipeline.launch.py