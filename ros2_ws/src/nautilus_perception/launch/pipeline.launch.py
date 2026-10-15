import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch.conditions import IfCondition


def generate_launch_description():
    # percorsi dei pacchetti
    camera_pkg = get_package_share_directory('nautilus_camera')
    perception_pkg = get_package_share_directory('nautilus_perception')

    # dichiarazione degli argomenti di lancio
    enable_enhancement_arg = DeclareLaunchArgument(
        'enable_enhancement', default_value='true',
        description='Set to true to launch the enhancement node'
    )
    
    enable_detection_arg = DeclareLaunchArgument(
        'enable_detection', default_value='true',
        description='Set to true to launch the detection node'
    )
    
    enable_saving_arg = DeclareLaunchArgument(
        'enable_saving', default_value='true',
        description='Enable saving to disk'
    )
    
    enable_metrics_arg = DeclareLaunchArgument(
        'enable_metrics', default_value='false',
        description='Enable the benchmark node'
    )
    
    enable_debug_arg = DeclareLaunchArgument(
        'enable_debug', default_value='false',
        description='Enable OpenCV debug window in detection node (false for benchmarks)'
    )
    
    params_file_arg = DeclareLaunchArgument(
        'params_file', default_value='detection_params.yaml',
        description='Nome file params detection (detection_params_pt.yaml | detection_params_ov.yaml)'
    )

    # determina l'input_type dinamicamente in base ad enable_enhancement
    dynamic_input_type = PythonExpression(
        ["'enhanced' if '", LaunchConfiguration('enable_enhancement'), "' == 'true' else 'raw'"]
    )
    
    model_filename_arg = DeclareLaunchArgument(
        'model_filename_override', default_value='yolov8n.pt',
        description='Nome modello in data/weights/'
    )
    
    half_res_arg = DeclareLaunchArgument(
        'half_res_override', default_value='true',
    )
    
    imgsz_arg = DeclareLaunchArgument(
        'imgsz_override', default_value='640',
    )

    # nodo di acquisizione (sempre attivo)
    stereo_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(camera_pkg, 'launch', 'stereo_camera.launch.py')),
        launch_arguments={
            'enable_saving':  LaunchConfiguration('enable_saving'),
            'enable_metrics': LaunchConfiguration('enable_metrics'),
        }.items()
    )

    # nodo di enhancement (condizionale)
    enhancement_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(perception_pkg, 'launch', 'enhancement.launch.py')),
        launch_arguments={'waternet_mode': 'force_off'}.items(),
        condition=IfCondition(LaunchConfiguration('enable_enhancement'))
    )

    # nodo di detection (condizionale)
    detection_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(perception_pkg, 'launch', 'detection.launch.py')
        ),
        launch_arguments={
            'input_type_override': dynamic_input_type,
            'enable_debug': LaunchConfiguration('enable_debug'),
            'params_file': LaunchConfiguration('params_file'),
            'model_filename_override': LaunchConfiguration('model_filename_override'),
            'half_res_override': LaunchConfiguration('half_res_override'),
            'imgsz_override': LaunchConfiguration('imgsz_override'),
        }.items(),
        condition=IfCondition(LaunchConfiguration('enable_detection'))
    )

    return LaunchDescription([
        enable_enhancement_arg,
        enable_detection_arg,
        enable_saving_arg,
        enable_metrics_arg,
        enable_debug_arg,
        params_file_arg,
        model_filename_arg,
        half_res_arg,
        imgsz_arg,
        stereo_launch,
        enhancement_launch,
        detection_launch,
    ])
