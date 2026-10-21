import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, TimerAction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

qos_yaml = os.path.join(
    get_package_share_directory('nautilus_common'),
    'config', 'qos_overrides.yaml',
)


def launch_setup(context, *args, **kwargs):
    pkg_share = get_package_share_directory('nautilus_camera')
    params_file = LaunchConfiguration('params_file').perform(context)
    config_file = os.path.join(pkg_share, 'config', params_file)

    # nodi camera_ros
    # nota: camera_ros legge tutti i parametri per-nodo dal YAML
    lx_camera = Node(
        package='camera_ros', executable='camera_node',
        name='camera', namespace='stereo/lx',
        parameters=[qos_yaml, config_file], output='screen',
    )
    rx_camera = Node(
        package='camera_ros', executable='camera_node',
        name='camera', namespace='stereo/rx',
        parameters=[qos_yaml, config_file], output='screen',
    )

    # delay 3 sec tra camera lx e rx
    rx_delayed = TimerAction(period=3.0, actions=[rx_camera])
    
    # nodo di benchmark
    # raccoglie eventuali override per metrics_node solo se passati da CLI
    metrics_overrides = {}

    def _check_metrics(arg_names, param_key):
        for name in arg_names:
            val = LaunchConfiguration(name).perform(context).strip()
            if val != '':
                metrics_overrides[param_key] = val
                break

    _check_metrics(['enable_display', 'display'], 'display')

    metrics_params = [config_file]
    if metrics_overrides:
        metrics_params.append(metrics_overrides)

    # determina se avviare metrics_node (controlla sia enable_metrics che metrics)
    metrics_flag = False
    for name in ['enable_metrics', 'metrics']:
        val = LaunchConfiguration(name).perform(context).strip().lower()
        if val in ('true', '1', 'yes', 'on'):
            metrics_flag = True
            break

    nodes = [lx_camera, rx_delayed]
    if metrics_flag:
        metrics_node = Node(
            package='nautilus_camera', executable='metrics_node',
            name='metrics_node',
            parameters=metrics_params,
            output='screen',
        )
        nodes.append(metrics_node)

    return nodes


def generate_launch_description():
    declared_arguments = [
        DeclareLaunchArgument(
            'params_file', default_value='nautilus_camera.yaml',
            description='nome del file params in config/'
        ),
        DeclareLaunchArgument(
            'enable_metrics', default_value='false',
            description='avvia il nodo di benchmark (FPS/jitter/skew)'
        ),
        DeclareLaunchArgument(
            'metrics', default_value='',
            description='alias per enable_metrics'
        ),
        DeclareLaunchArgument(
            'enable_display', default_value='',
            description='apre la finestra OpenCV del metrics_node (default: usa valore YAML)'
        ),
        DeclareLaunchArgument(
            'display', default_value='',
            description='alias per enable_display'
        ),
        OpaqueFunction(function=launch_setup)
    ]

    return LaunchDescription(declared_arguments)
    