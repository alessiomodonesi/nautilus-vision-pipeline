# nautilus_camera

Pacchetto ROS 2 dedicato all'acquisizione stereoscopica e alla diagnostica telemetrica in tempo reale per il modulo di visione del veicolo **Nautilus** (su host Raspberry Pi 5).

---

## 1. Panoramica del Pacchetto

Il pacchetto si interfaccia direttamente con i due sensori Sony IMX708 (Raspberry Pi Camera Module 3 con autofocus a diottrie regolabili) collegati via bus CSI-2 tramite il driver open-source [`camera_ros`](../camera_ros/README.md).

Le responsabilità principali del pacchetto includono:

1. **Acquisizione Stereoscopica Sincronizzata**: acquisizione video a risoluzione 1280×720 a 5 FPS nominali (`FrameDurationLimits: [200000, 200000]`), con parametri hardware e fotometrici centralizzati in un unico file YAML (`config/camera_params.yaml`).
2. **Diagnostica Telemetrica in Tempo Reale ([`metrics_node.py`](nautilus_camera/metrics_node.py))**: benchmark continuo del flusso visivo con calcolo di FPS effettivi, jitter temporale inter-frame e skew di sincronizzazione stereo tra telecamera sinistra e destra.
3. **Architettura di Salvataggio Zero-Overhead**: la persistenza delle missioni non avviene tramite nodi Python dedicati, bensì tramite registrazione nativa ROS 2 in formato MCAP compresso (`nautilus-bag.service`). Per le necessità di analisi scientifica e per i biologi, i frame JPEG numerati vengono estratti a posteriori tramite lo script [`tools/extract_bag_frames.py`](../../../tools/extract_bag_frames.py), preservando la CPU di bordo durante la navigazione autonoma.

---

## 2. Struttura del Pacchetto

```text
nautilus_camera/
├── config/
│   └── camera_params.yaml          # File unico di configurazione (camera_ros + metrics_node)
├── launch/
│   └── stereo_camera.launch.py     # Launch file acquisizione stereo e diagnostica
├── nautilus_camera/
│   ├── __init__.py
│   └── metrics_node.py             # Nodo diagnostico (FPS, jitter, skew stereo)
├── resource/
│   └── nautilus_camera
├── test/
│   └── test_flake8.py
├── package.xml
├── setup.cfg
└── setup.py
```

---

## 3. Launch File: `stereo_camera.launch.py`

Il file di launch [`launch/stereo_camera.launch.py`](launch/stereo_camera.launch.py) coordina:

* L'avvio di due istanze del nodo `camera_node` di `camera_ros` su namespace distinti:
  * `/stereo/lx/camera` (ID hardware 0, sensore sinistro)
  * `/stereo/rx/camera` (ID hardware 1, sensore destro)
* Un ritardo di sicurezza temporizzato di **6.0 secondi** sull'avvio della camera destra (`TimerAction`), necessario per consentire al driver libcamera di inizializzare stabilmente il primo bus I2C/CSI prima di attivare il secondo.
* L'avvio opzionale di `metrics_node` per la telemetria.

### Argomenti di Lancio Supportati

| Argomento | Default | Descrizione |
| :--- | :---: | :--- |
| `params_file` | `camera_params.yaml` | Nome del file YAML in `config/` |
| `enable_metrics` (alias `metrics`) | `false` | Se `true`, attiva il nodo di monitoraggio `metrics_node` |
| `enable_display` (alias `display`) | `''` (vuoto) | Se specificato (`true`/`false`), sovrascrive la chiave `display` di `metrics_node` |

### Esempi di Utilizzo

```bash
# 1. Avvio standard della sola acquisizione stereo (produzione al boot)
ros2 launch nautilus_camera stereo_camera.launch.py

# 2. Avvio acquisizione con monitoraggio telemetrico attivo a terminale
ros2 launch nautilus_camera stereo_camera.launch.py enable_metrics:=true

# 3. Avvio con finestra grafica OpenCV di affiancamento stereo (richiede monitor/X11)
ros2 launch nautilus_camera stereo_camera.launch.py metrics:=true display:=true
```

---

## 4. Nodo di Benchmark: `metrics_node`

Il nodo [`metrics_node.py`](nautilus_camera/metrics_node.py) è un osservatore passivo non intrusivo:

