from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    # 'auto', 'force_on', 'force_off'
    WATERNET_MODE = 'force_off' 

    # nodo per la camera lx
    lx_enhancement = Node(
        package='nautilus_perception',
        executable='enhancement_node',
        name='enhancement_node',
        namespace='stereo/lx',
        parameters=[{'waternet_mode': WATERNET_MODE}],
        remappings=[('image_raw', 'camera/image_raw')],
        output='screen'
    )
    
    # nodo per la camera rx
    rx_enhancement = Node(
        package='nautilus_perception',
        executable='enhancement_node',
        name='enhancement_node',
        namespace='stereo/rx',
        parameters=[{'waternet_mode': WATERNET_MODE}],
        remappings=[('image_raw', 'camera/image_raw')],
        output='screen'
    )

    return LaunchDescription([
        lx_enhancement,
        rx_enhancement
    ])
    