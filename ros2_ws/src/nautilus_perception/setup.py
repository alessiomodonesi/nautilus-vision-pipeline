import os
from glob import glob
from setuptools import setup

package_name = 'nautilus_perception'


def ov_weights_dirs():
    """Ritorna [(dest, [files])] per ogni sottocartella in data/weights/.

    Così l'install copre automaticamente tutti i modelli OpenVINO
    (yolov8n_openvino_640_fp32, yolov8n_openvino_640_int8, ...) senza
    doverli elencare a mano ogni volta che si aggiunge/rinomina uno.
    """
    base = 'nautilus_perception/data/weights'
    entries = []
    for entry in sorted(os.scandir(base), key=lambda e: e.name):
        if not entry.is_dir():
            continue
        dest = os.path.join('share', package_name, 'data', 'weights', entry.name)
        files = glob(os.path.join(base, entry.name, '*.*'))
        if files:
            entries.append((dest, files))
    return entries


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
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
        (os.path.join('share', package_name, 'launch'),
         glob(os.path.join('launch', '*launch.[pxy][yma]*'))),
        (os.path.join('share', package_name, 'data'),
         ['nautilus_perception/data/stereo_calib_720p.npz']),
        # file al primo livello di weights/ (yolov8n.pt, best.pt, waternet.pt)
        (os.path.join('share', package_name, 'data', 'weights'),
         glob('nautilus_perception/data/weights/*.*')),
        # tutte le sottodirectory OpenVINO, scoperte dinamicamente
        *ov_weights_dirs(),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Nautilus Software Team',
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