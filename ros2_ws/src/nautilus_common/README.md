# nautilus_common

Pacchetto ROS 2 di utility condivise per la suite **Nautilus**.

Questo pacchetto centralizza i profili di comunicazione (QoS) di tutta la
pipeline in un'unica fonte di verità: `config/qos_overrides.yaml`. I nodi
Python li leggono tramite il loader `qos_profiles.py`, i nodi C++ li
ricevono direttamente come `--params-file`. Nessuna duplicazione di valori
QoS tra un nodo e l'altro.

## Struttura del Pacchetto

```text
nautilus_common/
├── config/
│   └── qos_overrides.yaml    # SSOT dei profili QoS (formato ROS standard)
├── nautilus_common/
│   ├── __init__.py
│   └── qos_profiles.py       # Loader: YAML → QoSProfile + costanti di comodo
├── resource/
│   └── nautilus_common
├── package.xml
└── setup.py
```

---

## Architettura: SSOT + Loader

`config/qos_overrides.yaml` è la **single source of truth** dei QoS della
pipeline. Segue la struttura standard ROS, compatibile con `--params-file`:

```yaml
/**:
  ros__parameters:
    qos_overrides:
      /stereo/lx/camera/image_raw:
        publisher:
          reliability: best_effort
          history: keep_last
          depth: 1
          durability: volatile
      /stereo_down/targets:
        publisher:
          reliability: reliable
          history: keep_last
          depth: 10
          durability: volatile
      # ...
```

Due modalità di consumo, una sola fonte:

1. **Nodi C++** (es. `camera_ros`): il YAML viene passato al nodo come
   `--params-file`. `rclcpp` interpreta nativamente la chiave
   `qos_overrides` e applica i profili.
2. **Nodi Python**: `rclpy` non ha un meccanismo equivalente. Il modulo
   `qos_profiles.py` legge lo **stesso** YAML all'import e costruisce i
   `QoSProfile` corrispondenti, esposti come costanti.

Estratto del loader in `qos_profiles.py`:

```python
def _load_overrides():
    path = os.path.join(
        get_package_share_directory('nautilus_common'),
        'config', 'qos_overrides.yaml',
    )
    with open(path, 'r') as f:
        data = yaml.safe_load(f)
    # struttura ROS: /**: {ros__parameters: {qos_overrides: {...}}}
    return data.get('/**', {}).get('ros__parameters', {}).get('qos_overrides', {})

_OVERRIDES = _load_overrides()


def get_qos(topic: str, direction: str = 'publisher') -> QoSProfile:
    entry = _OVERRIDES.get(topic, {}).get(direction, {})
    # ... costruisce QoSProfile da entry, con fallback se topic assente
```

**Fallback**: se il topic non è nel YAML, `get_qos` restituisce
`best_effort / keep_last / depth 5 / volatile`. Nessuna eccezione: un nodo
deve restare avviabile anche con un YAML incompleto (utile per topic
locali di test). Se ti serve una QoS diversa dal fallback, **aggiungi il
topic al YAML**, non hardcodare.

---

## Profili esposti

`qos_profiles.py` espone 5 costanti pronte all'uso:

| Costante | Topic YAML (`direction`) | Reliability | Depth | Durability |
| --- | --- | --- | --- | --- |
| `IMAGE_PUB_QOS` | `/stereo/lx/camera/image_raw` (publisher) | `BEST_EFFORT` | 1 | `VOLATILE` |
| `IMAGE_SUB_QOS` | *(hardcoded)* | `BEST_EFFORT` | 5 | `VOLATILE` |
| `ENHANCED_PUB_QOS` | `/stereo/lx/image_enhanced` (publisher) | `BEST_EFFORT` | 1 | `VOLATILE` |
| `DETECTION_QOS` | `/stereo_down/targets` (publisher) | `RELIABLE` | 10 | `VOLATILE` |
| `DEBUG_QOS` | `/stereo_down/timings` (publisher) | `BEST_EFFORT` | 10 | `VOLATILE` |

Le prime tre vengono dal YAML. `IMAGE_SUB_QOS` è l'unica costante
hardcoded, perché il depth "giusto" per un subscriber con `message_filters`
è una scelta di design, non un valore che ha senso duplicare per ogni topic:

- **`depth 1` sui publisher real-time** = scarta i frame vecchi, elabori
  sempre l'ultimo (giusto per non accumulare latenza)
- **`depth 5` sui subscriber con `message_filters`** = buffer di ~1 s a
  5 Hz, sufficiente per accoppiare lx/rx anche con jitter

---

## Perché publisher `depth 1` e subscriber `depth 5`

