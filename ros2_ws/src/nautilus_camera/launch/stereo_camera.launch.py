from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    # parametri condivisi per 720p @ 5 FPS (intervallo di 200000 µs)
    # ros2 param describe /stereo/lx/camera frame_duration_limits
    shared_params = {
        'width': 1280,
        'height': 720,
        'FrameDurationLimits': [200000, 200000]
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
    