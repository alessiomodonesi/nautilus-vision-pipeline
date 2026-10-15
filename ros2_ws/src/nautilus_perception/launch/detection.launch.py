import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution


def generate_launch_description():
    pkg_dir = get_package_share_directory('nautilus_perception')

    params_file_arg = DeclareLaunchArgument(
        'params_file',
        default_value='detection_params.yaml',
        description='Nome del file params in config/'
    )

    input_type_arg = DeclareLaunchArgument(
        'input_type_override',
        default_value='raw',
        description='Overrides input_type in YAML if provided'
    )

    enable_debug_arg = DeclareLaunchArgument(
        'enable_debug',
        default_value='false',
        description='Overrides enable_debug in YAML (true/false for OpenCV debug window)'
    )

    params_path = PathJoinSubstitution(
        [pkg_dir, 'config', LaunchConfiguration('params_file')]
    )

    detection_node = Node(
        package='nautilus_perception',
        executable='detection_node',
        name='detection_node',
        output='screen',
        parameters=[
            params_path,
            {
                'input_type': LaunchConfiguration('input_type_override'),
                'enable_debug': LaunchConfiguration('enable_debug')
            }
        ]
    )

    return LaunchDescription([
        params_file_arg,
        input_type_arg,
        enable_debug_arg,
        detection_node
    ])
    