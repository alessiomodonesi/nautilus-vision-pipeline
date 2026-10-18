# Guida al Lancio Globale della Pipeline Nautilus Vision

Questo documento descrive il funzionamento del sistema di lancio della pipeline ROS 2 per il progetto Nautilus, spiegando come configurare l'esecuzione dei nodi, gestire i parametri e avviare il sistema.

## 1. Architettura del Lancio Globale

Il sistema di lancio è **modulare**: il pacchetto `nautilus_camera` gestisce l'acquisizione, il benchmark e il salvataggio (Fasi 1 e 3), mentre `nautilus_perception` gestisce enhancement e detection (Fasi 2 e 4). Ogni pacchetto ha il proprio launch file e può essere avviato in modo indipendente.

La pipeline completa è composta da quattro blocchi principali:

1. **Acquisizione (`nautilus_camera/stereo_camera.launch.py`):** sempre attiva. Avvia i due driver `camera_ros` (camera sinistra e destra) a 720p @ 5 FPS tramite `config/nautilus_camera.yaml`. È l'unico blocco che parte in automatico al boot del Raspberry Pi.
2. **Salvataggio (`saving_node`):** opzionale. Salva i frame stereo su disco locale (JPEG/PNG) con naming incrementale (nessun RTC richiesto). Si attiva al boot solo se `ENABLE_SAVING=true` in `pipeline_config.env`. Espone anche un ROS 2 Service per attivarlo/disattivarlo a runtime.
3. **Benchmark (`metrics_node`):** mai automatico. Misura FPS reali, jitter e skew stereo. Si lancia a mano durante i test.
4. **Enhancement + Detection (`nautilus_perception/pipeline.launch.py`):** mai automatici. Migliorano le immagini e calcolano la stereovisione. Si lanciano a mano quando servono.

### Regola di fondo

All'avvio del Raspberry Pi partono **solo** acquisizione e (opzionalmente) salvataggio. Enhancement, detection e metriche non devono mai partire in automatico: consumano CPU/batteria e servono solo durante test o sessioni dedicate. Questo vincolo è implementato in `start_pipeline.sh`.

### Diagramma dei flussi

```text
                   ┌──────────────────────────────────────────────┐
                   │            nautilus_camera                   │
                   │                                              │
    ┌────────┐     │  ┌──────────┐                                │
    │ Cam LX │────▶│  │ camera   │────┬──────────────────────────▶│ /stereo/lx/camera/image_raw
    └────────┘     │  │ _ros     │    │                           │
    ┌────────┐     │  │ (lx)     │    └──▶ ┌──────────────┐       │
    │ Cam RX │────▶│  └──────────┘         │ saving_node  │(opt.) │
    └────────┘     │  ┌──────────┐         └──────────────┘       │
                   │  │ camera   │────┬──────────────────────────▶│ /stereo/rx/camera/image_raw
                   │  │ _ros(rx) │    └──▶ (saving_node, same)    │
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
                   │      solo a mano         solo a mano         │
                   └──────────────────────────────────────────────┘
```

## 2. Configurazione Globale (`pipeline_config.env`)

Il comportamento della pipeline all'avvio è governato da un file di ambiente posizionato nella radice del progetto:

**Percorso:** `~/nautilus-vision-pipeline/pipeline_config.env`

```bash
# pipeline_config.env
# file di configurazione letto da start_pipeline.sh all'avvio del raspberry

export NAUTILUS_ROOT=/home/nautilus/nautilus-vision-pipeline

# salvataggio su disco: true = parte anche saving_node insieme all'acquisizione
# false = solo acquisizione (nessun I/O su microSD)
ENABLE_SAVING=false
```

| Variabile         | Default | Descrizione                                                       |
|-------------------|---------|-------------------------------------------------------------------|
| `ENABLE_SAVING`   | `false` | Avvia il nodo di salvataggio insieme all'acquisizione             |

