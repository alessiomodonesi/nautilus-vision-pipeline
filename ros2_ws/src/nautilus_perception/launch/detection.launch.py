import os
import sys
import yaml

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    pkg_dir = get_package_share_directory('nautilus_perception')
    config_file = os.path.join(pkg_dir, 'config', 'detection_params.yaml')

    try:
        with open(config_file, 'r') as f:
            params = yaml.safe_load(f)
            ros_params = params.get('detection_node', {}).get('ros__parameters', {})
            
            # parametro per configurare i remappings
            if 'input_type' not in ros_params:
                raise ValueError("Parameter 'input_type' is missing in the detection_params.yaml file!")

            input_type = ros_params['input_type']
    except Exception as e:
        print(f"[FATAL ERROR] Unable to load YAML configuration or missing parameter: {e}")
        sys.exit(1)

    # mappatura dinamica dei topic in base alla scelta della pipeline
    if input_type == 'enhanced':
        remappings = [
            ('/camera/left/image_enhanced', '/stereo/lx/image_enhanced'),
            ('/camera/right/image_enhanced', '/stereo/rx/image_enhanced'),
        ]
    elif input_type == 'raw':
        remappings = [
            ('/camera/left/image_raw', '/stereo/lx/camera/image_raw'),
            ('/camera/right/image_raw', '/stereo/rx/camera/image_raw'),
        ]
    else:
        print(f"[FATAL ERROR] input_type '{input_type}' not supported. Use only 'raw' or 'enhanced'.")
        sys.exit(1)

    detection_node = Node(
        package='nautilus_perception',
        executable='detection_node',
        name='detection_node',
        output='screen',
        parameters=[config_file],
        remappings=remappings
    )

    return LaunchDescription([
        detection_node
    ])
    