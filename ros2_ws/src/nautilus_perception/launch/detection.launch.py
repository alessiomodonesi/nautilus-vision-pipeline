import os
import yaml

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_dir = get_package_share_directory('nautilus_perception')
    config_file = os.path.join(pkg_dir, 'config', 'detection_params.yaml')

    # argomento di lancio per attivare/disattivare il debug grafico
    debug_arg = DeclareLaunchArgument(
        'enable_debug',
        default_value='false',
        description='Enables the OpenCV debug graphics window'
    )
    enable_debug_conf = LaunchConfiguration('enable_debug')

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
        parameters=[
            config_file,
            {'enable_debug': enable_debug_conf}
        ],
        remappings=remappings
    )

    return LaunchDescription([
        debug_arg,
        detection_node
    ])