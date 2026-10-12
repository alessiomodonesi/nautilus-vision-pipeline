import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share   = get_package_share_directory('nautilus_camera')
    config_file = os.path.join(pkg_share, 'config', 'nautilus_camera.yaml')

    # argomenti di lancio
    enable_metrics_arg = DeclareLaunchArgument(
        'enable_metrics', default_value='true',
        description='Avvia il nodo di benchmark (FPS/jitter/skew)'
    )
    enable_saving_arg = DeclareLaunchArgument(
        'enable_saving', default_value='true',
        description='Avvia il nodo di salvataggio immagini su disco'
    )
    enable_display_arg = DeclareLaunchArgument(
        'enable_display', default_value='false',
        description='Apre la finestra OpenCV del metrics_node (richiede GUI)'
    )

    # nodi camera_ros (sempre attivi)
    # nota: camera_ros legge i parametri per-nodo dal YAML, quindi
    # non vengono specificati di nuovo qui per evitare duplicazioni.
    lx_camera = Node(
        package='camera_ros',
        executable='camera_node',
        name='camera',
        namespace='stereo/lx',
        parameters=[
            config_file,
            {
                'AeEnable': False,
                'AwbEnable': False,
                'ExposureTime': 20000,
                'ColourGains': [1.5, 1.5],
                # AnalogueGain rimosso: rifiutato da camera_ros sul IMX708
            },
        ],
        output='screen',
    )
    rx_camera = Node(
        package='camera_ros',
        executable='camera_node',
        name='camera',
        namespace='stereo/rx',
        parameters=[
            config_file,
            {
                'AeEnable': False,
                'AwbEnable': False,
                'ExposureTime': 20000,
                'ColourGains': [1.5, 1.5],
                # AnalogueGain rimosso: rifiutato da camera_ros sul IMX708
            },
        ],
        output='screen',
    )

    # nodo di benchmark
    metrics_node = Node(
        package='nautilus_camera',
        executable='metrics_node',
        name='metrics_node',
        parameters=[
            config_file,
            {'display': LaunchConfiguration('enable_display')},
        ],
        output='screen',
        condition=IfCondition(LaunchConfiguration('enable_metrics')),
    )

    # nodo di salvataggio
    saving_node = Node(
        package='nautilus_camera',
        executable='saving_node',
        name='saving_node',
        parameters=[config_file],
        output='screen',
        condition=IfCondition(LaunchConfiguration('enable_saving')),
    )

    return LaunchDescription([
        enable_metrics_arg,
        enable_saving_arg,
        enable_display_arg,
        lx_camera,
        rx_camera,
        metrics_node,
        saving_node,
    ])
    