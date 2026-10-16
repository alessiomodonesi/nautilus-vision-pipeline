from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # modalità waternet: 'auto', 'force_on', 'force_off'
    # il default è 'force_off' perché WaterNet è una rete neurale pensata solo
    # per post-produzione delle immagini. sulla barca non serve alla navigazione
    # né alla detection e consuma batteria e CPU/GPU senza alcun beneficio operativo.
    # 'auto' e 'force_on' restano disponibili per uso su workstation o per
    # rigenerare immagini a posteriori: vanno richiesti esplicitamente.
    waternet_mode_arg = DeclareLaunchArgument(
        'waternet_mode', default_value='force_off',
        description="auto | force_on | force_off = CLAHE + sharpening only"
    )

    # nodo per la camera lx
    lx_enhancement = Node(
            package='nautilus_perception',
            executable='enhancement_node',
            name='enhancement_node',
            namespace='stereo/lx',
            parameters=[{'waternet_mode': LaunchConfiguration('waternet_mode')}],
            remappings=[('image_raw', 'camera/image_raw')],
            output='screen'
    )
    
    # nodo per la camera rx
    rx_enhancement = Node(
            package='nautilus_perception',
            executable='enhancement_node',
            name='enhancement_node',
            namespace='stereo/rx',
            parameters=[{'waternet_mode': LaunchConfiguration('waternet_mode')}],
            remappings=[('image_raw', 'camera/image_raw')],
            output='screen'
    )

    return LaunchDescription([
        waternet_mode_arg,
        lx_enhancement,
        rx_enhancement,
    ])
    