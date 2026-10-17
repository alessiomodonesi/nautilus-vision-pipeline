# nautilus_common

Pacchetto ROS 2 di utility condivise per la suite **Nautilus**.

Questo pacchetto nasce per centralizzare costanti, configurazioni e profili di comunicazione (QoS) che devono essere identici in tutti i nodi della pipeline, sia essi scritti in Python che in C++ (tramite YAML).

## Struttura del Pacchetto

```text
nautilus_common/
├── nautilus_common/
│   ├── __init__.py
│   └── qos_profiles.py       # Definizione centralizzata dei profili QoS
├── resource/
│   └── nautilus_common
├── package.xml
└── setup.py
```

---

## Profili QoS (Quality of Service)

ROS 2 utilizza i profili QoS per definire le regole di consegna dei messaggi. L'uso di profili non allineati tra publisher e subscriber può causare **la mancata ricezione dei dati** (senza errori espliciti) o introdurre latenze indesiderate.

In `nautilus_common/qos_profiles.py` sono definiti tre profili standard:

### 1. `IMAGE_QOS`

* **Reliability:** `BEST_EFFORT`
* **History:** `KEEP_LAST`
* **Depth:** `5`
* **Durability:** `VOLATILE`

**Utilizzo:** Flussi video (raw o enhanced).
**Motivazione:** La latenza è il fattore critico. Un frame video perso non compromette il sistema (il frame successivo arriva dopo 200 ms) e non deve bloccare il publisher in attesa di conferme (ACK). La profondità 5 è un buon compromesso per permettere a `message_filters` di sincronizzare i flussi stereo senza accumulare ritardo.

### 2. `DETECTION_QOS`

* **Reliability:** `RELIABLE`
* **History:** `KEEP_LAST`
* **Depth:** `10`
* **Durability:** `VOLATILE`

**Utilizzo:** Pubblicazione dei target rilevati (`/stereo_down/targets`).
**Motivazione:** Un target (es. un pesce o un detrito) è un dato fondamentale per i biologi e per la logica di navigazione. La perdita di un rilevamento non è accettabile, quindi si forza la consegna garantita (`RELIABLE`) con un buffer di 10 messaggi.

### 3. `DEBUG_QOS`

* **Reliability:** `BEST_EFFORT`
* **History:** `KEEP_LAST`
* **Depth:** `10`
* **Durability:** `VOLATILE`

**Utilizzo:** Telemetria e tempi di esecuzione (`/stereo_down/timings`).
**Motivazione:** Sono dati diagnostici. Se un pacchetto viene perso a causa di congestione, il sistema non deve rallentare per ritrasmetterlo.

---

## Utilizzo nei Nodi Python

Per garantire l'allineamento, i nodi Python importano i profili direttamente da questo pacchetto:

```python
from nautilus_common.qos_profiles import IMAGE_QOS, DETECTION_QOS, DEBUG_QOS

# Esempio: iscrizione a un'immagine
self.subscription = self.create_subscription(
    Image,
    '/stereo/lx/camera/image_raw',
    self.image_callback,
    IMAGE_QOS
)

# Esempio: pubblicazione di un target
self.publisher = self.create_publisher(
    Detection2DArray,
    '/stereo_down/targets',
    DETECTION_QOS
)
```

## Integrazione con Nodi C++ (YAML)

I nodi scritti in C++ (come `camera_ros`) non possono importare moduli Python. Per garantire l'allineamento, i loro file di configurazione YAML devono specificare il `qos_overrides` in modo da rispecchiare i profili definiti qui (es. `best_effort` con `depth: 5` per le immagini).
