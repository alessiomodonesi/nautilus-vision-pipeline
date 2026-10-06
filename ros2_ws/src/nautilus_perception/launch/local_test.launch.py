import os
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    # 'auto', 'force_on', 'force_off'
    WATERNET_MODE = 'force_on'
    IMG_PATH = '/home/nautilus/nautilus-vision-pipeline/ros2_ws/src/nautilus_perception/nautilus_perception/enhancement/test.jpg'

    # nodo standard ROS per pubblicare un'immagine statica su un topic
    image_publisher = Node(
        package='image_publisher',
        executable='image_publisher_node',
        name='image_publisher',
        arguments=[IMG_PATH],
        parameters=[{
            'publish_rate': 1.0
        }],
        remappings=[('image_raw', 'camera/image_raw')] 
    )

    # nodo di enhancement
    enhancer_node = Node(
        package='nautilus_perception',
        executable='enhancement_node',
        name='enhancement_node',
        parameters=[{'waternet_mode': WATERNET_MODE}],
        remappings=[('image_raw', 'camera/image_raw')],
        output='screen'
    )

    return LaunchDescription([
        image_publisher,
        enhancer_node
    ])
    