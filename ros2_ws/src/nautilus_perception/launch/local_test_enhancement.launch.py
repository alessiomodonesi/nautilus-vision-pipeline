import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    # 'force_on' (con WaterNet) o 'force_off' (senza WaterNet, solo CLAHE)
    WATERNET_MODE = 'force_on'

    # percorso per l'immagine di test nella directory "share" installata
    pkg_dir = get_package_share_directory('nautilus_perception')
    IMG_PATH = os.path.join(pkg_dir, 'data', 'test', 'test_image.jpg')

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
        parameters=[{
            'waternet_mode': WATERNET_MODE,
            'save_output': True
        }],
        remappings=[('image_raw', 'camera/image_raw')],
        output='screen'
    )

    return LaunchDescription([
        image_publisher,
        enhancer_node
    ])
    