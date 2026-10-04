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
        f'{package_name}.enhancement.waternet'
    ],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'enhancement'), ['nautilus_perception/enhancement/weights.pt']),
        (os.path.join('share', package_name, 'launch'), glob(os.path.join('launch', '*launch.[pxy][yma]*'))),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Il Tuo Nome',
    maintainer_email='tua.email@example.com',
    description='Nodo di enhancement per Nautilus Camera',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'enhancement_node = nautilus_perception.enhancement_node:main',
        ],
    },
)
