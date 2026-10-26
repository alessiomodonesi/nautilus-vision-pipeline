# Guida al Lancio Globale della Pipeline Nautilus Vision

Questo documento descrive il funzionamento del sistema di avvio e gestione della pipeline ROS 2 per il progetto Nautilus, spiegando come configurare l'esecuzione dei nodi, gestire i parametri e monitorare il sistema in produzione e in fase di test.

---

## 1. Architettura di Lancio della Pipeline

Il sistema è progettato in modo **modulare** e disaccoppiato:

- **`nautilus_camera`**: gestisce l'acquisizione hardware con i due sensori IMX708 via `camera_ros` e la telemetria di base con `metrics_node`.
- **`nautilus_perception`**: gestisce l'enhancement visivo (`enhancement_node`) e l'object detection 3D (`detection_node`).
- **`nautilus-bag.service`**: registra i flussi compressi in formato MCAP per la persistenza su disco, senza appesantire la CPU durante la navigazione.

### Flusso di Dati

```text
               ┌──────────────────────────────────────────────────┐
               │                nautilus_camera                   │
               │                                                  │
┌────────┐     │  ┌──────────┐                                    │
│ Cam LX │────▶│  │ camera   │───────────────────────────────────▶│ /stereo/lx/camera/image_raw
└────────┘     │  │ _ros(lx) │                                    │
┌────────┐     │  └──────────┘                                    │
│ Cam RX │────▶│  ┌──────────┐                                    │
└────────┘     │  │ camera   │───────────────────────────────────▶│ /stereo/rx/camera/image_raw
               │  │ _ros(rx) │                                    │
               │  └──────────┘                                    │
               └──────────────┬───────────────────────────────────┘
                              │
                              ▼ /stereo/{lx,rx}/camera/image_raw
               ┌──────────────────────────────────────────────────┐
               │               nautilus_perception                │
               │  ┌──────────────────┐    ┌────────────────────┐  │
               │  │ enhancement_node │───▶│   detection_node   │  │
               │  │ (CLAHE+Sharp)    │    │ (YOLOv8 + Stereo)  │  │
               │  └──────────────────┘    └────────────────────┘  │
               │       (opzionale)              (opzionale)       │
               │       input: raw               input: enhanced   │
               └────────────────────────────────────────┬─────────┘
                                                        │
                                                        ▼ /stereo_down/targets
                                               (3D Targets X, Y, Z)
```

### Regola Operativa di Bordo

All'accensione del Raspberry Pi 5 (trigger da interruttore magnetico a reed):

1. **Partono automaticamente solo le telecamere**: `nautilus-vision.service` avvia `stereo_camera.launch.py`.
2. **Lock fotometrico a runtime**: `lock-cameras.service` riapplica l'esposizione fissa (`ExposureTime: 20000`, `ColourGains: [1.5, 1.5]`) e le posizioni di fuoco (`LensPosition: 2.6 / 1.5`).
3. **Registrazione dati opzionale**: se `ENABLE_BAG=true` in `pipeline_config.env`, `nautilus-bag.service` registra i flussi video.
4. **I nodi pesanti di calcolo non partono da soli**: enhancement, detection e benchmark telemetrici consumano CPU e budget termico e vanno attivati su richiesta tramite i launch dedicati o da parte del mission manager.

---

## 2. Configurazione d'Ambiente (`pipeline_config.env`)

Il comportamento dell'intero sistema è controllato dal file d'ambiente situato nella root del progetto:

**Percorso:** `~/nautilus-vision-pipeline/pipeline_config.env`

```bash
# pipeline_config.env
export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export NAUTILUS_ROOT=/home/nautilus/nautilus-vision-pipeline
export CYCLONEDDS_URI="file://${NAUTILUS_ROOT}/deploy/cyclonedds.xml"

# Le telecamere partono SEMPRE al boot via nautilus-vision.service.
# La registrazione rosbag MCAP dei flussi è OPZIONALE (default spenta per i benchmark):
export ENABLE_BAG=false
export NAUTILUS_BAG_DIR=/home/nautilus/nautilus_bags
```

| Variabile | Default | Descrizione |
| :--- | :---: | :--- |
| `ROS_DOMAIN_ID` | `42` | ID del dominio CycloneDDS (deve coincidere su Pi e Jetson) |
| `RMW_IMPLEMENTATION` | `rmw_cyclonedds_cpp` | Middleware di comunicazione ROS 2 standard |
| `CYCLONEDDS_URI` | `.../deploy/cyclonedds.xml` | Configurazione di rete (interfacce, MTU, frammentazione) |
| `ENABLE_BAG` | `false` | Se `true`, attiva la registrazione automatica MCAP via systemd |
| `NAUTILUS_BAG_DIR` | `/home/nautilus/nautilus_bags` | Cartella di salvataggio delle registrazioni bag |

