#!/bin/bash
# carica l'ambiente di ROS 2
source /opt/ros/jazzy/setup.bash
source /home/nautilus/nautilus-vision-pipeline/ros2_ws/install/setup.bash

# carica il file di configurazione globale
CONFIG_FILE="/home/nautilus/nautilus-vision-pipeline/pipeline_config.env"
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
else
    echo "Configuration file not found. Using defaults (saving disabled)."
    ENABLE_SAVING=false
fi

# normalizza il valore booleano per il confronto (case-insensitive)
ENABLE_SAVING=$(echo "${ENABLE_SAVING:-false}" | tr '[:upper:]' '[:lower:]')

# all'avvio parte solo il blocco di acquisizione (stereo_camera.launch.py):
#   - camera_ros sinistra e destra (sempre attive)
#   - saving_node (solo se ENABLE_SAVING=true)
#
# i parametri fotometrici (lens position, autofocus, exposure, colour gains)
# sono nel YAML e vengono applicati al boot da camera_ros; lock-cameras.service
# li riapplica subito dopo via set_parameters per sicurezza (vedi lock_cameras.py).
ros2 launch nautilus_camera stereo_camera.launch.py \
    enable_saving:=${ENABLE_SAVING} \
    enable_metrics:=false