**Unica variabile gestita da `start_pipeline.sh`.** Enhancement, detection e metrics non hanno un flag nel `.env` perché non partono mai automaticamente: si lanciano a mano con `ros2 launch` quando servono.

### Cosa fa `start_pipeline.sh`

```bash
ros2 launch nautilus_camera stereo_camera.launch.py \
    enable_saving:=${ENABLE_SAVING} \
    enable_metrics:=false
```

- `enable_metrics:=false` è forzato: le metriche si lanciano solo a mano durante i benchmark.
- `camera_ros` legge i parametri fotometrici (lens position, autofocus, exposure, colour gains) dal YAML e li applica al boot.
- Subito dopo, `lock-cameras.service` lancia `lock_cameras.py` che riapplica gli stessi parametri via `set_parameters` per sicurezza (vedi sezione 6).

### Routing automatico dei topic

Nel launch file `nautilus_perception/pipeline.launch.py` il tipo di input per la detection viene valutato automaticamente:

- se `enable_enhancement:=true`, la detection riceve `input_type_override='enhanced'` e si collega a `/stereo/{lx,rx}/image_enhanced`

- se `enable_enhancement:=false`, riceve `input_type_override='raw'` e si collega a `/stereo/{lx,rx}/camera/image_raw`

Questo previene deadlock in cui il nodo di detection attenderebbe topic inesistenti.

## 3. Configurazione del Pacchetto `nautilus_camera`

Tutti i parametri di acquisizione, benchmark e salvataggio vivono in un unico file YAML. Lo stesso file è letto anche da `lock_cameras.py` (sezione 6) per riapplicare i parametri fotometrici a runtime.

**Percorso:** `ros2_ws/src/nautilus_camera/config/nautilus_camera.yaml`

```yaml
# parametri hardware per camera_ros - camera sinistra (lx)
/stereo/lx/camera:
  ros__parameters:
    camera: 0
    width: 1280
    height: 720
    FrameDurationLimits: [200000, 200000]   # 200 ms => 5 FPS
    AeEnable: false
    AwbEnable: false
    ExposureTime: 20000
    ColourGains: [1.5, 1.5]
    AfMode: 0
    LensPosition: 2.6                       # offset meccanico +1.05 vs rx

# parametri hardware per camera_ros - camera destra (rx)
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
    LensPosition: 1.5

# parametri del nodo di benchmark
/**/metrics_node:
  ros__parameters:
    left_topic:  '/stereo/lx/camera/image_raw'
    right_topic: '/stereo/rx/camera/image_raw'
    sync_slop_sec: 0.05
    window_size: 30
    log_interval_sec: 1.0
    display: false

# parametri del nodo di salvataggio
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

> **Nota QoS**: le entry `qos_overrides` **non** sono più in questo file.
> Sono centralizzate in `nautilus_common/config/qos_overrides.yaml` (SSOT)
> e passate a `camera_ros` dal launch `stereo_camera.launch.py` come
> `--params-file` aggiuntivo. Vedi `nautilus_common/README.md` per
> l'architettura completa.

### Note importanti sui parametri

- **`FrameDurationLimits`**: valori in microsecondi; `[200000, 200000]` forza 5 FPS stabili. Non modificare senza aggiornare i benchmark attesi.
- **`AeEnable`, `AwbEnable`, `ExposureTime`, `ColourGains`**: lock fotometrico. Servono per garantire coerenza radiometrica tra i due sensori: la stereo correlation (NCC, SGBM) fallisce se left e right hanno esposizione o white balance diversi.
- **`AfMode`, `LensPosition`**: messa a fuoco manuale. L'offset meccanico tra i due obiettivi è di +1.05 diottrie sulla sinistra (documentato in `DEBUG.md` §3.2). `camera_ros` può rifiutare questi parametri al boot su IMX708: `lock_cameras.py` li riapplica subito dopo.
- **`sync_slop_sec`**: tolleranza di disallineamento temporale (in secondi) tra i frame sinistro e destro nel `message_filters.ApproximateTimeSynchronizer`. Con skew misurato ~1.5 ms, 50 ms è ideale a 5 FPS (il periodo tra frame è 200 ms: uno slop ≤ 50 ms impedisce di accoppiare frame di epoche diverse).
- **`flush_every_n`**: forza il commit su disco (`os.sync()`) ogni N coppie stereo salvate. Cruciale sul veicolo per prevenire corruzioni di filesystem della MicroSD a seguito dello spegnimento brusco con reed switch magnetico.
- **`save_directory`**: deve essere una directory scrivibile dall'utente `nautilus`. Ad ogni avvio il nodo crea una sottocartella `YYYYmmdd-HHMMSS_session/` (con suffisso progressivo `_1`, `_2` in caso di orologio di sistema non sincronizzato) per evitare qualsiasi sovrascrittura accidentale.
- **`image_format`**: `'jpg'` o `'png'`. Il formato JPEG occupa molto meno spazio, ma introduce artefatti di compressione; per uso scientifico dei biologi potrebbe servire PNG.
- **`max_files_per_session`**: `0` significa nessun limite. Utile per test a tempo determinato.
- **`display`** (metrics_node): apre una finestra OpenCV; richiede sessione grafica attiva. Disattivato per default perché introduce overhead e falsa i benchmark.

## 4. Parametri del Nodo di Detection (`nautilus_perception/config/detection_params.yaml`)

I parametri specifici dell'algoritmo di visione risiedono in questo file separato:

```yaml
detection_node:
  ros__parameters:
    model_filename: 'yolov8n.pt' # o directory 'yolov8n_openvino_640_fp32'
    conf_threshold: 0.4
    input_type: 'raw'            # fallback (sovrascritto dinamicamente dal launch)
    enable_debug: False
    half_res: True               # False obbligatorio per OpenVINO
    imgsz: 640
    num_threads: 2               # Core logici dedicati all'inferenza CPU/OpenVINO
    sync_slop_sec: 0.05          # Tolleranza sincronizzazione stereo (50 ms)
