from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    # nodo per la camera lx
    lx_enhancement = Node(
        package='nautilus_perception',
        executable='enhancement_node',
        name='enhancement_node',
        namespace='stereo/lx',
        output='screen'
    )
    
    # nodo per la camera rx
    rx_enhancement = Node(
        package='nautilus_perception',
        executable='enhancement_node',
        name='enhancement_node',
        namespace='stereo/rx',
        output='screen'
    )

    return LaunchDescription([
        lx_enhancement,
        rx_enhancement
    ])
