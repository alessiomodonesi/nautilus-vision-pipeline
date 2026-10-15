# Guida al Lancio Globale della Pipeline Nautilus Vision

Questo documento descrive il funzionamento del sistema di lancio globale della pipeline ROS 2 per il progetto Nautilus, spiegando come configurare l'esecuzione dinamica dei nodi, gestire i parametri e avviare il sistema.

## 1. Architettura del Lancio Globale

Il sistema di lancio è **modulare**: il pacchetto `nautilus_camera` gestisce l'acquisizione, il benchmark e il salvataggio (Fasi 1 e 3), mentre `nautilus_perception` gestisce enhancement e detection (Fasi 2 e 4). Ogni pacchetto ha il proprio launch file e può essere avviato in modo indipendente.

La pipeline completa è composta da quattro blocchi principali:

1. **Acquisizione (`nautilus_camera/stereo_camera.launch.py`):** Sempre attivo. Avvia i due driver `camera_ros` (camera sinistra e destra) a 720p @ 5 FPS tramite il file `config/nautilus_camera.yaml`.
2. **Benchmark (`metrics_node`):** Condizionale. Misura FPS reali, jitter e skew stereo. È un puro osservatore, non pubblica nulla.
3. **Salvataggio (`saving_node`):** Condizionale. Salva i frame stereo su disco locale (JPEG/PNG) con naming incrementale (nessun RTC richiesto). Espone un ROS 2 Service per attivarlo/disattivarlo a runtime.
4. **Enhancement + Detection (`nautilus_perception/pipeline.launch.py`):** Condizionale. Migliora le immagini e calcola la stereovisione.

### Diagramma dei flussi

```text
                   ┌──────────────────────────────────────────────┐
                   │            nautilus_camera                   │
                   │                                              │
    ┌────────┐     │  ┌──────────┐   ┌──────────────┐             │
    │ Cam LX │────▶│  │ camera   │──▶│ metrics_node │ (opzionale) │
    └────────┘     │  │ _ros     │   └──────────────┘             │
    ┌────────┐     │  │ (lx)     │   ┌──────────────┐             │
    │ Cam RX │────▶│  └──────────┘──▶│ saving_node  │ (opzionale) │
    └────────┘     │  ┌──────────┐   └──────────────┘             │
                   │  │ camera   │──▶ ...                         │
                   │  │ _ros(rx) │                                │
                   │  └──────────┘                                │
                   └──────────────┬───────────────────────────────┘
                                  │ /stereo/{lx,rx}/camera/image_raw
                                  ▼
                   ┌──────────────────────────────────────────────┐
                   │          nautilus_perception                 │
                   │  ┌──────────────┐   ┌─────────────────┐      │
                   │  │ enhancement  │──▶│   detection     │      │
                   │  │   _node      │   │     _node       │      │
                   │  └──────────────┘   └─────────────────┘      │
                   │      (opzionale)         (opzionale)         │
                   └──────────────────────────────────────────────┘
```

## 2. Configurazione Globale (`pipeline_config.env`)

Invece di modificare il codice ROS 2 per ogni test, il comportamento della pipeline è governato da un file di ambiente posizionato nella radice del progetto:

**Percorso:** `~/nautilus-vision-pipeline/pipeline_config.env`

```bash
# pipeline_config.env
# Imposta a 'true' o 'false' per configurare l'esecuzione della pipeline
ENABLE_ENHANCEMENT=false
ENABLE_DETECTION=false
ENABLE_SAVING=true
```

| Variabile             | Default | Descrizione                                                       |
|-----------------------|---------|-------------------------------------------------------------------|
| `ENABLE_ENHANCEMENT`  | `false` | Avvia il nodo di enhancement (nautilus_perception)                |
| `ENABLE_DETECTION`    | `false` | Avvia il nodo di detection (nautilus_perception)                  |
| `ENABLE_SAVING`       | `true`  | Avvia il nodo di salvataggio (nautilus_camera)                    |

