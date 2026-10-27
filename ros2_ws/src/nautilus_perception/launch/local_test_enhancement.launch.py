import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # 'force_on' (con WaterNet) o 'force_off' (senza WaterNet, solo CLAHE)
    WATERNET_MODE = 'force_off'

    # le immagini di test sono installate con il pacchetto
    repo_root = os.environ.get(
        'NAUTILUS_ROOT',
        os.path.expanduser('~/nautilus-vision-pipeline')
    )
    default_image = os.path.join(
        repo_root, 'ros2_ws', 'src', 'nautilus_perception', 'nautilus_perception', 'enhancement', 'images', 'test_image.jpg'
    )

    image_path_arg = DeclareLaunchArgument(
        'image_path',
        default_value=default_image,
        description='Path to the test image used by the local enhancement test'
    )

    # nodo standard ROS per pubblicare un'immagine statica su un topic
    image_publisher = Node(
        package='image_publisher',
        executable='image_publisher_node',
        name='image_publisher',
        arguments=[LaunchConfiguration('image_path')],
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
        parameters=[{
            'waternet_mode': WATERNET_MODE,
            'save_output': True
        }],
        remappings=[('image_raw', 'camera/image_raw')],
        output='screen'
    )

    return LaunchDescription([
        image_path_arg,
        image_publisher,
        enhancer_node
    ])
    