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
        'enable_enhancement',
        default_value='true',
        description='Set to true to launch the enhancement node'
    )
    
    enable_detection_arg = DeclareLaunchArgument(
        'enable_detection',
        default_value='true',
        description='Set to true to launch the detection node'
    )
    
    
    # determina l'input_type dinamicamente in base ad enable_enhancement
    dynamic_input_type = PythonExpression(
        ["'enhanced' if '", LaunchConfiguration('enable_enhancement'), "' == 'true' else 'raw'"]
    )

    # nodo di acquisizione (sempre attivo)
    stereo_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(camera_pkg, 'launch', 'stereo_camera.launch.py'))
    )

    # nodo di enhancement (condizionale)
    enhancement_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(perception_pkg, 'launch', 'enhancement.launch.py')),
        condition=IfCondition(LaunchConfiguration('enable_enhancement'))
    )

    # nodo di detection (condizionale)
    detection_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(perception_pkg, 'launch', 'detection.launch.py')),
        launch_arguments={'input_type_override': dynamic_input_type}.items(),
        condition=IfCondition(LaunchConfiguration('enable_detection'))
    )

    return LaunchDescription([
        enable_enhancement_arg,
        enable_detection_arg,
        stereo_launch,
        enhancement_launch,
        detection_launch
    ])
    