Lo script `deploy/start_pipeline.sh` legge questo file e passa dinamicamente i valori al launch file. All'avvio automatico del Raspberry Pi (trigger del reed sensor) viene lanciata **solo la parte di acquisizione + salvataggio**, come richiesto dal capo progetto.

### Routing automatico dei topic

Nel launch file `nautilus_perception/pipeline.launch.py` il tipo di input per la detection viene valutato automaticamente:

* Se `ENABLE_ENHANCEMENT=true`, la detection riceverà l'argomento `input_type_override='enhanced'` e si collegherà ai topic `/stereo/{lx,rx}/image_enhanced`.
* Se `ENABLE_ENHANCEMENT=false`, riceverà `input_type_override='raw'` e si collegherà a `/stereo/{lx,rx}/camera/image_raw`.

Questo previene deadlock in cui il nodo di detection attenderebbe topic inesistenti.

## 3. Configurazione del Pacchetto `nautilus_camera`

Tutti i parametri di acquisizione, benchmark e salvataggio vivono in un unico file YAML:

**Percorso:** `ros2_ws/src/nautilus_camera/config/nautilus_camera.yaml`

```yaml
# Parametri hardware per camera_ros - camera sinistra (lx)
/stereo/lx/camera:
  ros__parameters:
    camera: 0
    width: 1280
    height: 720
    FrameDurationLimits: [200000, 200000]   # 200000 µs = 200 ms => 5 FPS
# Parametri hardware per camera_ros - camera destra (rx)
/stereo/rx/camera:
  ros__parameters:
    camera: 1
    width: 1280
    height: 720
    FrameDurationLimits: [200000, 200000]
# Parametri del nodo di benchmark
/**/metrics_node:
  ros__parameters:
    left_topic:  '/stereo/lx/camera/image_raw'
    right_topic: '/stereo/rx/camera/image_raw'
    sync_slop_sec: 0.05
    window_size: 30
    log_interval_sec: 1.0
    display: false
# Parametri del nodo di salvataggio
/**/saving_node:
  ros__parameters:
    enable_saving: true
    left_topic:  '/stereo/lx/camera/image_raw'
    right_topic: '/stereo/rx/camera/image_raw'
    save_directory: '/home/nautilus/nautilus_data'
    save_left: true
    save_right: true
    image_format: 'jpg'
    jpeg_quality: 95
    filename_prefix: 'nautilus'
    queue_size: 10
    flush_every_n: 1
    max_files_per_session: 0
    sync_slop_sec: 0.05
```

### Note importanti sui parametri*

* **`FrameDurationLimits`**: valori in microsecondi; `[200000, 200000]` forza 5 FPS stabili. Non modificare senza aggiornare i benchmark attesi.
* **`sync_slop_sec`**: tolleranza di disallineamento temporale (in secondi) tra i frame sinistro e destro nel `message_filters.ApproximateTimeSynchronizer`. Con skew misurato ~1.5 ms, 50 ms è ideale a 5 FPS (il periodo tra frame è 200 ms: uno slop $\le 50\text{ ms}$ impedisce di accoppiare frame di epoche diverse).
* **`flush_every_n`**: forza il commit su disco (`os.sync()`) ogni N coppie stereo salvate. Cruciale sul veicolo per prevenire corruzioni di filesystem della MicroSD a seguito dello spegnimento brusco con reed switch magnetico.
* **`save_directory`**: deve essere una directory scrivibile dall'utente `nautilus`. Ad ogni avvio il nodo crea una sottocartella `YYYYmmdd-HHMMSS_session/` (con suffisso progressivo `_1`, `_2` in caso di orologio di sistema non sincronizzato) per evitare qualsiasi sovrascrittura accidentale.
* **`image_format`**: `'jpg'` o `'png'`. Il formato JPEG occupa molto meno spazio, ma introduce artefatti di compressione; per uso scientifico dei biologi potrebbe servire PNG.
* **`max_files_per_session`**: `0` significa nessun limite. Utile per test a tempo determinato.
* **`display`** (metrics_node): apre una finestra OpenCV; richiede sessione grafica attiva. Disattivato per default perché introduce overhead e falsa i benchmark.

