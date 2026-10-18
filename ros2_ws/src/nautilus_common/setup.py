from setuptools import setup
package_name = 'nautilus_common'
setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', ['config/qos_overrides.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Nautilus Software Team',
    maintainer_email='nautilus.unipd@gmail.com',
    license='Apache-2.0',
)