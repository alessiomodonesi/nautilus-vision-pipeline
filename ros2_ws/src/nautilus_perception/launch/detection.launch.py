import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution


def generate_launch_description():
    pkg_dir = get_package_share_directory('nautilus_perception')

    params_file_arg = DeclareLaunchArgument(
        'params_file', default_value='detection_params.yaml',
        description='Nome del file params in config/'
    )
    
    input_type_arg = DeclareLaunchArgument(
        'input_type_override', default_value='raw',
        description="Override input_type: 'raw' | 'enhanced'"
    )
    
    enable_debug_arg = DeclareLaunchArgument(
        'enable_debug', default_value='false',
        description='OpenCV debug window (true/false)'
    )
    
    model_filename_arg = DeclareLaunchArgument(
        'model_filename_override', default_value='yolov8n.pt',
        description='Nome cartella OpenVINO o file .pt in data/weights/'
    )
    
    half_res_arg = DeclareLaunchArgument(
        'half_res_override', default_value='true',
        description='Dimezza il frame prima di YOLO (solo PyTorch)'
    )
    
    imgsz_arg = DeclareLaunchArgument(
        'imgsz_override', default_value='640',
        description='Risoluzione di inferenza, deve combaciare con export'
    )

    params_path = PathJoinSubstitution(
        [pkg_dir, 'config', LaunchConfiguration('params_file')]
    )

    detection_node = Node(
        package='nautilus_perception',
        executable='detection_node',
        name='detection_node',
        output='screen',
        parameters=[
            params_path,
            {
                'input_type': LaunchConfiguration('input_type_override'),
                'enable_debug': LaunchConfiguration('enable_debug'),
                'model_filename': LaunchConfiguration('model_filename_override'),
                'half_res': LaunchConfiguration('half_res_override'),
                'imgsz': LaunchConfiguration('imgsz_override'),
            }
        ]
    )

    return LaunchDescription([
        params_file_arg,
        input_type_arg,
        enable_debug_arg,
        model_filename_arg,
        half_res_arg,
        imgsz_arg,
        detection_node,
    ])
