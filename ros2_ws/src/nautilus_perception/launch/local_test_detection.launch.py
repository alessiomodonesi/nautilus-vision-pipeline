import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    pkg_dir = get_package_share_directory('nautilus_perception')
    config_file = os.path.join(pkg_dir, 'config', 'detection_params.yaml')

    # percorsi ai video di test nella directory "share" installata
    left_src = os.path.join(pkg_dir, 'data', 'test', 'test_video_1.mp4')
    right_src = os.path.join(pkg_dir, 'data', 'test', 'test_video_2.mp4')

    # publisher stream sinistro
    left_publisher = Node(
        package='image_publisher',
        executable='image_publisher_node',
        name='left_publisher',
        arguments=[left_src],
        parameters=[{'publish_rate': 30.0}],
        remappings=[('image_raw', '/camera/left/image_raw')] 
    )

    # publisher stream destro
    right_publisher = Node(
        package='image_publisher',
        executable='image_publisher_node',
        name='right_publisher',
        arguments=[right_src],
        parameters=[{'publish_rate': 30.0}],
        remappings=[('image_raw', '/camera/right/image_raw')] 
    )

    # nodo di detection
    detection_node = Node(
        package='nautilus_perception',
        executable='detection_node',
        name='detection_node',
        output='screen',
        parameters=[config_file]
    )

    return LaunchDescription([
        left_publisher,
        right_publisher,
        detection_node
    ])
    