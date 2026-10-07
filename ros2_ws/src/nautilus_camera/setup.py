import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'nautilus_camera'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # aggiunge i file di launch all'installazione
        (os.path.join('share', package_name, 'launch'), glob(os.path.join('launch', '*launch.[pxy][yma]*'))),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Nautilus',
    maintainer_email='nautilus.unipd@gmail.com',
    description='Stereo camera node for the Nautilus vehicle (runs on the Raspberry Pi hosts).',
    license='Apache-2.0',
    extras_require={'test': ['pytest']},
    entry_points={
        'console_scripts': [
            # registra il nuovo nodo di misurazione
            'metrics_node = nautilus_camera.metrics_node:main',
        ],
    },
)