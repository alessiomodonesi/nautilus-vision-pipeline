import os
import yaml

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    pkg_dir = get_package_share_directory('nautilus_perception')
    config_file = os.path.join(pkg_dir, 'config', 'detection_params.yaml')

    # parametro per configurare i remappings
    input_type = 'raw'
    try:
        with open(config_file, 'r') as f:
            params = yaml.safe_load(f)
            input_type = params.get('detection_node', {}).get('ros__parameters', {}).get('input_type', 'raw')
    except Exception:
        pass

    # mappatura dinamica dei topic in base alla scelta della pipeline
    if input_type == 'enhanced':
        remappings = [
            ('/camera/left/image_enhanced', '/stereo/lx/image_enhanced'),
            ('/camera/right/image_enhanced', '/stereo/rx/image_enhanced'),
        ]
    else:
        remappings = [
            ('/camera/left/image_raw', '/stereo/lx/camera/image_raw'),
            ('/camera/right/image_raw', '/stereo/rx/camera/image_raw'),
        ]

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