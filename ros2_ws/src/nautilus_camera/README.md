# nautilus_camera

Pacchetto ROS 2 dedicato all'acquisizione stereoscopica, al salvataggio su disco e alla diagnostica prestazionale del modulo di visione del veicolo Nautilus (host Raspberry Pi 5).

## Panoramica

Questo pacchetto si appoggia a [`camera_ros`](https://github.com/christianrauch/camera_ros) per interfacciarsi direttamente con i due sensori Pi Camera (CSI) e fornisce:

1. **Acquisizione** a 1280×720 @ 5 FPS, con parametri hardware centralizzati in un unico YAML.
2. **Benchmark** in tempo reale di FPS, jitter e skew stereo (`metrics_node`).
3. **Salvataggio** su filesystem locale in JPEG/PNG, con contatore incrementale e nessuna dipendenza da RTC (`saving_node`).

I tre blocchi possono essere attivati/disattivati indipendentemente tramite argomenti di lancio, per supportare sia l'uso in produzione (acquisizione + salvataggio) sia i benchmark puliti (solo acquisizione + metriche).

## Struttura del Pacchetto

```text
nautilus_camera/
├── config/
│   └── nautilus_camera.yaml          # unico file di configurazione
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

I parametri hardware di `camera_ros` **non vengono ripetuti** nel launch file: sono letti direttamente dal blocco `/stereo/lx/camera` e `/stereo/rx/camera` di `config/nautilus_camera.yaml`. Questo evita duplicazioni e drift di configurazione.

**Argomenti di lancio:**

| Argomento          | Default | Descrizione                                    |
|--------------------|---------|------------------------------------------------|
| `enable_metrics`   | `true`  | Avvia il nodo di benchmark                     |
| `enable_saving`    | `true`  | Avvia il nodo di salvataggio su disco          |
| `enable_display`   | `false` | Apre finestra OpenCV del `metrics_node`        |

**Esempi:**

```bash
# Pipeline standard: camera + metriche + salvataggio
ros2 launch nautilus_camera stereo_camera.launch.py

# Solo camera + metriche (benchmark pulito, zero I/O)
ros2 launch nautilus_camera stereo_camera.launch.py \
    enable_saving:=false enable_metrics:=true

# Solo camera + salvataggio (produzione)
ros2 launch nautilus_camera stereo_camera.launch.py \
    enable_saving:=true enable_metrics:=false

# Con finestra video (richiede GUI attiva)
ros2 launch nautilus_camera stereo_camera.launch.py enable_display:=true
```

## Nodi

### `metrics_node`

Nodo di benchmark: si sottoscrive ai due flussi immagine di `camera_ros`, li sincronizza con `message_filters.ApproximateTimeSynchronizer` e calcola a ogni coppia:

* **FPS reali** — frequenza effettiva di arrivo dei frame (finestra di 1 secondo).
* **Jitter** — deviazione standard degli intervalli tra frame consecutivi della camera sinistra (finestra di N frame).
* **Skew stereo** — differenza assoluta tra i timestamp della coppia left/right, riportata come media e massimo su finestra di N campioni.

È un **puro osservatore**: non pubblica nulla, non scrive su disco. Può essere spento senza impattare il resto della pipeline.

**Parametri principali** (vedi `config/nautilus_camera.yaml`):

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
* **Sessioni isolate**: ogni avvio crea una nuova sottocartella con ID sessione temporale.
* **Spegnibile a runtime** via ROS 2 Service (vedi sotto).
* **Skip dei frame vuoti**: i messaggi con data vuota vengono ignorati.

**Parametri principali:**

* `enable_saving` — stato iniziale (default `true`)
* `save_directory` — directory di output (default `/home/pi/nautilus_data`)
* `save_left` / `save_right` — salva solo una delle due camere
* `image_format` — `'jpg'` o `'png'`
* `jpeg_quality` — qualità JPEG (0-100)
* `filename_prefix` — prefisso dei file
* `max_files_per_session` — limite massimo di coppie salvate (0 = illimitato)

**Controllo a runtime (ROS 2 Service):**

Il nodo espone il service `~/set_saving` di tipo `std_srvs/SetBool`:

```bash
# disabilita il salvataggio (l'acquisizione e le metriche continuano)
ros2 service call /saving_node/set_saving std_srvs/srv/SetBool "{data: false}"

# riabilita
ros2 service call /saving_node/set_saving std_srvs/srv/SetBool "{data: true}"
```

Utile per passare rapidamente da modalità produzione a modalità benchmark senza riavviare il nodo.

## Configurazione

Tutto è centralizzato in `config/nautilus_camera.yaml`. Il file è organizzato in tre sezioni, ciascuna con il proprio match di nodo/namespace:

```yaml
# 1) parametri hardware camera_ros
/stereo/lx/camera:
  ros__parameters:
    camera: 0
    width: 1280
    height: 720
    FrameDurationLimits: [200000, 200000]   # 5 FPS

/stereo/rx/camera:
  ros__parameters:
    camera: 1
    width: 1280
    height: 720
    FrameDurationLimits: [200000, 200000]

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
    save_directory: '/home/pi/nautilus_data'
    image_format: 'jpg'
    jpeg_quality: 95
    filename_prefix: 'nautilus'
    save_left: true
    save_right: true
    queue_size: 10
    max_files_per_session: 0
```

## Dipendenze

* `camera_ros` — driver ufficiale Pi Camera per ROS 2
* `message_filters` — sincronizzazione stereo
* `sensor_msgs` — `Image`
* `std_srvs` — `SetBool` per il service di controllo
* `cv_bridge` — conversione ROS ↔ OpenCV
* `OpenCV` (Python) — encoding JPEG/PNG

## Test e Risultati (Fase 1)

Configurazione di riferimento: Pi 5, due Pi Camera v3 in box, 720p @ 5 FPS.

| Metrica | Valore tipico | Note |
| --- | --- | --- |
| FPS | 5.00 ± 0.05 | allineato a `FrameDurationLimits` |
| Jitter (sx) | ~0.3 ms | flusso pulito su bus CSI |
| Skew (sx-dx) | 1.0 – 2.0 ms | sincronizzazione timestamp ottima |

**Nota**: `camera_ros` emette warning iniziali relativi a `camera_info` mancante (file di calibrazione assente). La mancanza di calibrazione geometrica **non influisce** sull'acquisizione `image_raw` né sui benchmark di FPS/jitter/skew.

## Troubleshooting

* **Nessun topic pubblicato** → verifica che `camera_ros` veda le due camere: `rpicam-hello --list-cameras`.
* **Il nodo di salvataggio non scrive** → controlla che `save_directory` esista e sia scrivibile dall'utente che esegue ROS.
* **Skew elevato (> 20 ms)** → problema di sincronizzazione hardware, controlla cavi CSI e riduci risoluzione.
* **`colcon build` non trova `saving_node`** → verifica che `setup.py` contenga l'entry point e ricompila con `--symlink-install`.
