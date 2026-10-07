import os
from glob import glob
from setuptools import setup

package_name = 'nautilus_perception'

setup(
    name=package_name,
    version='0.0.0',
    packages=[
        package_name, 
        f'{package_name}.enhancement', 
        f'{package_name}.enhancement.waternet',
        f'{package_name}.detection',
        f'{package_name}.data',
    ],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob(os.path.join('launch', '*launch.[pxy][yma]*'))),
        (os.path.join('share', package_name, 'data'), ['nautilus_perception/data/stereo_calib.npz']),
        (os.path.join('share', package_name, 'data', 'weights'), glob('nautilus_perception/data/weights/*.*')),
        (os.path.join('share', package_name, 'data', 'weights', 'best_openvino_model'), glob('nautilus_perception/data/weights/best_openvino_model/*.*')),
        (os.path.join('share', package_name, 'data', 'weights', 'yolov8n_openvino_model'), glob('nautilus_perception/data/weights/yolov8n_openvino_model/*.*')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Nautilus',
    maintainer_email='nautilus.unipd@gmail.com',
    description='Nodo di enhancement per Nautilus Camera',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'enhancement_node = nautilus_perception.enhancement_node:main',
            'detection_node = nautilus_perception.detection_node:main',
        ],
    },
)