---

## 3. Parametri di Acquisizione Telecamere (`camera_params.yaml`)

Configura i due driver `camera_ros` e il nodo di telemetria.

**Percorso:** `ros2_ws/src/nautilus_camera/config/camera_params.yaml`

```yaml
# Camera sinistra (lx)
/stereo/lx/camera:
  ros__parameters:
    camera: 0
    width: 1280
    height: 720
    FrameDurationLimits: [200000, 200000]   # 200 ms => 5.0 FPS nominali
    AeEnable: false                         # No auto-exposure
    AwbEnable: false                        # No auto-white-balance
    ExposureTime: 20000                     # 20 ms
    ColourGains: [1.5, 1.5]
    AfMode: 0                               # Messa a fuoco manuale
    LensPosition: 2.6                       # Fuoco a ~0.65 m (offset +1.05 diottrie)

# Camera destra (rx)
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
    LensPosition: 1.5                       # Fuoco a ~0.65 m

# Nodo diagnostico
/**/metrics_node:
  ros__parameters:
    left_topic: '/stereo/lx/camera/image_raw'
    right_topic: '/stereo/rx/camera/image_raw'
    sync_slop_sec: 0.05                     # 50 ms tolleranza sincronizzazione
    window_size: 30
    log_interval_sec: 1.0
    display: false
```

> [!NOTE]
> I parametri Quality of Service (QoS) non risiedono in questo file: sono centralizzati in [`ros2_ws/src/nautilus_common/config/qos_overrides.yaml`](../ros2_ws/src/nautilus_common/config/qos_overrides.yaml) come Single Source of Truth (SSOT).

---

## 4. Parametri di Detection (`detection_params.yaml`)

Configura il modello neurale YOLOv8, le soglie e i parametri di calcolo della distanza 3D.

**Percorso:** `ros2_ws/src/nautilus_perception/config/detection_params.yaml`

```yaml
detection_node:
  ros__parameters:
    # Modello di inferenza (cartella OpenVINO in data/weights/)
    model_filename: 'yolov8n_640_fp32_openvino_model'
    half_res: false             # False per modelli OpenVINO a 640px
    imgsz: 640                  # Dimensione tensore input
    conf_threshold: 0.4         # Soglia di confidenza rilevamento
    input_type: 'raw'           # 'raw' oppure 'enhanced'
    enable_debug: false         # True apre la finestra OpenCV
    num_threads: 2              # Thread CPU dedicati a OpenVINO
    sync_slop_sec: 0.05         # Tolleranza stereo sincronizzazione (secondi)
```

### Routing Automatico dei Topic

All'interno di `nautilus_perception/launch/pipeline.launch.py`:

- Se `enable_enhancement:=true`, il parametro `input_type` per la detection diventa automaticamente `'enhanced'` e sottoscrive `/stereo/{lx,rx}/image_enhanced`.
- Se `enable_enhancement:=false`, diventa `'raw'` e sottoscrive direttamente `/stereo/{lx,rx}/camera/image_raw`.
- È possibile forzare manualmente il tipo tramite `input_type_override:=raw` o `input_type_override:=enhanced`.

---

## 5. Modalità di Avvio della Pipeline

### 5.1 Avvio Automatico tramite Systemd (Produzione al Boot)

Sul Raspberry Pi, i servizi systemd gestiscono l'avvio della pipeline:

```bash
# Stato dei servizi
sudo systemctl status nautilus-vision.service
sudo systemctl status lock-cameras.service
sudo systemctl status nautilus-bag.service

# Visualizzazione log in tempo reale
journalctl -u nautilus-vision.service -f
journalctl -u lock-cameras.service -f
```

### 5.2 Avvio Manuale del Solo Blocco Telecamere

```bash
# Avvio standard solo telecamere (5 FPS)
ros2 launch nautilus_camera stereo_camera.launch.py

# Con diagnostica FPS / Jitter / Skew attiva a log
ros2 launch nautilus_camera stereo_camera.launch.py enable_metrics:=true
```

### 5.3 Aggiungere Detection ed Enhancement sopra le Camere Attive

Quando le telecamere sono già in esecuzione al boot, `pipeline.launch.py` aggiunge l'elaborazione senza interferire con i nodi camera esistenti (`include_stereo_camera:=false` di default):

