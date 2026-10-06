from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    # nodo per la camera lx
    lx_enhancement = Node(
        package='nautilus_perception',
        executable='enhancement_node',
        name='enhancement_node',
        namespace='stereo/lx',
        remappings=[('image_raw', 'camera/image_raw')],
        output='screen'
    )
    
    # nodo per la camera rx
    rx_enhancement = Node(
        package='nautilus_perception',
        executable='enhancement_node',
        name='enhancement_node',
        namespace='stereo/rx',
        remappings=[('image_raw', 'camera/image_raw')],
        output='screen'
    )

    return LaunchDescription([
        lx_enhancement,
        rx_enhancement
    ])
    