## 4. Parametri del Nodo di Detection (`nautilus_perception/config/detection_params.yaml`)

I parametri specifici dell'algoritmo di visione risiedono in questo file separato:

```yaml
detection_node:
  ros__parameters:
    model_filename: 'yolov8n.pt' # o 'yolov8n_openvino_model'
    conf_threshold: 0.4
    input_type: 'raw'            # fallback (sovrascritto dinamicamente)
    enable_debug: False
    half_res: True               # False obbligatorio per OpenVINO
    num_threads: 2               # Core logici dedicati all'inferenza CPU/OpenVINO
    sync_slop_sec: 0.05          # Tolleranza sincronizzazione stereo (50 ms)
```

### Note importanti sui parametri**

* **`num_threads`**: è cruciale per i benchmark termici e prestazionali sul Raspberry Pi 5. Il nodo legge questo parametro e imposta le variabili di sistema `OMP_NUM_THREADS` e `MKL_NUM_THREADS` *prima* di caricare il modello, garantendo che le risorse CPU non vengano saturate in modo incontrollato.
* **`sync_slop_sec`**: allineato a 50 ms per evitare che in caso di frame drop su un canale vengano associati fotogrammi a intervalli temporali diversi ($t$ con $t+200\text{ ms}$), falsando disparità e stima di profondità.

## 5. Come Compilare e Avviare

Ogni volta che modifichi i file Python o i `.launch.py`, devi ricompilare il workspace:

```bash
cd ~/nautilus-vision-pipeline/ros2_ws
colcon build --symlink-install
source install/setup.bash
```

*(Nota: `--symlink-install` permette di modificare file Python non compilati e launch file senza rifare la build; è comunque buona pratica ricompilare dopo modifiche strutturali).*

### Avvio manuale del solo blocco acquisizione + salvataggio

```bash
cd ~/nautilus-vision-pipeline
./deploy/start_pipeline.sh
```

### Avvio manuale con controllo granulare

```bash
# solo acquisizione (benchmark pulito, zero I/O)
ros2 launch nautilus_camera stereo_camera.launch.py \
    enable_saving:=false enable_metrics:=true
# acquisizione + salvataggio (produzione)
ros2 launch nautilus_camera stereo_camera.launch.py \
    enable_saving:=true enable_metrics:=false
# pipeline completa (con enhancement + detection)
ros2 launch nautilus_perception pipeline.launch.py \
    enable_enhancement:=true \
    enable_detection:=true \
    enable_saving:=true \
    enable_metrics:=true
```

### Attivare/disattivare il salvataggio a runtime

Il nodo `saving_node` espone un ROS 2 Service per controllare il salvataggio senza spegnere il nodo:

```bash
# ferma il salvataggio (continua l'acquisizione e le metriche)
ros2 service call /saving_node/set_saving std_srvs/srv/SetBool "{data: false}"
# riprendi il salvataggio
ros2 service call /saving_node/set_saving std_srvs/srv/SetBool "{data: true}"
```

Utile durante i test per alternare rapidamente modalità "benchmark" e "produzione" senza restart.

## 6. Avvio tramite Servizio Systemd

Il Raspberry Pi è configurato per lanciare la pipeline in automatico all'avvio (trigger: reed sensor + magnetismo → alimentazione → boot). Il servizio systemd si chiama `nautilus-vision.service`.

### Installazione (una tantum)

```bash
# copia lo unit file
sudo cp ~/nautilus-vision-pipeline/deploy/nautilus-vision.service \
        /etc/systemd/system/
# copia lo script di avvio
sudo cp ~/nautilus-vision-pipeline/deploy/start_pipeline.sh \
        /usr/local/bin/
sudo chmod +x /usr/local/bin/start_pipeline.sh
# ricarica e abilita
sudo systemctl daemon-reload
sudo systemctl enable nautilus-vision.service
```

### Comandi utili