```

### Come vengono risolti i parametri

Il nodo di detection ha **due livelli di override**:

1. il file YAML fornisce i valori di default
2. il launch file `detection.launch.py` sovrascrive **sempre** `input_type`, `enable_debug`, `model_filename`, `half_res`, `imgsz` con i propri default di `DeclareLaunchArgument`, anche quando l'utente non passa nulla a riga di comando

Quindi, per modificare uno di questi cinque valori, o si aggiornano i default in `detection.launch.py`, oppure si passano esplicitamente come argomenti di lancio. Gli altri parametri (`conf_threshold`, `num_threads`, `sync_slop_sec`) non hanno override di lancio e restano quelli del YAML.

### Note importanti sui parametri

- **`num_threads`**: è cruciale per i benchmark termici e prestazionali sul Raspberry Pi 5. Il nodo legge questo parametro e imposta le variabili di sistema `OMP_NUM_THREADS` e `MKL_NUM_THREADS` *prima* di caricare il modello, garantendo che le risorse CPU non vengano saturate in modo incontrollato.
- **`sync_slop_sec`**: allineato a 50 ms per evitare che in caso di frame drop su un canale vengano associati fotogrammi a intervalli temporali diversi (t con t+200 ms), falsando disparità e stima di profondità.

#### Override manuale dell'input

`pipeline.launch.py` espone anche `input_type_override` (default vuoto).
Se passato, forza `input_type` e vince sulla logica automatica
`enable_enhancement → enhanced/raw`. Utile quando si vuole lanciare
l'enhancement esternamente e fare detection su enhanced **senza**
duplicare l'enhancement:

```bash
# terminale 1: enhancement esterno
ros2 launch nautilus_perception enhancement.launch.py

# terminale 2: solo detection, ma su enhanced
ros2 launch nautilus_perception pipeline.launch.py \
    enable_enhancement:=false \
    enable_detection:=true \
    input_type_override:=enhanced