Un `depth 1` sul publisher significa che il driver camera tiene al massimo
1 frame in coda per subscriber. Se il subscriber è occupato, il frame
successivo sovrascrive il precedente: nessun accumulo di latenza. È il
comportamento corretto per uno stream real-time dove la freschezza conta
più della completezza.

Un `depth 1` anche sul subscriber sarebbe però troppo aggressivo: se il
callback è occupato (enhancement ~65 ms, detection ~250–1000 ms), il frame
in coda viene rimpiazzato prima di essere processato e perdi quello
precedente. Con `depth 5` hai margine.

Per questo la costante è splittata: `IMAGE_PUB_QOS` (depth 1) per i
publisher, `IMAGE_SUB_QOS` (depth 5) per i subscriber.

---

## Uso nei nodi Python

```python
from nautilus_common.qos_profiles import (
    IMAGE_PUB_QOS, IMAGE_SUB_QOS, ENHANCED_PUB_QOS,
    DETECTION_QOS, DEBUG_QOS,
)

# Publisher real-time (drop frame vecchi)
self.publisher = self.create_publisher(Image, 'image_enhanced', ENHANCED_PUB_QOS)

# Subscriber con message_filters (buffer per sync)
self.left_sub = message_filters.Subscriber(
    self, Image, left_topic, qos_profile=IMAGE_SUB_QOS
)

# Subscriber real-time senza message_filters (elabora solo il più recente)
self.subscription = self.create_subscription(
    Image, 'image_raw', self.image_callback, IMAGE_PUB_QOS
)

# Target (garantito)
self.detection_pub = self.create_publisher(
    Detection2DArray, '/stereo_down/targets', DETECTION_QOS
)

# Telemetria (best effort)
self.timing_pub = self.create_publisher(
    Float32MultiArray, '/stereo_down/timings', DEBUG_QOS
)
```

Per un topic non coperto dalle costanti, usa `get_qos`:

```python
from nautilus_common.qos_profiles import get_qos

qos = get_qos('/mio/topic/custom', 'subscriber')
```

---

## Integrazione con Nodi C++ (YAML)

I nodi C++ non possono importare moduli Python. Ricevono il file YAML
come `--params-file`, e `rclcpp` applica nativamente le `qos_overrides`.
Nei launch file:

```python
from ament_index_python.packages import get_package_share_directory
import os

qos_yaml = os.path.join(
    get_package_share_directory('nautilus_common'),
    'config', 'qos_overrides.yaml',
)

Node(
    package='camera_ros',
    executable='camera_node',
    parameters=[qos_yaml, config_file],  # il YAML globale va PRIMA
    ...
)
```

L'ordine conta: se `config_file` contiene `qos_overrides` locali per gli
stessi topic, questi **sovrascrivono** quelli globali. Per questo
`nautilus_camera.yaml` **non** contiene più `qos_overrides`: la SSOT è una
sola.

---

## Aggiungere un nuovo topic

1. Apri `config/qos_overrides.yaml`
2. Aggiungi l'entry sotto `qos_overrides:`, con la struttura
   `/{topic}/{publisher|subscriber}/...`
3. Se il topic serve da costante in Python, aggiungila in
   `qos_profiles.py` con `get_qos('/mio/topic', 'publisher')`
4. Rebuild (`--symlink-install` per vedere le modifiche a caldo)

Non aggiungere `qos_overrides` nei YAML locali dei nodi: finiresti con
due fonti che possono divergere, e l'ultima delle due a essere caricata
vince. Se il nodo è C++ e il launch non espone il YAML globale, il
problema è nel launch, non nel YAML locale.

---

## Verifica

Dopo aver modificato la QoS:

```bash
# la entry è presente e valida
QOS_YAML="$(ros2 pkg prefix nautilus_common)/share/nautilus_common/config/qos_overrides.yaml"
python3 -c "import yaml; d=yaml.safe_load(open('$QOS_YAML')); \
    print(d['/**']['ros__parameters']['qos_overrides']['/mio/topic'])"

# la QoS effettiva sul topic
ros2 topic info /mio/topic -v | grep -E 'Reliability|Depth|Durability'
```

Se la QoS osservata non corrisponde a quella nel YAML:

- topic sbagliato nel YAML (path esatto, con `/` iniziale)
- publisher che non è né C++ via `--params-file` né un nodo Python che usa
  le costanti / `get_qos`
- YAML installato diverso dal source (`diff` per confermare,
  `--symlink-install` per evitare il problema)

---

## Riferimenti

- [ROS 2 QoS concepts](https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Quality-of-Service-Settings.html)
- [CycloneDDS QoS override](https://github.com/ros2/rmw_cyclonedds#qos-overrides)
- Applicazione nella pipeline: `nautilus_camera/README.md`,
  `nautilus_perception/README.md`
