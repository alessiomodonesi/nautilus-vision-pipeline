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
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Nautilus Software Team',
    maintainer_email='TODO@example.com',
    description='Stereo camera node for the Nautilus vehicle (runs on the Raspberry Pi hosts).',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            # TODO: register nodes here as they are implemented, e.g.
            #   'camera_node = nautilus_camera.camera_node:main',
        ],
    },
)
