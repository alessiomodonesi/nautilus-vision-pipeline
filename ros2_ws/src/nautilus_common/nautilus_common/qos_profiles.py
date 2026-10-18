"""QoS profiles caricati da config/qos_overrides.yaml.

il file YAML è la single source of truth, allineata alla repo Nautilus.
i nodi C++ (camera_ros) lo ricevono via --params-file; i nodi Python lo
leggono qui per costruire i QoSProfile."""
import os
import yaml
from ament_index_python.packages import get_package_share_directory
from rclpy.qos import (
    QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
)

_RELIABILITY = {
    'best_effort': ReliabilityPolicy.BEST_EFFORT,
    'reliable':    ReliabilityPolicy.RELIABLE,
}
_DURABILITY = {
    'volatile':        DurabilityPolicy.VOLATILE,
    'transient_local': DurabilityPolicy.TRANSIENT_LOCAL,
}
_HISTORY = {
    'keep_last': HistoryPolicy.KEEP_LAST,
    'keep_all':  HistoryPolicy.KEEP_ALL,
}


def _load_overrides():
    path = os.path.join(
        get_package_share_directory('nautilus_common'),
        'config', 'qos_overrides.yaml',
    )
    with open(path, 'r') as f:
        return yaml.safe_load(f).get('qos_overrides', {})


_OVERRIDES = _load_overrides()


def get_qos(topic: str, direction: str = 'publisher') -> QoSProfile:
    """QoSProfile per `topic` secondo qos_overrides.yaml.

    fallback: best_effort / keep_last / depth 5 / volatile se il topic
    non è nel YAML. nessun lancio di eccezioni: il nodo deve restare
    avviabile anche con un YAML incompleto (es. topic locali di test)."""
    entry = _OVERRIDES.get(topic, {}).get(direction, {})
    return QoSProfile(
        reliability=_RELIABILITY.get(entry.get('reliability', 'best_effort'),
                                     ReliabilityPolicy.BEST_EFFORT),
        history=_HISTORY.get(entry.get('history', 'keep_last'),
                             HistoryPolicy.KEEP_LAST),
        depth=int(entry.get('depth', 5)),
        durability=_DURABILITY.get(entry.get('durability', 'volatile'),
                                   DurabilityPolicy.VOLATILE),
    )

IMAGE_QOS     = get_qos('/stereo/lx/camera/image_raw', 'publisher')
DETECTION_QOS = get_qos('/stereo_down/targets', 'publisher')
DEBUG_QOS     = get_qos('/stereo_down/timings', 'publisher')
