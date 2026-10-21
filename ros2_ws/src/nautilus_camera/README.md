# nautilus_camera

Pacchetto ROS 2 dedicato all'acquisizione stereoscopica, al salvataggio su disco e alla diagnostica prestazionale del modulo di visione del veicolo Nautilus (host Raspberry Pi 5).

## Panoramica

Questo pacchetto si appoggia a [`camera_ros`](https://github.com/christianrauch/camera_ros) per interfacciarsi direttamente con i due sensori Pi Camera (CSI) e fornisce:

1. **Acquisizione** a 1280×720 @ 5 FPS, con parametri hardware e fotometrici centralizzati in un unico YAML.
2. **Benchmark** in tempo reale di FPS, jitter e skew stereo (`metrics_node`).
3. **Salvataggio** su filesystem locale in JPEG/PNG, con contatore incrementale e nessuna dipendenza da RTC (`saving_node`).

Il blocco di acquisizione è l'unico che parte automaticamente al boot del Raspberry Pi (tramite `nautilus-vision.service`). Il salvataggio è opzionale, controllato da `ENABLE_SAVING` in `pipeline_config.env`. Il benchmark non parte mai da solo.

Lo stesso `camera_params.yaml` è letto anche da `lock_cameras.py` (deploy esterno), che riapplica i parametri fotometrici via `set_parameters` subito dopo il boot: così la fonte di verità è unica e non ci sono duplicazioni.

## Struttura del Pacchetto

```text
nautilus_camera/
├── config/
│   └── camera_params.yaml          # unico file di configurazione
├── launch/
│   └── stereo_camera.launch.py       # camera_ros + metrics + saving
├── nautilus_camera/
│   ├── __init__.py
│   ├── metrics_node.py               # benchmark FPS / jitter / skew
│   └── saving_node.py                # salvataggio stereo su disco
├── resource/
│   └── nautilus_camera
├── package.xml
├── setup.cfg
├── setup.py
└── test/
    └── test_flake8.py
```

## Launch File

### `stereo_camera.launch.py`

Fa partire in un colpo solo:

* due istanze del driver `camera_ros` in namespace separati (`/stereo/lx` e `/stereo/rx`);
* `metrics_node` (opzionale);
* `saving_node` (opzionale).

I parametri hardware di `camera_ros` **non vengono ripetuti** nel launch file: sono letti direttamente dai blocchi `/stereo/lx/camera` e `/stereo/rx/camera` di `config/camera_params.yaml`. Questo evita duplicazioni e drift di configurazione.

**Argomenti di lancio:**

| Argomento | Default | Descrizione |
|---|---|---|
| `params_file` | `camera_params.yaml` | Nome del file di configurazione in `config/` |
| `enable_metrics` (alias: `metrics`) | `false` | Avvia il nodo di benchmark (`metrics_node`) |
| `enable_display` (alias: `display`) | `''` (vuoto) | Apre finestra OpenCV del `metrics_node` (se vuoto, usa valore di `camera_params.yaml`) |

**Regola di priorità:**
Se `enable_display` non viene specificato da riga di comando, il nodo prende il valore del parametro `display` direttamente da `config/camera_params.yaml`. L'argomento da riga di comando ha effetto solo se esplicitato.

**Esempi:**

```bash
# Solo acquisizione (default)
ros2 launch nautilus_camera stereo_camera.launch.py

# Acquisizione + benchmark (run di test, prende display da YAML)
ros2 launch nautilus_camera stereo_camera.launch.py enable_metrics:=true

# Con finestra video forzata da CLI (richiede GUI attiva)
ros2 launch nautilus_camera stereo_camera.launch.py \
    metrics:=true display:=true
```

## Nodi

### `metrics_node`

Nodo di benchmark: si sottoscrive ai due flussi immagine di `camera_ros`, li sincronizza con `message_filters.ApproximateTimeSynchronizer` e calcola a ogni coppia:

* **FPS reali** — frequenza effettiva di arrivo dei frame (finestra di 1 secondo).
* **Jitter** — deviazione standard degli intervalli tra frame consecutivi della camera sinistra (finestra di N frame).
* **Skew stereo** — differenza assoluta tra i timestamp della coppia left/right, riportata come media e massimo su finestra di N campioni.

È un **puro osservatore**: non pubblica nulla, non scrive su disco. Può essere spento senza impattare il resto della pipeline.

**Parametri principali** (vedi `config/camera_params.yaml`):

* `left_topic`, `right_topic` — topic di input
* `sync_slop_sec` — tolleranza di sincronizzazione (default 0.05 s)
* `window_size` — ampiezza finestra statistica (default 30)
* `log_interval_sec` — intervallo di stampa a log (default 1.0 s)
* `display` — apre finestra OpenCV affiancata (default `false`)

**Esempio di output:**

```text
[metrics_node] FPS:  5.01 | Jitter(sx):   0.34 ms | Skew(sx-dx): avg  1.21 / max  2.05 ms
```

### `saving_node`

Nodo di salvataggio: sottoscrive le stesse coppie stereo e salva ogni frame su disco come JPEG (o PNG) in `<save_directory>/<YYYYmmdd-HHMMSS_session>/`.

**Caratteristiche:**

* **Naming incrementale**: `nautilus_lx_00000001.jpg`, `nautilus_rx_00000001.jpg`, … — ordinabile anche senza RTC.
* **Sessioni isolate e anti-collisione**: ogni avvio crea una nuova sottocartella con ID sessione temporale. Se l'orologio di sistema al boot è ripetuto (es. assenza di modulo RTC), il nodo appende un suffisso numerico progressivo (`session_1`, `session_2`, ecc.) per evitare sovrascritture accidentali.
* **Affidabilità su spegnimento brusco (reed switch)**: supporta `os.sync()` periodico o immediato via `flush_every_n` per garantire la persistenza dei frame su MicroSD prima dell'interruzione dell'alimentazione.
* **Spazio colore coerente**: forza l'encoding OpenCV in `bgr8` per evitare l'inversione di canali cromatici (rosso/blu) durante la scrittura dei file.
* **Spegnibile a runtime** via ROS 2 Service (vedi sotto).

**Parametri principali:**

* `enable_saving` — stato iniziale (default `true`)
* `save_directory` — directory di output (default `/home/nautilus/nautilus_data`)
* `save_left` / `save_right` — salva solo una delle due camere (default `true`)
* `image_format` — `'jpg'` o `'png'` (default `'jpg'`)
* `jpeg_quality` — qualità JPEG 0-100 (default `95`)
* `filename_prefix` — prefisso dei file (default `'nautilus'`)
* `queue_size` — profondità della coda di sincronizzazione (default `10`)
* `flush_every_n` — forza `os.sync()` ogni N coppie stereo (default `1`, flush immediato)
* `sync_slop_sec` — tolleranza di sincronizzazione temporale stereo (default `0.05` s)
* `max_files_per_session` — limite massimo di coppie salvate (default `0` = illimitato)

**Controllo a runtime (ROS 2 Service):**

Il nodo espone il service `~/set_saving` di tipo `std_srvs/SetBool`:

```bash
# disabilita il salvataggio (l'acquisizione continua)
ros2 service call /saving_node/set_saving std_srvs/srv/SetBool "{data: false}"

# riabilita
ros2 service call /saving_node/set_saving std_srvs/srv/SetBool "{data: true}"
```

Utile per passare rapidamente da modalità produzione a modalità benchmark senza riavviare il nodo.

## Configurazione

Tutto è centralizzato in `config/camera_params.yaml`. Il file è organizzato in tre sezioni, ciascuna con il proprio match di nodo/namespace:

```yaml
# 1) parametri hardware camera_ros
/stereo/lx/camera:
  ros__parameters:
    camera: 0
    width: 1280
    height: 720
    FrameDurationLimits: [200000, 200000]   # 5 FPS
    AeEnable: false
    AwbEnable: false
    ExposureTime: 20000
    ColourGains: [1.5, 1.5]
    AfMode: 0
    LensPosition: 2.6

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

# 2) parametri del nodo di benchmark
/**/metrics_node:
  ros__parameters:
    left_topic: '/stereo/lx/camera/image_raw'
    right_topic: '/stereo/rx/camera/image_raw'
    sync_slop_sec: 0.05
    window_size: 30
    log_interval_sec: 1.0
    display: false

# 3) parametri del nodo di salvataggio
/**/saving_node:
  ros__parameters:
    enable_saving: true
    left_topic: '/stereo/lx/camera/image_raw'
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

## Allineamento QoS (Quality of Service)

Tutti i profili QoS della pipeline sono definiti in un unico file,
`nautilus_common/config/qos_overrides.yaml`, che è la **single source of
truth**. Vedi [`nautilus_common/README.md`](../nautilus_common/README.md)
per l'architettura completa (SSOT + loader + `--params-file` per i C++).

Nel contesto di `nautilus_camera`:

* **`camera_ros`** (C++, lx + rx): pubblica i flussi raw e `camera_info` con
  la QoS definita nel YAML. Il file viene passato a `camera_ros` dal launch
  `stereo_camera.launch.py` come `--params-file` aggiuntivo
  (`parameters=[qos_yaml, config_file]`). Non esiste più una sezione
  `qos_overrides` in `config/camera_params.yaml`: è stata rimossa per
  evitare due fonti che possono divergere.

* **`metrics_node`** (Python): sottoscrive `image_raw` lx/rx con
  `IMAGE_SUB_QOS` (`best_effort`, `depth 5`). Il `depth 5` dà margine
  all'`ApproximateTimeSynchronizer` per accoppiare i frame stereo anche
  in presenza di jitter.

* **`saving_node`** (Python): sottoscrive `image_raw` lx/rx con
  `IMAGE_SUB_QOS` (`best_effort`, `depth 5`). La stessa motivazione:
  bufferizzare qualche frame in più evita di perdere coppie stereo da
  scrivere su disco quando il thread di I/O è occupato.

QoS effettive verificate sul campo (2026-10-18) con `ros2 topic info -v`:

| Topic | Reliability | Depth | Durability |
| --- | --- | --- | --- |
| `/stereo/{lx,rx}/camera/image_raw` | `BEST_EFFORT` | 1 | `VOLATILE` |
| `/stereo/{lx,rx}/camera/image_raw/compressed` | `BEST_EFFORT` | 1 | `VOLATILE` |
| `/stereo/{lx,rx}/camera/camera_info` | `RELIABLE` | 1 | `TRANSIENT_LOCAL` |

### Perché i parametri fotometrici sono nel YAML

I parametri `AeEnable`, `AwbEnable`, `ExposureTime`, `ColourGains` garantiscono coerenza radiometrica tra i due sensori. La stereo correlation (NCC, SGBM) fallisce se left e right hanno esposizione o white balance diversi. `AfMode` e `LensPosition` fissano la messa a fuoco: l'offset meccanico tra i due obiettivi è di +1.05 diottrie sulla sinistra.

`camera_ros` può rifiutare `AfMode` e `LensPosition` al boot su IMX708. In quel caso interviene `lock_cameras.py`, esterno al pacchetto, che rilegge questo stesso YAML e riapplica i valori via `set_parameters`. Vedi `docs/global_launch.md` sezione 6.

## Dipendenze

* `camera_ros` — driver ufficiale Pi Camera per ROS 2
* `message_filters` — sincronizzazione stereo
* `sensor_msgs` — `Image`
* `std_srvs` — `SetBool` per il service di controllo
* `std_msgs` — messaggi standard ROS 2
* `cv_bridge` — conversione ROS ↔ OpenCV
* `OpenCV` (Python) — encoding JPEG/PNG

## Test e Risultati (Fase 1)

Configurazione di riferimento: Pi 5, due Pi Camera v3 in box, 720p @ 5 FPS.

| Metrica | Valore tipico | Note |
| --- | --- | --- |
| FPS | 5.00 ± 0.05 | allineato a `FrameDurationLimits` |
| Jitter (sx) | ~0.3 ms | flusso pulito su bus CSI |
| Skew (sx-dx) | 1.0 – 2.0 ms | sincronizzazione timestamp ottima |

**QoS verificata** (2026-10-18): `camera_ros` pubblica `best_effort depth 1`
su raw e compressed, `reliable depth 1 transient_local` su `camera_info`.
Verificato con `ros2 topic info /stereo/lx/camera/image_raw -v`.

**Nota**: `camera_ros` emette warning iniziali relativi a `camera_info` mancante (file di calibrazione assente). La mancanza di calibrazione geometrica **non influisce** sull'acquisizione `image_raw` né sui benchmark di FPS/jitter/skew.

## Troubleshooting

* **Nessun topic pubblicato** → verifica che `camera_ros` veda le due camere: `rpicam-hello --list-cameras`.
* **Il nodo di salvataggio non scrive** → controlla che `save_directory` esista e sia scrivibile dall'utente che esegue ROS (`mkdir -p /home/nautilus/nautilus_data`).
* **File salvati con colori errati** → `saving_node` esegue la decodifica in BGR per `cv2.imwrite`; non alterare il `desired_encoding`.
* **Corruzione file su spegnimento reed switch** → mantieni `flush_every_n: 1` per forzare `os.sync()` su MicroSD ad ogni scrittura.
* **Lens position non applicata al boot** → `camera_ros` può rifiutare `AfMode`/`LensPosition`; verifica `journalctl -u lock-cameras.service`.
* **Skew elevato (> 20 ms)** → problema di sincronizzazione hardware, controlla cavi CSI e riduci risoluzione.
* **`colcon build` non trova `saving_node`** → verifica che `setup.py` contenga l'entry point e ricompila con `--symlink-install`.
