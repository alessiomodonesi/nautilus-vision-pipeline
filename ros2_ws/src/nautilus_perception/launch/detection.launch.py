import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration


def launch_setup(context, *args, **kwargs):
    pkg_dir = get_package_share_directory('nautilus_perception')
    params_file = LaunchConfiguration('params_file').perform(context)
    params_path = os.path.join(pkg_dir, 'config', params_file)

    # dizionario degli override: solo gli argomenti esplicitamente passati
    # a riga di comando (non vuoti) sovrascrivono il file YAML.
    overrides = {}

    def _check_param(arg_names, param_key):
        for name in arg_names:
            val = LaunchConfiguration(name).perform(context).strip()
            if val != '':
                overrides[param_key] = val
                break

    _check_param(['enable_debug', 'debug'], 'enable_debug')
    _check_param(['input_type_override', 'input_type'], 'input_type')
    _check_param(['model_filename_override', 'model_filename'], 'model_filename')
    _check_param(['half_res_override', 'half_res'], 'half_res')
    _check_param(['imgsz_override', 'imgsz'], 'imgsz')

    node_params = [params_path]
    if overrides:
        node_params.append(overrides)

    # nodo di detection
    # i parametri del file YAML hanno la priorità nel caso non vengano specificati argomenti di lancio.
    # gli argomenti di lancio sovrascrivono il file YAML solo se esplicitati nel comando.
    detection_node = Node(
        package='nautilus_perception',
        executable='detection_node',
        name='detection_node',
        output='screen',
        parameters=node_params
    )

    return [detection_node]


def generate_launch_description():
    declared_arguments = [
        DeclareLaunchArgument(
            'params_file', default_value='detection_params.yaml',
            description='nome del file params in config/'
        ),
        DeclareLaunchArgument(
            'enable_debug', default_value='',
            description='finestra di debug OpenCV (default: usa valore YAML)'
        ),
        DeclareLaunchArgument(
            'debug', default_value='',
            description='alias per enable_debug'
        ),
        DeclareLaunchArgument(
            'model_filename_override', default_value='',
            description='nome cartella OpenVINO o file .pt (default: usa valore YAML)'
        ),
        DeclareLaunchArgument(
            'model_filename', default_value='',
            description='alias per model_filename_override'
        ),
        DeclareLaunchArgument(
            'half_res_override', default_value='',
            description='dimezza il frame prima di YOLO (default: usa valore YAML)'
        ),
        DeclareLaunchArgument(
            'half_res', default_value='',
            description='alias per half_res_override'
        ),
        DeclareLaunchArgument(
            'imgsz_override', default_value='',
            description='risoluzione di inferenza (default: usa valore YAML)'
        ),
        DeclareLaunchArgument(
            'imgsz', default_value='',
            description='alias per imgsz_override'
        ),
        DeclareLaunchArgument(
            'input_type_override', default_value='',
            description="override input_type: 'raw' | 'enhanced' (default: usa valore YAML)"
        ),
        DeclareLaunchArgument(
            'input_type', default_value='',
            description='alias per input_type_override'
        ),
        OpaqueFunction(function=launch_setup)
    ]

    return LaunchDescription(declared_arguments)
    