```bash
# Aggiungi solo la detection (input raw)
ros2 launch nautilus_perception pipeline.launch.py \
    enable_detection:=true \
    enable_enhancement:=false

# Aggiungi enhancement + detection (input enhanced)
ros2 launch nautilus_perception pipeline.launch.py \
    enable_detection:=true \
    enable_enhancement:=true

# Avvio con finestra grafica OpenCV di debug (richiede display X11)
ros2 launch nautilus_perception detection.launch.py enable_debug:=true
```

### 5.4 Avvio Standalone Completo da Zero

Se i servizi systemd sono stati fermati (ad esempio su banco di laboratorio o workstation):

```bash
ros2 launch nautilus_perception pipeline.launch.py \
    include_stereo_camera:=true \
    enable_detection:=true \
    enable_enhancement:=false
```

---

## 6. Registrazione Dati ed Estrazione Frame

La memorizzazione delle immagini a bordo non grava sulla CPU grazie all'impiego del formato standard **MCAP**:

### Registrazione Automatica via Systemd

Configurare in `pipeline_config.env`:

```bash
export ENABLE_BAG=true
```

Riavviare il servizio:

```bash
sudo systemctl restart nautilus-bag.service
```

### Registrazione Manuale Rapida

```bash
ros2 bag record -s mcap \
    -o /home/nautilus/nautilus_bags/sessione_test \
    /stereo/lx/camera/image_raw/compressed \
    /stereo/rx/camera/image_raw/compressed \
    /stereo_down/targets
```

### Estrazione Frame JPEG per i Biologi (`tools/extract_bag_frames.py`)

Al termine della missione, lo script dedicato estrae i frame JPEG numerati direttamente dal file MCAP senza ricompressione:

```bash
python3 tools/extract_bag_frames.py \
    --bag /home/nautilus/nautilus_bags/sessione_test \
    --out-dir /home/nautilus/immagini_missione \
    --copy-calibration
```

Lo script genera le cartelle `left/` e `right/` con numerazione sequenziale e il file `metadata.csv` di corrispondenza temporale.

---

## 7. Protocolli di Test e Benchmark (Fasi 6 e 7)

Per l'esecuzione dei benchmark prestazionali e termici, utilizzare i wrapper dedicati descritti nelle rispettive cartelle:

- **Fase 6 — Benchmark Prestazionali**:
  - Script di automazione: [`benchmarks/run_benchmark.sh`](../benchmarks/run_benchmark.sh)
  - Documentazione: [`benchmarks/benchmark_results/CONFIGS.md`](../benchmarks/benchmark_results/CONFIGS.md)
  - Report dei risultati: [`benchmarks/benchmark_results/RESULTS.md`](../benchmarks/benchmark_results/RESULTS.md)
- **Fase 7 — Stress Test Termico (1h a box chiusa)**:
  - Script di automazione: [`benchmarks/run_thermal_test.sh`](../benchmarks/run_thermal_test.sh)
  - Documentazione: [`benchmarks/thermal_results/CONFIGS.md`](../benchmarks/thermal_results/CONFIGS.md)
  - Report dei risultati: [`benchmarks/thermal_results/RESULTS.md`](../benchmarks/thermal_results/RESULTS.md)

---

## 8. Guida al Troubleshooting

| Sintomo | Causa Probabile | Azione Correttiva |
| :--- | :--- | :--- |
| `camera_ros` non trova i device `/dev/video*` | Device occupati o cavo CSI non inserito correttamente | Esegui `sudo fuser -k -9 /dev/video*`; controlla con `rpicam-hello --list-cameras`. |
| Errore "node already exists" su `camera_node` | Telecamere già avviate da `nautilus-vision.service` | Non passare `include_stereo_camera:=true` in `pipeline.launch.py`. |
| Distanza Z instabile o nulla (`0.00 m`) | Parametri AE/AWB non bloccati sulle telecamere | Verifica l'esecuzione di `lock_cameras.py` con `systemctl status lock-cameras.service`. |
| Skew temporale elevato (> 10 ms) | Desincronizzazione dei sensori o clock non stazionario | Verifica i cavi CSI; controlla che `camera_params.yaml` usi `FrameDurationLimits: [200000, 200000]`. |
| Detection lenta (< 0.5 FPS) | Utilizzo di modello INT8 su CPU ARM o WaterNet attivo | Usa il modello raccomandato `yolov8n_640_fp32_openvino_model` e `waternet_mode:=force_off`. |
| I nodi ROS 2 su Pi e Jetson non comunicano | Mismatch di configurazione DDS o `ROS_DOMAIN_ID` | Assicurati che entrambe le macchine abbiano `ROS_DOMAIN_ID=42` ed esportino lo stesso file `cyclonedds.xml`. |