* Sottoscrive i flussi `/stereo/lx/camera/image_raw` e `/stereo/rx/camera/image_raw` con profilo QoS `IMAGE_SUB_QOS` (`BEST_EFFORT`, depth 5).
* Accoppia le coppie di frame tramite `message_filters.ApproximateTimeSynchronizer` con una tolleranza temporale definita da `sync_slop_sec` (0.05 s).
* Calcola su una finestra mobile di N campioni (`window_size: 30`):
  * **FPS Reali**: frequenza effettiva di arrivo dei frame al secondo.
  * **Jitter Temporale (LX)**: deviazione standard della differenza di timestamp (`header.stamp`) tra frame consecutivi della telecamera sinistra (in millisecondi).
  * **Skew Stereo**: differenza assoluta tra i timestamp dei frame della coppia sinistra-destra (`|t_lx - t_rx|`), espressa come media e picco massimo.
* Stampa periodicamente a log un riepilogo a frequenza fissa (`log_interval_sec: 1.0`).

### Esempio di Log Telemetrico

```text
[metrics_node]: FPS:  5.00 | Jitter(sx):   0.31 ms | Skew(sx-dx): avg  1.15 / max  1.82 ms
```

---

## 5. Configurazione: `camera_params.yaml`

Tutti i parametri hardware del pacchetto sono centralizzati in [`config/camera_params.yaml`](config/camera_params.yaml):

```yaml
# Parametri hardware per camera_ros - Camera Sinistra (lx)
/stereo/lx/camera:
  ros__parameters:
    camera: 0
    width: 1280
    height: 720
    FrameDurationLimits: [200000, 200000]   # 200 ms => 5.0 FPS esatti
    AeEnable: false                         # Blocco auto-exposure
    AwbEnable: false                        # Blocco auto-white-balance
    ExposureTime: 20000                     # 20 ms tempo di esposizione
    ColourGains: [1.5, 1.5]                 # Bilanciamento cromatico fisso
    AfMode: 0                               # Messa a fuoco manuale
    LensPosition: 2.6                       # Diottrie sinistra (compensazione offset +1.05)

# Parametri hardware per camera_ros - Camera Destra (rx)
/stereo/rx/camera:
  ros__parameters:
    camera: 1
    width: 1280
    height: 720
    FrameDurationLimits: [200000, 200000]
    AeEnable: false
    AwbEnable: false
    ExposureTime: 20000
    ColourGains: [1.5, 1.5]
    AfMode: 0
    LensPosition: 1.5                       # Diottrie destra (fuoco a ~0.65 m)

# Parametri del nodo di benchmark telemetrico
/**/metrics_node:
  ros__parameters:
    left_topic: '/stereo/lx/camera/image_raw'
    right_topic: '/stereo/rx/camera/image_raw'
    sync_slop_sec: 0.05
    window_size: 30
    log_interval_sec: 1.0
    display: false
```

### Note sulla Calibrazione Ottica e sul Lock Fotometrico

* **Offset Meccanico delle Lenti**: La lente sinistra richiede `LensPosition: 2.6` diottrie rispetto alle `1.5` della destra per ottenere il fuoco identico a ~0.65 m, a causa di una tolleranza costruttiva rilevata sperimentalmente (vedi documentazione in [`nautilus_perception/detection/DEBUG.md`](../nautilus_perception/nautilus_perception/detection/DEBUG.md)).
* **Lock Fotometrico a Runtime ([`lock_cameras.py`](../../../deploy/lock_cameras.py))**: A causa di un limite noto di `camera_ros` su Raspberry Pi 5 che impedisce l'applicazione di `AeEnable` e `AwbEnable` direttamente dal launch, lo script esterno `lock_cameras.py` viene eseguito al boot da `lock-cameras.service` riapplicando i parametri fotometrici tramite chiamate a servizio `set_parameters` su entrambe le camere.

---

## 6. Integrazione con i Profili QoS

Il pacchetto adotta i profili di comunicazione centralizzati in [`nautilus_common`](../nautilus_common/README.md):

* I nodi `camera_ros` C++ leggono [`config/qos_overrides.yaml`](../nautilus_common/config/qos_overrides.yaml) via `--params-file`, pubblicando `/stereo/{lx,rx}/camera/image_raw` con profilo `BEST_EFFORT`, `history: keep_last`, `depth: 1`, `durability: volatile`.
* Il nodo `metrics_node` importa `IMAGE_SUB_QOS` da `nautilus_common.qos_profiles` (`BEST_EFFORT`, `depth: 5`) per garantire un buffer adeguato alla sincronizzazione temporale delle immagini.
