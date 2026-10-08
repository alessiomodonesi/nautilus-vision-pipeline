import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource


def generate_launch_description():
    # percorsi dei pacchetti
    camera_pkg = get_package_share_directory('nautilus_camera')
    perception_pkg = get_package_share_directory('nautilus_perception')

    # nodo di acquisizione
    stereo_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(camera_pkg, 'launch', 'stereo_camera.launch.py'))
    )

    # nodo di enhancement
    enhancement_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(perception_pkg, 'launch', 'enhancement.launch.py'))
    )

    # nodo di detection
    detection_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(perception_pkg, 'launch', 'detection.launch.py'))
    )

    return LaunchDescription([
        stereo_launch,
        enhancement_launch,
        detection_launch
    ])