```bash
# applica subito le modifiche al .env senza riavviare la scheda
sudo systemctl restart nautilus-vision.service
# ferma la pipeline
sudo systemctl stop nautilus-vision.service
# stato del servizio
sudo systemctl status nautilus-vision.service
# log in tempo reale (FPS, metriche, errori)
journalctl -u nautilus-vision.service -f
```

## 7. Esempi di Configurazione per i Test (Fase 6 e 7)

1. **Test: Solo Acquisizione (Baseline hardware)**
   * Nel `.env`: `ENABLE_ENHANCEMENT=false`, `ENABLE_DETECTION=false`, `ENABLE_SAVING=false`
   * Avvio: `ros2 launch nautilus_camera stereo_camera.launch.py enable_metrics:=true enable_saving:=false`

2. **Test: Acquisizione + Detection (Nessun pre-processing)**
   * Nel `.env`: `ENABLE_ENHANCEMENT=false`, `ENABLE_DETECTION=true`, `ENABLE_SAVING=false`
   * Nel `.yaml` di detection: imposta `num_threads` desiderato.

3. **Test: Full Pipeline con salvataggio**
   * Nel `.env`: `ENABLE_ENHANCEMENT=true`, `ENABLE_DETECTION=true`, `ENABLE_SAVING=true`

4. **Test: Stress test termico (1 h a box chiusa)**
   * Avvia con `enable_metrics:=true` per loggare FPS, jitter e skew ogni secondo.
   * Logga in parallelo temperatura e throttling: `vcgencmd measure_temp` e `vcgencmd get_throttled`.

5. **Test: Benchmark Fase 6 (9 run A/B/C)**
   * Usa `benchmarks/CONFIGS.md` come riferimento
   * `enable_debug:=false` sempre

## 8. Dove trovare i dati salvati

Di default i frame vengono salvati in:

```text
/home/nautilus/nautilus_data/<YYYYmmdd-HHMMSS_session>/
├── nautilus_lx_00000001.jpg
├── nautilus_rx_00000001.jpg
├── nautilus_lx_00000002.jpg
├── nautilus_rx_00000002.jpg
└── ...
```

Il contatore è monotonicamente crescente e viene azzerato ad ogni avvio di sessione. Poiché il Raspberry Pi non ha RTC, **non fidarti dell'orario del filesystem**: usa il contatore per ordinare i frame, e l'ID sessione solo per raggrupparli. Inoltre, se l'orario di sistema coincide tra reboot successivi, `saving_node` rileva la collisione e crea automaticamente una sottocartella con suffisso incrementale (es. `YYYYmmdd-HHMMSS_session_1`), proteggendo i dati precedenti dalla sovrascrittura.

Per contare i file salvati:

```bash
find /home/nautilus/nautilus_data -name "*.jpg" | wc -l
```

## 9. Troubleshooting

| Sintomo | Causa probabile | Soluzione |
| --- | --- | --- |
| `camera_ros` non trova la camera | device ID errato nel YAML | verifica con `rpicam-hello --list-cameras` |
| Skew > 50 ms persistente | i due sensori sono sincronizzati male | controlla cavi CSI, riduci risoluzione |
| Warning `camera_info` mancante | calibrazione non presente | non blocca l'acquisizione, ignora per ora |
| `saving_node` non scrive nulla | `save_directory` non scrivibile | `mkdir -p /home/nautilus/nautilus_data && chmod 755` |
| File JPEG con colori invertiti (rosso/blu) | conversione spazio colore non conforme | `saving_node` converte forzatamente in `bgr8` prima di `cv2.imwrite` |
| File parzialmente scritti o corrotti al distacco del magnete | cache I/O non svuotata prima del cut off | imposta `flush_every_n: 1` nel YAML per forzare `os.sync()` su MicroSD |
| Servizio systemd non parte | path in `ExecStart` sbagliato | controlla `journalctl -u nautilus-vision -f` |
| `ros2 launch` trova `pipeline.launch.py` ma non `stereo_camera.launch.py` | workspace non ricompilato | `colcon build --symlink-install && source install/setup.bash` |
