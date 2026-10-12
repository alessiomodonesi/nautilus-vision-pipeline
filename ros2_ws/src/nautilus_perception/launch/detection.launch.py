import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration

def generate_launch_description():
    pkg_dir = get_package_share_directory('nautilus_perception')
    config_file = os.path.join(pkg_dir, 'config', 'detection_params.yaml')

    input_type_arg = DeclareLaunchArgument(
        'input_type_override',
        default_value='raw',
        description='Overrides input_type in YAML if provided'
    )

    detection_node = Node(
        package='nautilus_perception',
        executable='detection_node',
        name='detection_node',
        output='screen',
        parameters=[
            config_file, 
            {'input_type': LaunchConfiguration('input_type_override')}
        ]
    )

    return LaunchDescription([
        input_type_arg,
        detection_node
    ])
    