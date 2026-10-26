# Strumenti Operativi — Nautilus Vision Pipeline

Raccolta di script standalone per operazioni **fuori dalla pipeline real-time**: post-missione, manutenzione e analisi offline dei dati acquisiti.
Non richiedono ROS 2 installato (richiedono unicamente le librerie Python elencate), quindi possono essere eseguiti direttamente su un laptop da laboratorio senza un ambiente ROS completo.

> **Differenza con `deploy/` e `deploy/bag/`:**
>
> * In [`deploy/`](../deploy/) e [`deploy/bag/`](../deploy/bag/) risiedono i componenti che girano a bordo del Raspberry Pi (servizi systemd, configurazioni di runtime CycloneDDS, script di registrazione `ros2 bag`).
> * Il comportamento al boot è controllato dalle variabili in [`pipeline_config.env`](../pipeline_config.env) (in particolare `ENABLE_BAG` e `NAUTILUS_BAG_DIR`).
> * In `tools/` si trovano invece gli strumenti offline da lanciare manualmente dopo il recupero della fototrappola o del robot per estrarre immagini, metadati e calibrazione.

---

## Indice

* **[Panoramica Architettura Bag & Salvataggio](#panoramica-architettura-bag--salvataggio)** — Come vengono generate le registrazioni a bordo
* **[`extract_bag_frames.py`](#extract_bag_framespy)** — Estrazione frame JPEG bit-identical da rosbag MCAP
* **[Workflow End-to-End](#workflow-end-to-end)** — Configurazione Pi → Registrazione → Copia → Estrazione e Dataset
* **[Troubleshooting](#troubleshooting)** — Diagnostica dei problemi più comuni
* **[Riferimenti](#riferimenti)**

---

## Panoramica Architettura Bag & Salvataggio

A bordo del Raspberry Pi 5, la registrazione video non viene eseguita tramite un nodo custom di scrittura file su disco (che consumerebbe CPU preziosa e rischierebbe perdite di frame), ma tramite il formato ad alte prestazioni **MCAP** nativo di ROS 2:

1. **Configurazione ambiente ([`pipeline_config.env`](../pipeline_config.env)):**
   * `ENABLE_BAG=false` *(default)*: le telecamere trasmettono in DDS, ma la persistenza su disco è disattivata (ideale durante i benchmark o navigazione in tempo reale).
   * `ENABLE_BAG=true`: abilita la registrazione automatica su MicroSD/NVMe all'avvio del robot (trigger reed switch).
   * `NAUTILUS_BAG_DIR=/home/nautilus/nautilus_bags`: directory di destinazione delle bag.

2. **Automazione Systemd ([`deploy/bag/nautilus-bag.service`](../deploy/bag/nautilus-bag.service)):**
   * Servizio secondario legato a `nautilus-vision.service` (`PartOf`, `Requires`, `WantedBy`).
   * Tramite `ExecCondition`, verifica se `ENABLE_BAG=true` nel file `pipeline_config.env`. Se disabilitato, il servizio non parte e non consuma risorse.
   * Quando il robot viene spento o il servizio viene fermato, systemd invia il segnale `KillSignal=SIGINT`, consentendo al recorder ROS 2 di finalizzare correttamente i chunk e l'indice del file MCAP (evitando corruzioni).

3. **Registrazione flussi ([`deploy/bag/record_stereo_bag.sh`](../deploy/bag/record_stereo_bag.sh)):**
   * Registra i flussi stereo compressi JPEG pubblicati da `camera_ros`:
     * `/stereo/lx/camera/image_raw/compressed`
     * `/stereo/rx/camera/image_raw/compressed`
     * `/stereo/lx/camera/camera_info`
     * `/stereo/rx/camera/camera_info`
   * Applica i profili di Quality of Service dedicati in [`deploy/bag/bag_qos.yaml`](../deploy/bag/bag_qos.yaml) (`best_effort`, `keep_last`, `depth 1` per i frame; `reliable`, `transient_local` per `camera_info`).
   * Rotazione automatica dei file (rolling policy): split ogni 300 secondi (5 minuti) o al raggiungimento di 2 GiB (`--max-bag-duration 300`, `--max-bag-size 2147483648`), con output nella cartella `NAUTILUS_BAG_DIR/<TIMESTAMP>_<NAME>`.

---

## `extract_bag_frames.py`

Converte una rosbag MCAP registrata da `deploy/bag/record_stereo_bag.sh` (o `nautilus-bag.service`) in una directory di file `.jpg` leggibili dai biologi o adatti per annotazione e re-training di modelli di rilevamento, generando un file CSV di metadati temporali e copiando opzionalmente i parametri di calibrazione stereo.

### Perché è veloce (e senza perdita di qualità)

I messaggi ROS `sensor_msgs/CompressedImage` in formato `jpeg` contengono già un flusso binario JPEG valido. Lo script effettua un **passthrough diretto dei byte**:

* **Zero perdita di qualità:** nessuna decodifica o ricompressione OpenCV (i frame sono bit-identici a quelli prodotti dall'hardware `camera_ros`).
* **Zero overhead computazionale:** estrazione ~100× più veloce rispetto all'uso di nodi ROS 2 o conversioni tramite `cv_bridge` (nessun consumo di ~50 ms/frame per de-codifica).
* **Nessun ambiente ROS necessario:** utilizza solo la libreria pura Python `mcap`.

### Installazione Dipendenze

```bash
pip install --user mcap mcap-ros2-support
```

Questi due pacchetti Python permettono la lettura del formato MCAP e la decodifica dei messaggi serializzati ROS 2 su qualsiasi sistema operativo (Linux, macOS, Windows).

### Utilizzo

```bash
# Bag singola (un solo file .mcap)
./tools/extract_bag_frames.py ~/nautilus_bags/20261018_161956_smoke_test

# Output in una directory personalizzata
./tools/extract_bag_frames.py ~/nautilus_bags/<bag_name> -o ~/frames/missione1

# Bag rollata (directory con più file .mcap splittati da ros2 bag)
./tools/extract_bag_frames.py ~/nautilus_bags/20261018_162051_stereo -o ~/frames/missione1

# Sottocampionamento: 1 frame ogni 10 (utile per dataset di training per evitare duplicati)
./tools/extract_bag_frames.py <bag_path> -o ~/frames/missione1 --every 10

# Copia contestuale del file di calibrazione stereo (consigliato per post-processing 3D)
./tools/extract_bag_frames.py <bag_path> -o ~/frames/missione1 \
    --copy-calibration ~/nautilus-vision-pipeline/ros2_ws/src/nautilus_perception/nautilus_perception/data/stereo_calib_720p.npz

# Esporta anche i metadati camera_info emessi dal driver (se presenti)
./tools/extract_bag_frames.py <bag_path> -o ~/frames/missione1 --dump-camera-info
```

### Parametri e Opzioni CLI

| Opzione | Default | Descrizione |
| --- | --- | --- |
| `bag` | *(obbligatorio)* | Percorso al singolo file `.mcap` o alla directory contenente i file `.mcap` |
| `-o`, `--out` | `./frames` | Directory di output per il salvataggio dei frame e metadati |
| `--prefix` | `nautilus` | Prefisso dei file estratti (`<prefix>_lx_00000001.jpg`) |
| `--every` | `1` | Estrae 1 coppia ogni N (per sottocampionare la frequenza temporale) |
| `--sync-slop-ms` | `50.0` | Finestra massima di tolleranza temporale tra frame sinistro e destro (in ms) |
| `--no-sync` | *(disabilitato)* | Estrae i frame sinistri e destri in modo indipendente, senza accoppiamento stereo |
| `--dump-camera-info` | *(disabilitato)* | Esporta i messaggi `camera_info` in formato JSON (se non 0×0) |
| `--copy-calibration` | *(nessuno)* | Copia il file `.npz` di calibrazione stereo specificato nella directory di output |

### Struttura Output

```text
frames/
├── nautilus_lx_00000001.jpg     ← Frame sinistro (indicizzazione progressiva a 8 cifre)
├── nautilus_rx_00000001.jpg     ← Frame destro corrispondente sincronizzato
├── nautilus_lx_00000002.jpg
├── nautilus_rx_00000002.jpg
├── ...
├── metadata.csv                 ← Tracciamento temporale e mapping per ogni immagine
├── stereo_calib_720p.npz        ← File di calibrazione stereo (se specificato con --copy-calibration)
└── camera_info/                 ← Esportazione JSON camera_info (se specificato con --dump-camera-info)
    ├── lx.json
    └── rx.json
```

#### Struttura di `metadata.csv`

| Colonna | Significato |
| --- | --- |
| `frame` | Indice sequenziale della coppia stereo (1, 2, 3, ...) |
| `side` | Telecamera di riferimento (`lx` oppure `rx`) |
| `filename` | Nome del file immagine `.jpg` generato |
| `log_time_ns` | Timestamp nanosecondi di ricezione nella rosbag (monotono crescente, affidabile) |
| `stamp_ns` | `header.stamp` originale di esposizione del sensore (acquisizione driver) |

> [!NOTE]
> La presenza di `log_time_ns` garantisce l'ordinamento cronologico corretto dei frame anche in assenza di un modulo hardware RTC (Real Time Clock), situazione tipica del Raspberry Pi al boot prima di un'eventuale sincronizzazione oraria via NTP/Chrony.

### Gestione di `camera_info` (0×0)

Il driver `camera_ros` pubblica messaggi su `/stereo/{lx,rx}/camera/camera_info` a ogni frame. Se non viene impostato un file di calibrazione intrinseca tramite `camera_info_url` nel file YAML, i campi dimensionali risultano `width=0, height=0`.

* Lo script rileva questa condizione ed evita di generare file JSON vuoti o inutili.
* La geometria e la matrice estrinseca/intrinseca stereo della fototrappola sono memorizzate in `ros2_ws/src/nautilus_perception/nautilus_perception/data/stereo_calib_720p.npz` (utilizzato da `detection_node`). Si raccomanda pertanto di usare sempre `--copy-calibration`.

### Efficienza della Memoria su Registrazioni Estese

Lo script adotta una strategia a due passaggi:

1. **Passaggio 1 (indicizzazione leggera):** scansione dei soli metadati per calcolare l'accoppiamento stereo e applicare il filtro `--every`.
2. **Passaggio 2 (scrittura diretta):** caricamento selettivo dei soli frame richiesti.

Per registrazioni molto prolungate (oltre 2–4 ore), il consumo di RAM scala linearmente con il numero di frame. Per ridurre l'impronta di memoria durante la creazione di dataset, impostare `--every 2` o `--every 5`.

---

## Workflow End-to-End

### 1. Configurazione e Avvio sul Raspberry Pi

#### Registrazione automatica al boot (Missione reale)

Abilitare la registrazione modificando `pipeline_config.env`:

```bash
# Modifica il flag ENABLE_BAG da false a true
sed -i 's/^export ENABLE_BAG=false/export ENABLE_BAG=true/' \
    ~/nautilus-vision-pipeline/pipeline_config.env

# Riavvia il servizio di visione (nautilus-bag.service partirà automaticamente in parallelo)
sudo systemctl restart nautilus-vision.service

# Verifica lo stato del recorder
systemctl status nautilus-bag.service       # active (running)
journalctl -u nautilus-bag.service -f       # log di registrazione in tempo reale
```

A fine missione, fermare il servizio per chiudere la registrazione MCAP:

```bash
sudo systemctl stop nautilus-vision.service
```

Il servizio `nautilus-bag.service` intercetta l'arresto via `KillSignal=SIGINT`, chiude e indicizza i file MCAP senza perdita di pacchetti. Le registrazioni vengono salvate in `/home/nautilus/nautilus_bags/<YYYYmmdd_HHMMSS>_stereo/`.

#### Registrazione manuale (Test di laboratorio o debug)

Se i servizi systemd sono disattivati e le telecamere sono già attive (es. lanciate tramite `stereo_camera.launch.py`), è possibile avviare una bag manuale con un nome personalizzato:

```bash
# Avvio manuale specificando il nome della sessione (es. test_vasca)
~/nautilus-vision-pipeline/deploy/bag/record_stereo_bag.sh test_vasca

# Interrompere con Ctrl+C per finalizzare il file MCAP
```

### 2. Trasferimento Dati su Workstation / Laptop

Dopo il recupero del robot o della scheda SD, copiare la cartella della sessione sul proprio computer:

```bash
rsync -avz --progress \
    nautilus@nautilus-pi:~/nautilus_bags/20261018_162051_stereo \
    ~/missioni/missione1/
```

### 3. Ispezione ed Estrazione Offline

Sul proprio computer (anche senza ROS installato):

```bash
# 1. Verifica preliminare della bag
# (Se è presente ROS 2):
ros2 bag info ~/missioni/missione1/20261018_162051_stereo
# (In alternativa tramite CLI mcap):
# mcap info ~/missioni/missione1/20261018_162051_stereo/*.mcap

# 2. Estrazione delle immagini con calibrazione stereo inclusa
./tools/extract_bag_frames.py \
    ~/missioni/missione1/20261018_162051_stereo \
    -o ~/missioni/missione1/frames \
    --copy-calibration ~/nautilus-vision-pipeline/ros2_ws/src/nautilus_perception/nautilus_perception/data/stereo_calib_720p.npz

# 3. Controllo dell'output
ls ~/missioni/missione1/frames/*.jpg | wc -l
# Il numero totale di file JPG deve essere esattamente pari a 2 × numero di coppie
```

### 4. Filtraggio e Preparazione Dataset per Training (Opzionale)

Se le immagini estratte devono essere utilizzate per arricchire il dataset di object detection (es. scartando frame torbidi, sfocati o privi di contrasto):

```bash
python3 ~/nautilus-vision-pipeline/benchmarks/datasets/tools/clean_dataset.py \
    ~/missioni/missione1/frames \
    --out ~/missioni/missione1/dataset_clean
```

---

## Troubleshooting

| Sintomo | Possibile Causa | Risoluzione |
| --- | --- | --- |
| `ModuleNotFoundError: No module named 'mcap'` | Pacchetti Python mancanti | Eseguire `pip install --user mcap mcap-ros2-support` |
| `Nessun file .mcap in <dir>` | Percorso errato o cartella bag vuota | Verificare con `ls <dir>/*.mcap` |
| `Coppie stereo: 0 \| lx orfani: N` | Differenza di clock/latenza tra i canali CSI | Aumentare il margine di sincronizzazione con `--sync-slop-ms 150` o `--sync-slop-ms 200` |
| `camera_info lx vuoto (0x0)` | `camera_ros` non ha `camera_info_url` | Comportamento normale; utilizzare `--copy-calibration` per includere `stereo_calib_720p.npz` |
| `[warn] calibrazione non trovata` | Percorso errato al file `.npz` | Controllare che il file esista in `ros2_ws/src/nautilus_perception/nautilus_perception/data/stereo_calib_720p.npz` |
| Immagini con tonalità alterate | Profilo colore driver errato | Verificare che `camera_ros` pubblichi su formato `rgb8` o `bgr8` coerente |
| `nautilus-bag.service` non parte al boot | `ENABLE_BAG` è impostato su `false` | Controllare `pipeline_config.env` e assicurarsi che contenga `export ENABLE_BAG=true` |
| File MCAP corrotto o incompleto | Arresto forzato (`SIGKILL` anziché `SIGINT`) | Fermare sempre con `sudo systemctl stop nautilus-vision.service` o `Ctrl+C` per permettere la finalizzazione dell'indice MCAP |

---

## Riferimenti

* **Configurazione Globale Pipeline:** [`pipeline_config.env`](../pipeline_config.env)
* **Suite Registrazione Rosbag:** [`deploy/bag/`](../deploy/bag/)
  * Script di registrazione: [`deploy/bag/record_stereo_bag.sh`](../deploy/bag/record_stereo_bag.sh)
  * Servizio systemd: [`deploy/bag/nautilus-bag.service`](../deploy/bag/nautilus-bag.service)
  * Profili QoS: [`deploy/bag/bag_qos.yaml`](../deploy/bag/bag_qos.yaml)
* **Guida al Lancio della Pipeline:** [`docs/LAUNCH.md`](../docs/LAUNCH.md)
* **Strumento di Pulizia e Filtraggio Dataset:** [`benchmarks/datasets/tools/clean_dataset.py`](../benchmarks/datasets/tools/clean_dataset.py)
* **Calibrazione Stereo Ufficiale:** [`ros2_ws/src/nautilus_perception/nautilus_perception/data/stereo_calib_720p.npz`](../ros2_ws/src/nautilus_perception/nautilus_perception/data/stereo_calib_720p.npz)
