import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    pkg_dir = get_package_share_directory('nautilus_perception')
    config_file = os.path.join(pkg_dir, 'config', 'detection_params.yaml')

    detection_node = Node(
        package='nautilus_perception',
        executable='detection_node',
        name='detection_node',
        output='screen',
        parameters=[config_file],
        remappings=[
            ('/camera/left/image_raw', '/stereo/lx/image_raw'),
            ('/camera/right/image_raw', '/stereo/rx/image_raw'),
        ]
    )

    return LaunchDescription([
        detection_node
    ])
    