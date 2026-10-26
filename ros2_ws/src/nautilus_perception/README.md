# nautilus_perception

Pacchetto ROS 2 dedicato all'elaborazione visiva, all'enhancement delle immagini subacquee e all'object detection con stima metrica della distanza 3D per il veicolo **Nautilus**.

Il pacchetto è ottimizzato per l'esecuzione real-time su target **Raspberry Pi 5** con accelerazione Intel OpenVINO.

---

## 1. Struttura del Pacchetto

```text
nautilus_perception/
├── config/
│   └── detection_params.yaml       # Parametri runtime per detection_node
├── data/
│   ├── stereo_calib_720p.npz       # Calibrazione stereo attiva (1280x720, RMS 0.125 px)
│   ├── stereo_calib_480p.npz       # Calibrazione legacy (riferimento)
│   └── weights/                    # Pesi YOLOv8 (.pt e OpenVINO models)
│       ├── yolov8n.pt
│       ├── yolov8n_640_fp32_openvino_model/
│       ├── yolov8n_640_int8_openvino_model/
│       ├── yolov8n_416_int8_openvino_model/
│       └── best_416_fp32_openvino_model/
├── launch/
│   ├── pipeline.launch.py          # Launch integrato (enhancement + detection + camere)
│   ├── detection.launch.py         # Launch del solo nodo di detection
│   ├── enhancement.launch.py       # Launch del solo nodo di enhancement
│   └── local_test_enhancement.launch.py # Test locale enhancement su singola immagine
├── nautilus_perception/
│   ├── __init__.py
│   ├── detection_node.py           # Nodo ROS 2 di Detection e Stereovisione 3D
│   ├── enhancement_node.py         # Nodo ROS 2 di Enhancement
│   ├── detection/                  # Libreria core di Computer Vision e Stereo Matching
│   │   ├── core_detection.py       # SparseBlockMatcher, DenseStereoMatcher, YoloDetector
│   │   ├── config.py               # Parametri ottici geometrici (StereoConfig)
│   │   ├── calibration/            # Tooling di calibrazione ChArUco e find_focus
│   │   ├── README.md               # Documentazione del modulo detection core
│   │   └── DEBUG.md                # Note di debug calibrazione e offset lenti
│   └── enhancement/                # Algoritmi di miglioramento immagine
│       ├── core_enhancement.py     # Pipeline CLAHE + Laplacian Sharpening
│       └── waternet/               # Modello neurale WaterNet (PyTorch)
├── package.xml
├── setup.cfg
└── setup.py
```

---

## 2. Modulo di Enhancement (`enhancement_node`)

Il nodo [`enhancement_node.py`](nautilus_perception/enhancement_node.py) elabora i flussi stereo raw provenienti da `camera_ros` per migliorare la visibilità in ambienti subacquei torbidi.

### Algoritmo e Modalità Operative

Il modulo supporta tre modalità di funzionamento tramite il parametro `waternet_mode`:

- **`force_off` (Default di produzione)**: Disabilita la rete neurale WaterNet ed esegue esclusivamente **Laplacian Sharpening + CLAHE** (OpenCV deterministico). Questo approccio richiede solo **~65 ms per frame**, risultando sostenibile sul processore ARM del Raspberry Pi 5.
- **`auto`**: Rileva l'hardware disponibile. Se trova accelerazione GPU (CUDA o Apple Silicon MPS) attiva WaterNet; su CPU ARM fa fallback su CLAHE + Sharpening.
- **`force_on`**: Forza l'esecuzione del modello profondo WaterNet anche su CPU. **Non idoneo per l'uso real-time**: su Raspberry Pi 5 richiede **~70.6 secondi per frame** (framerate effettivo 0.01 FPS), comportando un ritardo inaccettabile.

### Benchmark di Confronto (Target Raspberry Pi 5)

| Parametro | `force_off` (Sharpening + CLAHE) | `force_on` (WaterNet su CPU) |
| :--- | :---: | :---: |
| **Latenza di Calcolo** | **~65.3 – 67.1 ms** | **~70,658 ms (~70.6 s)** |
| **Throughput Sostenibile** | Compatibile con streaming | Inutilizzabile in navigazione |
| **Destinazione d'Uso** | **A bordo veicolo (crociera)** | **Post-missione su workstation** |

### Avvio dell'Enhancement

```bash
# Avvio standard di produzione (force_off)
ros2 launch nautilus_perception enhancement.launch.py

# Test su singola immagine fissa con calcolo delay
ros2 launch nautilus_perception local_test_enhancement.launch.py
```

---

## 3. Modulo di Detection e Stereovisione 3D (`detection_node`)

Il nodo [`detection_node.py`](nautilus_perception/detection_node.py) implementa un'architettura **Detect-Then-Range** progettata per minimizzare il consumo di CPU:

1. **Sincronizzazione Stereo**: Sottoscrive i flussi video sinistro e destro (`raw` o `enhanced`) tramite `message_filters.ApproximateTimeSynchronizer` (`sync_slop_sec: 0.05`).
2. **Rettifica Geometrica**: Applica le mappe di rettifica epipolare precalcolate (`stereo_calib_720p.npz`) con `cv2.remap`.
3. **Inferenza YOLOv8 (Camera Sinistra)**: Esegue il modello YOLOv8 Nano unicamente sul frame sinistro rettificato, individuando le classi dei target marini e i relativi bounding box 2D.
4. **Stima Metrica della Distanza 3D ([`SparseBlockMatcher`](nautilus_perception/detection/core_detection.py))**:
   - Invece di calcolare la disparità densa su tutti i pixel (troppo costosa su CPU), calcola la disparità epipolare tramite Normalized Cross-Correlation (NCC) solo in corrispondenza degli oggetti rilevati.
   - Per garantire robustezza contro riflessi o trasparenze, campiona **5 punti** (il centroide e 4 punti distribuiti sugli assi) e seleziona la **mediana** delle disparità valide.
   - Calcola le coordinate 3D $(X, Y, Z)$ nel sistema di riferimento ottico della telecamera sinistra:
     $$Z = \frac{f_x \cdot B}{d}, \quad X = \frac{(u - c_x) \cdot Z}{f_x}, \quad Y = \frac{(v - c_y) \cdot Z}{f_y}$$
     dove $f_x = 1500.89\text{ px}$ e $B = 0.12017\text{ m}$.
