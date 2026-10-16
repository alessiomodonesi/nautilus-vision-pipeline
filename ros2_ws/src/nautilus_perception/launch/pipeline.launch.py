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

    # modalità waternet: default 'force_off', allineato a enhancement.launch.py
    # e enhancement_node.py. WaterNet gira solo se richiesto esplicitamente,
    # perché è utile solo in post-produzione e non alla navigazione.
    waternet_mode_arg = DeclareLaunchArgument(
        'waternet_mode', default_value='force_off',
        description="auto | force_on | force_off (force_off = solo OpenCV: CLAHE + sharpening)"
    )

    # include_stereo_camera: di default false, perché sulla barca le camere
    # sono già avviate all'accensione da nautilus-vision.service.
    # lanciare pipeline.launch.py deve solo AGGIUNGERE enhancement/detection
    # sopra l'acquisizione già attiva.
    # se invece vuoi fare un test da zero passa include_stereo_camera:=true.
    include_stereo_camera_arg = DeclareLaunchArgument(
        'include_stereo_camera', default_value='false',
        description='Avvia anche camera_ros (true solo se le camere non sono già attive)'
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

    # nodo di acquisizione (condizionale)
    # di default NON viene lanciato perché le camere sono già attive dal boot
    stereo_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(camera_pkg, 'launch', 'stereo_camera.launch.py')),
        launch_arguments={
            'enable_saving':  LaunchConfiguration('enable_saving'),
            'enable_metrics': LaunchConfiguration('enable_metrics'),
        }.items(),
        condition=IfCondition(LaunchConfiguration('include_stereo_camera'))
    )
    
    # nodo di enhancement (condizionale)
    enhancement_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(perception_pkg, 'launch', 'enhancement.launch.py')),
        launch_arguments={'waternet_mode': LaunchConfiguration('waternet_mode')}.items(),
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
        waternet_mode_arg,
        include_stereo_camera_arg,
        model_filename_arg,
        half_res_arg,
        imgsz_arg,
        stereo_launch,
        enhancement_launch,
        detection_launch,
    ])
    