```

Senza `input_type_override`, l'unico modo per avere detection su
`image_enhanced` è `enable_enhancement:=true`, che però rilancerebbe
una seconda coppia di `enhancement_node` → nodo duplicato sul topic.

## 5. Come Compilare e Avviare

Ogni volta che modifichi i file Python o i `.launch.py`, devi ricompilare il workspace:

```bash
cd ~/nautilus-vision-pipeline/ros2_ws
colcon build --symlink-install
source install/setup.bash
```

*(Nota: `--symlink-install` permette di modificare file Python non compilati e launch file senza rifare la build; è comunque buona pratica ricompilare dopo modifiche strutturali).*

### Avvio automatico al boot (già configurato)

`nautilus-vision.service` lancia `start_pipeline.sh`, che avvia acquisizione + salvataggio opzionale. Non serve fare nulla a mano.

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
```

### Aggiungere enhancement e/o detection sopra l'acquisizione già attiva

Quando le camere sono già in esecuzione (dal boot o da un `stereo_camera.launch.py` lanciato a mano), per aggiungere detection/enhancement si usa `pipeline.launch.py` senza toccare le camere:

```bash
# aggiungi solo la detection (input raw)
ros2 launch nautilus_perception pipeline.launch.py \
    enable_detection:=true \
    enable_enhancement:=false

# aggiungi enhancement + detection (input enhanced)
ros2 launch nautilus_perception pipeline.launch.py \
    enable_detection:=true \
    enable_enhancement:=true
```

`pipeline.launch.py` di default **non** riavvia `camera_ros` (`include_stereo_camera:=false`): assume che le camere siano già attive. Se invece vuoi lanciare tutto da zero (es. su workstation con i service systemd fermi), passa `include_stereo_camera:=true`.

### Attivare/disattivare il salvataggio a runtime

Il nodo `saving_node` espone un ROS 2 Service per controllare il salvataggio senza spegnere il nodo:

```bash
# ferma il salvataggio (continua l'acquisizione)
ros2 service call /saving_node/set_saving std_srvs/srv/SetBool "{data: false}"

# riprendi il salvataggio
ros2 service call /saving_node/set_saving std_srvs/srv/SetBool "{data: true}"
```

Utile durante i test per alternare rapidamente modalità "benchmark" e "produzione" senza restart.

## 6. Avvio tramite Servizio Systemd

Il Raspberry Pi è configurato per lanciare la pipeline in automatico all'avvio (trigger: reed sensor + magnetismo → alimentazione → boot). I service systemd coinvolti sono due:

- **`nautilus-vision.service`**: lancia `start_pipeline.sh`, che avvia acquisizione + salvataggio opzionale.
- **`lock-cameras.service`**: parte dopo `nautilus-vision.service` e lancia `lock_cameras.py`, che riapplica i parametri fotometrici (lens position, autofocus, exposure, colour gains) via `set_parameters`. È necessario perché `camera_ros` può rifiutare `AfMode` e `LensPosition` al boot su IMX708.

### Installazione (una tantum)

```bash
# copia gli unit file
sudo cp ~/nautilus-vision-pipeline/deploy/nautilus-vision.service \
        /etc/systemd/system/
sudo cp ~/nautilus-vision-pipeline/deploy/lock-cameras.service \
        /etc/systemd/system/
# copia lo script di avvio
sudo cp ~/nautilus-vision-pipeline/deploy/start_pipeline.sh \
        /usr/local/bin/
sudo chmod +x /usr/local/bin/start_pipeline.sh
# ricarica e abilita
sudo systemctl daemon-reload
sudo systemctl enable nautilus-vision.service
```

Grazie a `WantedBy=nautilus-vision.service` nel `[Install]` di `lock-cameras.service`, anche quest'ultimo viene avviato automaticamente ogni volta che parte `nautilus-vision`.

### Comandi utili

```bash
# applica subito le modifiche al .env senza riavviare la scheda
sudo systemctl restart nautilus-vision.service
# ferma la pipeline
sudo systemctl stop nautilus-vision.service
# stato dei servizi
sudo systemctl status nautilus-vision.service
sudo systemctl status lock-cameras.service
# log in tempo reale (FPS, metriche, errori)
journalctl -u nautilus-vision.service -f
journalctl -u lock-cameras.service -f
```

