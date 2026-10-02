from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    # parametri hardware condivisi per 720p @ 5 FPS
    shared_params = {
        'width': 1280,
        'height': 720,
        'fps': 5.0
    }

    # nodo per la camera lx
    lx_camera_node = Node(
        package='camera_ros',
        executable='camera_node',
        name='camera',
        namespace='stereo/lx',
        parameters=[{
            'camera': 0,
            **shared_params
        }],
        output='screen'
    )

    # nodo per la camera rx
    rx_camera_node = Node(
        package='camera_ros',
        executable='camera_node',
        name='camera',
        namespace='stereo/rx',
        parameters=[{
            'camera': 1,
            **shared_params
        }],
        output='screen'
    )

    return LaunchDescription([
        lx_camera_node,
        rx_camera_node
    ])