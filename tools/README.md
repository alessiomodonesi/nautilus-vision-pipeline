# Strumenti Operativi — Nautilus Vision Pipeline

Raccolta di script standalone per operazioni **fuori dalla pipeline real-time**:
post-missione, manutenzione, analisi offline. Non richiedono ROS 2 installato
(solo le librerie Python elencate), quindi girano anche su un portatile di
laboratorio senza ambiente ROS.

**Non confondere con `deploy/`:** in `deploy/` c'è ciò che gira sul Raspberry Pi
in automatico (systemd, config di runtime). Qui c'è ciò che lanci tu a mano,
tipicamente dopo che la missione è finita.

---

## Indice

* **[`extract_bag_frames.py`](#extract_bag_framespy)** — estrae frame JPEG da una rosbag MCAP Nautilus
* **[Workflow end-to-end](#workflow-end-to-end)** — record sul Pi → copia → estrazione
* **[Troubleshooting](#troubleshooting)**

---

## `extract_bag_frames.py`

Converte una rosbag MCAP registrata da `nautilus-bag.service` in una cartella
di file `.jpg` leggibili dai biologi, con metadata CSV e calibrazione stereo
opzionale.

### Perché è veloce (e senza perdita di qualità)

I messaggi `sensor_msgs/CompressedImage` in formato `jpeg` contengono **già un
file JPEG completo**: `msg.data` sono i bytes di un `.jpg` valido. Lo script fa
**passthrough dei bytes**, senza decodifica né ricompressione OpenCV. Questo
significa:

* zero perdita di qualità rispetto ai frame originali del sensore
* zero CPU sprecata (un `cv2.imdecode` + `cv2.imencode` costerebbe ~50 ms/frame)
* estrazione ~100× più veloce di un giro via `cv_bridge`

I frame estratti sono **bit-identici** a quelli che `camera_ros` ha prodotto al
momento dell'acquisizione.

### Installazione

```bash
pip install --user mcap mcap-ros2-support
```

Due pacchetti, nessuna dipendenza da ROS. Su Ubuntu 24.04 e derivate funziona
out-of-the-box.

### Uso base

```bash
# bag singola (un solo .mcap)
./extract_bag_frames.py ~/nautilus_bags/20261018_161956_smoke_test

# output in una cartella specifica
./extract_bag_frames.py ~/nautilus_bags/<bag> -o ~/frames/missione3

# bag rollata (più .mcap nella stessa directory)
./extract_bag_frames.py ~/nautilus_bags/20261018_162051_stereo -o ~/frames/missione3

# 1 frame ogni 10 (utile per dataset di re-training: riduce i duplicati)
./extract_bag_frames.py <bag> -o ~/frames/missione3 --every 10

# includi la calibrazione stereo (raccomandato)
./extract_bag_frames.py <bag> -o ~/frames/missione3 \
    --copy-calibration ~/nautilus-vision-pipeline/ros2_ws/src/nautilus_perception/nautilus_perception/data/stereo_calib_720p.npz

# esporta anche camera_info (vedi nota sotto)
./extract_bag_frames.py <bag> -o ~/frames/missione3 --dump-camera-info
```

### Opzioni

| Opzione | Default | Descrizione |
| --- | --- | --- |
| `bag` | *(obbligatorio)* | File `.mcap` o directory con più `.mcap` |
| `-o`, `--out` | `./frames` | Directory di output |
| `--prefix` | `nautilus` | Prefisso dei file (`<prefix>_lx_00000001.jpg`) |
| `--every` | `1` | Estrai 1 frame ogni N coppie |
| `--sync-slop-ms` | `50.0` | Tolleranza di accoppiamento stereo in ms |
| `--no-sync` | *(off)* | Estrai lx e rx separatamente, senza accoppiare |
| `--dump-camera-info` | *(off)* | Esporta `camera_info` come JSON (può essere 0×0, vedi sotto) |
| `--copy-calibration` | *(nessuno)* | Copia un file `.npz` di calibrazione nell'output |

### Output

```text
frames/
├── nautilus_lx_00000001.jpg     ← frame sinistro, ordine crescente
├── nautilus_rx_00000001.jpg     ← frame destro accoppiato
├── nautilus_lx_00000002.jpg
├── nautilus_rx_00000002.jpg
├── ...
├── metadata.csv                 ← timestamp e mapping file → frame
├── stereo_calib_720p.npz        ← se --copy-calibration
└── camera_info/                 ← se --dump-camera-info, e solo se non 0×0
    ├── lx.json
    └── rx.json
```

**`metadata.csv`** contiene una riga per ogni file:

| Campo | Significato |
| --- | --- |
| `frame` | Contatore incrementale (1, 2, 3, ...) |
| `side` | `lx` o `rx` |
| `filename` | Nome del file `.jpg` |
| `log_time_ns` | Timestamp di ricezione nella bag (monotono, affidabile) |
| `stamp_ns` | `header.stamp` originale (acquisizione camera) |

Il contatore è monotonicamente crescente e ordinabile anche in assenza di RTC
(caso tipico del Raspberry Pi: all'avvio l'orologio può essere sbagliato).

### Nota su `camera_info` (0×0)

`camera_ros` emette un messaggio `camera_info` a ogni frame, ma se non ha un
file di calibrazione configurato (`camera_info_url` nel YAML) il messaggio è
**vuoto**: `width=0, height=0, k=[], d=[]`. Lo script:

* non scrive JSON per i `camera_info` 0×0 (sarebbero file inutili)
* stampa un warning esplicito che rimanda a `--copy-calibration`

La **vera calibrazione stereo** per il post-processing è in
`stereo_calib_720p.npz` (quella caricata da `detection_node`), non nel
`camera_info` del topic. Quindi il flag `--copy-calibration` è la scelta
giusta per la maggior parte dei casi.

Se in futuro configurerai `camera_ros` con un `camera_info_url` valido, i
JSON verranno popolati automaticamente senza modifiche allo script.

### Limite noto: memoria per bag molto grandi

Lo script legge **tutti** i bytes dei frame selezionati in un dizionario prima
di scriverli. Stima: ~35 KB/frame × 2 lati × N coppie.

| Durata bag a 5 FPS | Coppie | RAM richiesta |
| --- | --- | --- |
| 10 min | ~3 000 | ~200 MB |
| 30 min | ~9 000 | ~650 MB |
| 2 h | ~36 000 | ~2.5 GB |
| 8 h | ~144 000 | ~10 GB |

Per una missione tipica (≤ 1 h) va benissimo su un portatile moderno. Per bag
più lunghe, o in caso di RAM scarsa, si può riscrivere il pass 2 in streaming
(facile: iterare e scrivere man mano invece di accumulare). Non è stato fatto
ora per mantenere il codice leggibile, ma è una modifica di ~20 righe se
serve.

**Workaround pratico per bag lunghe:** usa `--every 2` o `--every 5` per
estrarre un sottoinsieme. La RAM scala linearmente con `N / every`.

---

## Workflow end-to-end

### Sul Pi (durante la missione)

La bag parte in automatico se `ENABLE_BAG=true` in `pipeline_config.env`:

```bash
# attiva la bag per la prossima missione
sed -i 's/^export ENABLE_BAG=false/export ENABLE_BAG=true/' \
    ~/nautilus-vision-pipeline/pipeline_config.env
sudo systemctl restart nautilus-vision.service

# verifica che stia registrando
systemctl status nautilus-bag.service       # -> active (running)
journalctl -u nautilus-bag.service -f       # -> "Recording..."

# a fine missione, ferma con SIGINT (chiude MCAP in modo pulito)
sudo systemctl stop nautilus-vision.service
```

Le bag finiscono in `/home/nautilus/nautilus_bags/<YYYYmmdd_HHMMSS>_stereo/`.

### Sul portatile (post-missione)

```bash
# 1. copia la bag dal Pi
rsync -avz --progress \
    nautilus@nautilus-pi:~/nautilus_bags/20261018_162051_stereo \
    ~/missioni/missione3/

# 2. ispeziona la bag prima di estrarre
ros2 bag info ~/missioni/missione3/20261018_162051_stereo
# oppure, senza ROS: usa mcap info (se installato)
# mcap info ~/missioni/missione3/20261018_162051_stereo/*.mcap

# 3. estrai frame + calibrazione + metadata
./tools/extract_bag_frames.py \
    ~/missioni/missione3/20261018_162051_stereo \
    -o ~/missioni/missione3/frames \
    --copy-calibration ~/nautilus-vision-pipeline/ros2_ws/src/nautilus_perception/nautilus_perception/data/stereo_calib_720p.npz

# 4. verifica output
ls ~/missioni/missione3/frames/*.jpg | wc -l
# deve essere 2 × numero di coppie

# 5. (opzionale) crea dataset YOLO filtrato per varianza
python3 ~/nautilus-vision-pipeline/benchmarks/tools/clean_dataset.py \
    ~/missioni/missione3/frames --out ~/missioni/missione3/dataset_clean
```

---

## Troubleshooting

| Sintomo | Causa probabile | Soluzione |
| --- | --- | --- |
| `ModuleNotFoundError: No module named 'mcap'` | dipendenze mancanti | `pip install --user mcap mcap-ros2-support` |
| `Nessun file .mcap in <dir>` | path errato o bag vuota | verifica con `ls <dir>/*.mcap` |
| `Coppie stereo: 0 \| lx orfani: N` | timestamp troppo distanti | aumenta `--sync-slop-ms`, es. 200 |
| `camera_info lx vuoto (0x0)` | `camera_ros` senza calibrazione | usa `--copy-calibration`, ignora il warning |
| `[warn] calibrazione non trovata` | path sbagliato a `.npz` | verifica con `ls <path>` |
| Immagini con colori invertiti | bag corrotta o encoder errato | controlla che `camera_ros` pubblichi `rgb8` |
| Estrazione lentissima | pass 2 legge tutta la bag | usa `--every N` per ridurre i frame |
| `xdg-open: no method available` | Pi headless | apri i frame dal tuo PC con `scp` |
| `camera_info/` esiste ma è vuota | tutti i lati erano 0×0 | atteso, nessun JSON scritto per scelta |

---

## Riferimenti

* **Registrazione bag:** `deploy/bag/` (service, script, QoS override)
* **Configurazione topic:** `deploy/bag/bag_qos.yaml`
* **Documentazione pipeline:** `docs/global_launch.md`
* **Estrazione dataset per YOLO:** `benchmarks/tools/clean_dataset.py`