### Come funziona `lock_cameras.py`

1. legge `nautilus_camera.yaml` dal package share di `nautilus_camera`
2. estrae i parametri della whitelist (`AeEnable`, `AwbEnable`, `ExposureTime`, `ColourGains`, `AfMode`, `LensPosition`) per i due namespace
3. attende che il service `/stereo/{lx,rx}/camera/set_parameters` sia disponibile (fino a 30 s)
4. chiama `set_parameters` con i valori del YAML

Così la fonte di verità dei parametri fotometrici resta unica (il YAML) e non ci sono valori duplicati tra startup e lock.

## 7. Esempi di Configurazione per i Test (Fase 6 e 7)

Tutti i test si fanno con le camere **già attive** (dal boot o da un `stereo_camera.launch.py` manuale). I flag `enable_*` di `pipeline.launch.py` non vanno confusi con le variabili di `pipeline_config.env`: servono a controllare cosa parte a mano, non cosa parte al boot.

1. **Test: Solo Acquisizione (Baseline hardware)**
   - Le camere sono attive dal boot (`ENABLE_SAVING=false` nel `.env`)
   - Avvia a mano solo le metriche: `ros2 launch nautilus_camera stereo_camera.launch.py enable_metrics:=true enable_saving:=false`
   - Nota: se le camere sono già attive, questo comando darà errore per nodo duplicato. In alternativa avvia `metrics_node` direttamente con `ros2 run nautilus_camera metrics_node`.

2. **Test: Acquisizione + Detection (Nessun pre-processing)**
   - Le camere sono attive dal boot
   - `ros2 launch nautilus_perception pipeline.launch.py enable_detection:=true enable_enhancement:=false`
   - Nel `.yaml` di detection: imposta `num_threads` desiderato.

3. **Test: Full Pipeline con enhancement (WaterNet mai attiva di default)**
   - Le camere sono attive dal boot
   - `ros2 launch nautilus_perception pipeline.launch.py enable_detection:=true enable_enhancement:=true waternet_mode:=force_off`
   - WaterNet resta off: la pipeline usa solo CLAHE + sharpening.

4. **Test: Stress test termico (1 h a box chiusa)**
   - Avvia `metrics_node` per loggare FPS, jitter e skew ogni secondo.
   - Logga in parallelo temperatura e throttling: `vcgencmd measure_temp` e `vcgencmd get_throttled`.

5. **Test: Benchmark Fase 6 (5 configurazioni × 3 run)**
   - Usa `benchmarks/CONFIGS.md` come riferimento
   - `enable_debug:=false` sempre

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
| Lens position non applicata al boot | `camera_ros` rifiuta `AfMode`/`LensPosition` su IMX708 | `lock-cameras.service` li riapplica subito dopo: verifica `journalctl -u lock-cameras.service` |
| `saving_node` non scrive nulla | `save_directory` non scrivibile | `mkdir -p /home/nautilus/nautilus_data && chmod 755` |
| File JPEG con colori invertiti (rosso/blu) | conversione spazio colore non conforme | `saving_node` converte forzatamente in `bgr8` prima di `cv2.imwrite` |
| File parzialmente scritti o corrotti al distacco del magnete | cache I/O non svuotata prima del cut off | imposta `flush_every_n: 1` nel YAML per forzare `os.sync()` su MicroSD |
| Servizio systemd non parte | path in `ExecStart` sbagliato | controlla `journalctl -u nautilus-vision.service` |
| `pipeline.launch.py` va in errore "node already exists" | le camere sono già attive e `include_stereo_camera` non è `false` | non passare `include_stereo_camera:=true` se le camere sono già su |
| `ros2 launch` trova `pipeline.launch.py` ma non `stereo_camera.launch.py` | workspace non ricompilato | `colcon build --symlink-install && source install/setup.bash` |