5. **Pubblicazione Dati**:
   - `/stereo_down/targets` (`vision_msgs/Detection2DArray` con QoS `RELIABLE`): pubblica i bounding box 2D uniti alle coordinate 3D $(X, Y, Z)$ memorizzate nei campi `bbox.center.position`.
   - `/stereo_down/timings` (`std_msgs/Float32MultiArray` con QoS `BEST_EFFORT`): pubblica la scomposizione dei tempi di calcolo `[pre_ms, infer_ms, post_ms, total_ms]`.

---

## 4. Parametri di Configurazione (`detection_params.yaml`)

Tutti i parametri di runtime sono definiti in [`config/detection_params.yaml`](config/detection_params.yaml):

```yaml
detection_node:
  ros__parameters:
    # Modello di inferenza (directory OpenVINO esportata in data/weights/)
    model_filename: 'yolov8n_640_fp32_openvino_model'
    half_res: false             # Dimezzamento risoluzione (false per OpenVINO)
    imgsz: 640                  # Dimensione tensore di ingresso (640x640)
    conf_threshold: 0.4         # Soglia di confidenza minima
    input_type: 'raw'           # 'raw' oppure 'enhanced'
    enable_debug: false         # Visualizzazione finestra OpenCV di debug
    num_threads: 2              # Thread CPU allocati a OpenVINO/OMP
    sync_slop_sec: 0.05         # Tolleranza sincronizzazione stereo (s)
```

> [!TIP]
> **Modello Consigliato**: I benchmark hanno confermato che **`yolov8n_640_fp32_openvino_model`** offre le migliori prestazioni su Raspberry Pi 5 (~2.3 FPS, 347 ms di inferenza, mAP identica a PyTorch). I modelli quantizzati INT8 (`_int8_`) presentano un'anomalia di runtime nel plugin CPU ARM e sono al momento sconsigliati.

---

## 5. Profili di Comunicazione QoS

Il pacchetto importa le definizioni centralizzate da [`nautilus_common.qos_profiles`](../nautilus_common/nautilus_common/qos_profiles.py):

| Nodo | Topic | Direzione | Profilo QoS | Motivazione Progettuale |
| :--- | :--- | :---: | :--- | :--- |
| `enhancement_node` | `/stereo/{lx,rx}/camera/image_raw` | Sub | `BEST_EFFORT` (depth 1) | Scarta i frame obsoleti elaborando solo il più recente |
| `enhancement_node` | `/stereo/{lx,rx}/image_enhanced` | Pub | `BEST_EFFORT` (depth 1) | Trasmette direttamente il frame migliore alla detection |
| `detection_node` | `/stereo/{lx,rx}/camera/image_raw` (o `enhanced`) | Sub | `BEST_EFFORT` (depth 5) | Buffer di ~1 s a 5 Hz per consentire l'accoppiamento stereo |
| `detection_node` | `/stereo_down/targets` | Pub | `RELIABLE` (depth 10) | Garantisce il recapito dei target ai nodi di controllo |
| `detection_node` | `/stereo_down/timings` | Pub | `BEST_EFFORT` (depth 10) | Telemetria diagnostica non bloccante |

---

## 6. Comandi di Esecuzione e Test

### Compilazione del Pacchetto

```bash
cd ~/nautilus-vision-pipeline/ros2_ws
colcon build --symlink-install --packages-select nautilus_perception
source install/setup.bash
```

### Avvio Standalone del Nodo di Detection

```bash
# Esecuzione headless (produzione / benchmark)
ros2 launch nautilus_perception detection.launch.py

# Esecuzione con finestra grafica OpenCV di debug (visualizza bounding box e Z)
ros2 launch nautilus_perception detection.launch.py enable_debug:=true

# Esecuzione con modello personalizzato (es. modello subacqueo a 416)
ros2 launch nautilus_perception detection.launch.py \
    model_filename_override:=best_416_fp32_openvino_model \
    imgsz_override:=416
```

### Avvio Integrato tramite `pipeline.launch.py`

Il launch file integrato permette di coordinare in modo condizionale tutti i nodi:

```bash
# Avvio di enhancement + detection sopra l'acquisizione già attiva al boot
ros2 launch nautilus_perception pipeline.launch.py \
    enable_enhancement:=true \
    enable_detection:=true

# Avvio completo da zero (inclusa l'acquisizione stereocamera)
ros2 launch nautilus_perception pipeline.launch.py \
    include_stereo_camera:=true \
    enable_enhancement:=false \
    enable_detection:=true
```

### Ispezione dei Dati Pubblicati

```bash
# Visualizzazione dei target rilevati con coordinate metriche
ros2 topic echo /stereo_down/targets

# Visualizzazione dei tempi di calcolo per stage (pre, inferenza, post, totale)
ros2 topic echo /stereo_down/timings
```
