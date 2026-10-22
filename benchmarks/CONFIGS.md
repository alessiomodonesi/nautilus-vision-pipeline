# Fase 6 — Configurazioni di Benchmark

Questo documento descrive le configurazioni di test per il benchmark
prestazionale e termico della pipeline Nautilus Vision (Fase 6 e 7 di
`docs/TODO.md`).

Ogni configurazione va eseguita **3 volte** sullo stesso hardware, con la
stessa scena e la stessa illuminazione, per valutare la varianza.

---

## Prerequisiti comuni

Prima di ogni sessione:

```bash
# 1. stop (systemd sa che è volontario → non riavvia)
sudo systemctl stop nautilus-bag.service
sudo systemctl stop nautilus-vision.service
sudo systemctl stop lock-cameras.service

# 2. disable (impedisce la ripartenza al prossimo boot — utile in Fase B
#    dove si riavvia per l'overclock)
sudo systemctl disable nautilus-bag.service
sudo systemctl disable nautilus-vision.service
sudo systemctl disable lock-cameras.service

# 3. conferma
systemctl is-active nautilus-vision.service   # atteso: inactive
systemctl is-enabled nautilus-vision.service  # atteso: disabled

# 4. SOLO ORA puoi uccidere i residui. Se lo fai prima dello stop,
#    systemd interpreta la morte come crash e riavvia il servizio
#    (Restart=on-failure, RestartSec=5) — è ciò che ha invalidato i
#    primi run del 20/10/2026.
pkill -f "ros2 launch nautilus_camera" || true
pkill -f camera_node || true
pkill -f detection_node || true
pkill -f enhancement_node || true
pkill -f "ros2 bag record" || true
sleep 3

# 4b. verifica che il pkill abbia funzionato (facoltativo ma utile
#     prima di un batch: il wrapper fa gli stessi check ad ogni run,
#     ma se il primo abortisce vuoi sapere subito cosa è attivo)
ps aux | grep -E "camera_node|detection_node|enhancement_node|ros2 bag record" | grep -v grep
# non deve stampare nulla
ros2 node list
# non deve stampare nulla (o solo /rosout)
ros2 topic info /stereo/lx/camera/image_raw -v
# atteso: "Publisher count: 0"

# 5. source ambiente
source /opt/ros/jazzy/setup.bash
source ~/nautilus-vision-pipeline/ros2_ws/install/setup.bash
ls ~/nautilus-vision-pipeline/ros2_ws/src/nautilus_perception/nautilus_perception/data/weights/
```

Durante i benchmark:

- **Nessun salvataggio attivo** — `saving_node` non è più nel launch di
  produzione e `nautilus-bag.service` viene fermato da `systemctl stop
  nautilus-vision.service` a inizio benchmark. Nessun I/O continuativo
  su MicroSD durante le misure.
- **`enable_metrics` sempre a `true`** — controprova FPS dal nodo metriche
- **`enable_debug` sempre a `false`** — nessuna finestra OpenCV

**Nota su `systemctl mask`**: se i file unit sono stati copiati con `sudo cp`,
`systemctl mask` fallisce con `File … already exists.` In quel caso
`disable` + `stop` è sufficiente per la sessione di benchmark. Per un mask
vero occorre spostare prima i file `.service` in `.service.bak`,
`daemon-reload`, poi `mask`. Non necessario per i benchmark.

---

## Piano di test

Il piano è articolato in **due fasi sequenziali**, per distinguere il
contributo del clock CPU da quello delle scelte software (modello,
quantizzazione, risoluzione).

### Fase A — senza overclock (riferimento)

6 configurazioni, con la CPU a clock **nominale** (2400 MHz su Pi 5).
È la baseline pulita: se qualcosa non funziona qui, l'overclock non fa
altro che aggiungere rumore termico.

| # | ID | Config | Modello | half_res | imgsz |
| --- | --- | --- | --- | --- | --- |
| 1 | `A_baseline` | solo camera | — | — | — |
| 2 | `B1_pt` | camera + detection | `yolov8n.pt` | True | 640 |
| 3 | `B2_ov_fp32` | camera + detection | `yolov8n_640_fp32_openvino_model` | False | 640 |
| 4 | `B3_ov_int8_640` | camera + detection | `yolov8n_640_int8_openvino_model` | False | 640 |
| 5 | `B4_ov_int8_416` | camera + detection | `yolov8n_416_int8_openvino_model` | False | 416 |
| 6 | `C_full` | camera + enh + detection | `yolov8n_640_fp32_openvino_model` | False | 640 |

### Fase B — con overclock (senza baseline)

5 configurazioni, con la CPU **overclockata** (2800 MHz). `A_baseline` è
esclusa: il collo di bottiglia dell'acquisizione non è la CPU, e
l'overclock non porterebbe beneficio spendendo budget termico.

Ogni config ha la stessa parametrizzazione della Fase A ma con suffisso
`_oc` per non collidere nei CSV.

| # | ID | Config | Modello | half_res | imgsz |
| --- | --- | --- | --- | --- | --- |
| 1 | `B1_pt_oc` | camera + detection | `yolov8n.pt` | True | 640 |
| 2 | `B2_ov_fp32_oc` | camera + detection | `yolov8n_640_fp32_openvino_model` | False | 640 |
| 3 | `B3_ov_int8_640_oc` | camera + detection | `yolov8n_640_int8_openvino_model` | False | 640 |
| 4 | `B4_ov_int8_416_oc` | camera + detection | `yolov8n_416_int8_openvino_model` | False | 416 |
| 5 | `C_full_oc` | camera + enh + detection | `yolov8n_640_fp32_openvino_model` | False | 640 |

### Totale run

- **Fase A**: 6 config × 3 run = 18 run
- **Fase B**: 5 config × 3 run = 15 run
- **Totale**: 33 run, ~4.5 h stimate (a ~8 min per run, vedi sezione successiva)

L'analisi successiva confronta `B*` vs `B*_oc` e `C_full` vs `C_full_oc`
sugli stessi grafici, per quantificare il guadagno dell'overclock in FPS
e latenza rispetto all'aumento di temperatura e ai flag di throttling.

---

## Gestire l'overclock

Il file di configurazione del firmware è `/boot/firmware/config.txt`. La
sezione `[pi5]` controlla i clock del Pi 5.

### Senza overclock (nominale, 2400 MHz)

Rimuovi o commenta la sezione `[pi5]` (i valori di default del firmware
valgono 2400 MHz per la CPU):

```ini
[pi5]
# nessun overclock
```

Oppure esplicita il valore nominale:

```ini
[pi5]
arm_freq=2400
```

### Con overclock (2800 MHz)

```ini
[pi5]
arm_freq=2800
gpu_freq=1000
over_voltage_delta=50000
```

**Warning alimentazione**: con `arm_freq=2800` e `over_voltage_delta=50000`,
il Pi 5 richiede un alimentatore da **5V/5A** (USB-C PD). Un alimentatore
sottodimensionato porta a throttling da undervoltage (`get_throttled` bit
`0x1`), che invalida i benchmark.

**Warning termico**: con OC attivo e box chiusa, il Pi 5 può raggiungere il
soft-throttling in pochi minuti sotto carico YOLO. Se il dissipatore è
passivo (nessuna ventola), l'OC potrebbe non essere utilizzabile in
produzione — è esattamente quello che questa fase vuole misurare.

### Applicare le modifiche

Dopo ogni modifica a `config.txt`:

```bash
sudo reboot
```

Al riavvio, verifica il clock attivo:

```bash
vcgencmd measure_clock arm
# 2400000000 => 2400 MHz (nominale, Fase A)
# 2800000000 => 2800 MHz (OC, Fase B)
```

### Verifica del throttling durante i run

I CSV generati da `system_monitor.py` contengono la colonna `throttled`
con il valore di `vcgencmd get_throttled`. I bit significativi:

| Bit | Hex | Significato |
| --- | --- | --- |
| 0 | `0x1` | undervoltage rilevato (al boot) |
| 1 | `0x2` | ARM frequency capped |
| 2 | `0x4` | currently throttled |
| 3 | `0x8` | soft temperature limit reached |
| 16 | `0x10000` | undervoltage è occorso dall'ultimo reboot |
| 17 | `0x20000` | ARM frequency capped dall'ultimo reboot |
| 18 | `0x40000` | throttling è occorso dall'ultimo reboot |
| 19 | `0x80000` | soft temperature limit occorso dall'ultimo reboot |

Se uno dei bit `16`-`19` è settato, la run è **compromessa** e va scartata.
Il wrapper `run_benchmark.sh` scrive il valore iniziale e finale nel
metadata, ma il controllo esaustivo va fatto a posteriori sul CSV system.

Anche la colonna `cpu_clock_mhz` va controllata: se durante la run scende
sotto il valore nominale della fase, c'è stato throttling.

---

## Scena di test e considerazioni

Per ottenere un benchmark attendibile anche in assenza di un ambiente subacqueo reale, la scena inquadrata dalle telecamere deve rispettare due requisiti: **oggetti rilevabili** e **texture sufficiente**.

- **YOLO e inferenza**: Il tempo di inferenza (e quindi la latenza) dipende esclusivamente dalle dimensioni dei tensori (es. 640x640) e dal modello (`.pt` o OpenVINO). Non dipende da *cosa* inquadra la telecamera. Una stanza con oggetti comuni (es. una bottiglia, una lattina, una sveglia) è perfetta.
- **Matcher Stereo (Post-processing)**: Se la telecamera inquadra un muro bianco o il soffitto, YOLO non troverà nulla e il matcher stereo non calcolerà le distanze. Per misurare i tempi di `post`, inquadra 2 o 3 oggetti riconoscibili (con `enable_debug:=true` verifica che vengano disegnati i box). Il matcher lavorerà a pieno regime.
- **Enhancement (C_full)**: Il nodo di enhancement sul Raspberry Pi non usa la rete neurale WaterNet, ma algoritmi classici di Computer Vision (Laplacian sharpening + CLAHE). Essendo deterministici, si comportano in modo identico su un'immagine statica, rendendo le misure di latenza estremamente stabili e veritiere.

---

## Lancio manuale (una config)

Wrapper unico per tutte le config: `benchmarks/run_benchmark.sh`.
Uso:

```bash
cd ~/nautilus-vision-pipeline
./benchmarks/run_benchmark.sh <config> <run_n>
#   config Fase A: A_baseline | B1_pt | B2_ov_fp32 | B3_ov_int8_640
#                | B4_ov_int8_416 | C_full
#   config Fase B: B1_pt_oc | B2_ov_fp32_oc | B3_ov_int8_640_oc
#                | B4_ov_int8_416_oc | C_full_oc
#   run_n:  1 | 2 | 3
```

Lo script gestisce automaticamente:

- **check temperatura** `< 55 °C` (unico controllo bloccante: se fallisce,
  `exit 1` e nessun CSV viene prodotto)
- **governor CPU** → `performance` (con `sudo tee` su `scaling_governor`)
- **stop** di `nautilus-bag.service`, `nautilus-vision.service`,
  `lock-cameras.service` (via `systemctl stop`)
- **`pkill`** di `camera_node`, `detection_node`, `enhancement_node`,
  `metrics_node` e di eventuali `ros2 bag record`
- **`ros2 daemon stop && ros2 daemon start`**
- **hardware unlock**: `sudo fuser -k -9 /dev/video0 /dev/video1`
- **lancio pipeline** con `include_stereo_camera:=true`,
  `input_type_override` esplicito e gli override del modello
- attesa 5 s + esecuzione di `deploy/lock_cameras.py`
- **grep sul launch log** per errori fatali noti
  (`is not a supported model format`, `stereo_callback failed`,
  `failed to acquire camera`): se trovati, emette un **WARNING** ma
  **prosegue** (nessun `exit 1`)
- **warmup 30 s**
- **`system_monitor.py --duration 300`** in background
- **`benchmark_pipeline.py --duration 120`** in foreground. Se `DET=true`
  (tutte le config tranne `A_baseline`), passa `--stages-topic
  /stereo_down/timings` e produce anche il `<...>_stages.csv`.
- **attesa della fine di `system_monitor.py`**, poi `kill -9` del
  processo di launch e `cleanup_camera_nodes` (pkill `-9`)
- **scrittura metadata CSV**
- **cooldown 10 s**

⚠️ **Cosa NON fa il wrapper**: non controlla nodi residui prima del
launch, non controlla publisher sui topic raw, non verifica il rate raw
contro `FrameDurationLimits`, non verifica che `/detection_node` sia
attivo dopo 5 s, non esegue `systemctl disable`. La sessione va quindi
preparata manualmente come da "Prerequisiti comuni" e i dati vanno
validati a posteriori sui CSV (rate anomali, `throttled`, `cpu_clock_mhz`).

I CSV finiscono in `benchmarks/results/csv/` con naming:
`<data>_<config>_run<N>_{latency,system,metadata}.csv`, più
`<data>_<config>_run<N>_launch.log` e, solo per le config con detection
attiva (`DET=true`), `<data>_<config>_run<N>_stages.csv`.

### Lancio manuale di A_baseline (solo camera)

```bash
ros2 launch nautilus_camera stereo_camera.launch.py \
  enable_metrics:=true
```

### Lancio manuale di B2_ov_fp32 (OpenVINO FP32 640)

```bash
# include_stereo_camera:=true è necessario perché i servizi sono stati
# fermati: le camere non sono attive e pipeline.launch.py di default
# assume che lo siano già.
ros2 launch nautilus_perception pipeline.launch.py \
  include_stereo_camera:=true \
  enable_enhancement:=false enable_detection:=true \
  input_type_override:=raw \
  enable_metrics:=true enable_debug:=false \
  model_filename_override:=yolov8n_640_fp32_openvino_model \
  half_res_override:=false imgsz_override:=640
```

### Lancio manuale di C_full (full + OpenVINO FP32 640)

```bash
ros2 launch nautilus_perception pipeline.launch.py \
  include_stereo_camera:=true \
  enable_enhancement:=true enable_detection:=true \
  input_type_override:=enhanced \
  enable_metrics:=true enable_debug:=false \
  model_filename_override:=yolov8n_640_fp32_openvino_model \
  half_res_override:=false imgsz_override:=640
```

---

## Verifica topic (dopo il lancio)

```bash
ros2 topic list | grep -E "stereo.*image|stereo_down"

# A_baseline:
#   /stereo/lx/camera/image_raw
#   /stereo/rx/camera/image_raw

# B*:
#   ... + /stereo_down/targets

# C_full:
#   ... + /stereo/lx/image_enhanced
#   ... + /stereo/rx/image_enhanced

ros2 topic hz /stereo_down/targets
# Atteso Fase A: ~0.7–1.0 Hz con .pt, ~TBD con OpenVINO FP32/INT8
#                 (da misurare, stima ottimistica precedente ~2.7/3.2 Hz)
```

---

## Valori attesi (dai test preliminari del 15/10/2026, no OC)

| Config | Stage | n | fps | Note |
| --- | --- | --- | --- | --- |
| A_baseline | raw | ~600 | 5.00 | baseline camera_ros (`FrameDurationLimits` verificato 2026-10-21: 5.003 Hz) |
| B1_pt | raw | ~600 | 5.00 | camera continua a 5 Hz |
| B1_pt | targets | ~TBD | ~0.7–1.0 | YOLOv8n CPU ARM, half_res=true, imgsz=640 (osservato 18/10/2026) |
| B2_ov_fp32 | raw | ~600 | 5.00 | |
| B2_ov_fp32 | targets | ~TBD | **~TBD** | da misurare (prediction ~4 Hz ottimistica, da confermare) |
| C_full | raw | ~600 | 5.00 | |
| C_full | enhanced | ~550 | ~4.5 | enhancement ~65 ms/frame |
| C_full | targets | ~TBD | ~0.7–1.0 | enhancement ~65-100 ms + detection ~1000 ms |
| B3_ov_int8_640 | targets | ~TBD | **~TBD** | da misurare (INT8) |
| B4_ov_int8_416 | targets | ~TBD | **~TBD** | da misurare (INT8 + imgsz ridotto) |

✅ **`FrameDurationLimits: [200000, 200000]` funziona** (verificato 2026-10-21:
`ros2 topic hz` → 5.003 Hz con `camera_ros` lanciato da solo).
⚠️ Se durante un run il rate raw è ~30 Hz, **non** è un bug del driver: i
frame vengono da un processo esterno (servizio systemd ripartito durante lo
stop, launch manuale dimenticato) che pubblica sullo stesso topic.

⚠️ Il wrapper `run_benchmark.sh` **non** implementa controlli automatici
su nodi residui, publisher sui topic, rate raw, `ros2 bag record` o errori
fatali nel launch log: fa solo un `grep` sui messaggi d'errore noti e
stampa un **WARNING** senza abortire. La validazione va quindi fatta a
posteriori sui CSV, scartando le run con rate anomali o throttling. Se
sospetti una run sporca, controlla `<run>_launch.log`.

Per la Fase B (OC), i valori attesi sono **superiori** se il throttling
non morde: tipicamente +10–20% sugli FPS di detection. Se il throttling
interviene entro i 120 s di benchmark, il guadagno si annulla.

⚠️ La detection **non tiene i 5 FPS** su Pi 5 a 720p. Il collo di bottiglia
è l'inferenza YOLO su CPU ARM. Il `metrics_node` continuerà a mostrare 5 Hz
sul topic `image_raw` (le camere non rallentano), ma `/stereo_down/targets`
avrà rate inferiore: frame droppati dal `message_filters` a valle.

Valori misurati il 18/10/2026 con `yolov8n.pt` (half_res=true, imgsz=640):
**~0.7–1.0 Hz** su `/stereo_down/targets` (YOLOv8n CPU ARM ~1000 ms/frame).
La stima precedente (~2.7 Hz) era ottimistica. I valori OpenVINO FP32/INT8
sono da misurare in Fase A e verranno sostituiti qui.

⚠️ Skew stereo misurato il 15/10/2026: **~6.6–7.9 ms** (storico documentato
in `DEBUG.md`: ~1.5 ms). Da annotare nel metadata; da indagare post-Fase 6.

---

## Esecuzione batch

### Fase A (senza overclock, ~2.5 h)

Assicurati che `config.txt` sia in modalità nominale (2400 MHz) e
riavvia. Poi:

```bash
for cfg in A_baseline B1_pt B2_ov_fp32 B3_ov_int8_640 B4_ov_int8_416 C_full; do
    for n in 1 2 3; do
        ./benchmarks/run_benchmark.sh "$cfg" "$n"
    done
done
```

### Fase B (con overclock, ~2 h)

Modifica `config.txt` per attivare l'OC (2800 MHz), riavvia, verifica
`vcgencmd measure_clock arm`, poi:

```bash
for cfg in B1_pt_oc B2_ov_fp32_oc B3_ov_int8_640_oc B4_ov_int8_416_oc C_full_oc; do
    for n in 1 2 3; do
        ./benchmarks/run_benchmark.sh "$cfg" "$n"
    done
done
```

Suggerito l'uso di `tmux` o `screen` (durata totale ~4.5 h):

```bash
tmux new -s bench
# incolla il loop sopra
# Ctrl+B poi D per detach
# tmux attach -t bench per rientrare
```

Prima di ogni run il wrapper:

- aspetta il cooldown del run precedente (10 s)
- verifica temperatura con `vcgencmd measure_temp` (deve essere < 55 °C)
- scrive un metadata CSV con commit hash, config, run, modello, flag
  `enable_*`, risoluzione (`imgsz`), temperature, throttled e clock CPU

---

## Metadata di riproducibilità

Il wrapper `run_benchmark.sh` genera automaticamente
`<data>_<config>_run<N>_metadata.csv` con:

- commit hash del repo (`git rev-parse HEAD`)
- config ID e numero di run
- `model_filename` usato (file `.pt` o directory OpenVINO)
- flag `half_res` e risoluzione `imgsz`
- tutti i flag `enable_*` usati
- temperatura SoC iniziale e finale
- `throttled_initial` / `throttled_final` (valore di `vcgencmd get_throttled`
  a inizio e fine run)
- `cpu_clock_initial_mhz` / `cpu_clock_final_mhz` (clock ARM a inizio e fine
  run, in MHz)

```csv
field,value
commit_hash,<output di git rev-parse HEAD>
config,B2_ov_fp32
run,1
enable_enhancement,false
enable_detection,true
enable_metrics,true
model_filename,yolov8n_640_fp32_openvino_model
half_res,false
imgsz,640
soc_temp_initial_c,47.5
soc_temp_final_c,49.9
throttled_initial,0x0
throttled_final,0x0
cpu_clock_initial_mhz,2400
cpu_clock_final_mhz,2400
notes,OV FP32
```

Il clock CPU effettivo è registrato colonna per colonna anche nel CSV
`_system.csv` (`cpu_clock_mhz`), perché è l'unico modo per accorgersi di
eventuale throttling durante la run.

---

## Analisi dei risultati

Dopo aver raccolto tutti i CSV:

```bash
python3 benchmarks/scripts/plot_results.py \
  --csv benchmarks/results/csv/ \
  --out benchmarks/results/plots/
```

Grafici generati (8 PNG):

1. `01_latency_mean_by_config.png` — latenza media per stage e config
2. `02_latency_p50_p95.png` — p50 e p95 per stage
3. `03_fps_by_config.png` — FPS effettivi per config
4. `04_soc_temp.png` — temperatura SoC nel tempo
5. `05_cpu.png` — CPU% nel tempo
6. `06_ram.png` — RAM usata nel tempo
7. `07_map_comparison.png` — mAP (se presenti CSV `map_*.csv`)
8. `08_detection_stages.png` — scomposizione pre/inferenza/post per config
   (richiede i CSV `_stages.csv` prodotti da `benchmark_pipeline.py`)

Con i suffissi `_oc`, ogni config OC compare separatamente nel grafico:
utile per confrontare visivamente la coppia `B*` vs `B*_oc` e vedere se
l'overclock sposta davvero l'ago.

### mAP sul validation set (opzionale, fuori dal loop)

Test di non-regressione dell'export OpenVINO su COCO128:

```bash
python3 benchmarks/scripts/evaluate_map.py \
  --weights ros2_ws/src/nautilus_perception/nautilus_perception/data/weights/yolov8n.pt \
  --data benchmarks/datasets/coco128.yaml \
  --imgsz 640 --tag yolov8n_pt \
  --out benchmarks/results/csv/map_yolov8n_pt.csv

python3 benchmarks/scripts/evaluate_map.py \
  --weights ros2_ws/src/nautilus_perception/nautilus_perception/data/weights/yolov8n_640_fp32_openvino_model \
  --data benchmarks/datasets/coco128.yaml \
  --imgsz 640 --tag yolov8n_ov_fp32 \
  --out benchmarks/results/csv/map_yolov8n_ov_fp32.csv

python3 benchmarks/scripts/evaluate_map.py \
  --weights ros2_ws/src/nautilus_perception/nautilus_perception/data/weights/yolov8n_640_int8_openvino_model \
  --data benchmarks/datasets/coco128.yaml \
  --imgsz 640 --tag yolov8n_ov_int8_640 \
  --out benchmarks/results/csv/map_yolov8n_ov_int8_640.csv
```

Atteso: `map50` di `.pt` e `.ov` **quasi identiche** (< 0.5 punti di scarto).
Se differiscono di più → regressione nell'export.

⚠️ `best.pt` (4 classi subacquee) **non** va valutato su COCO128:
le classi non corrispondono e la mAP risultante non ha significato.
Serve un validation set subacqueo con lo stesso schema di classi del training.

---

## Note operative

- **Non mischiare run**: se un run ha FPS anomali o throttling, va scartato
  e rifatto. Non mediare run buoni e cattivi.
- **Non toccare l'hardware tra run**: box aperto/chiuso, cavi, alimentazione
  devono essere costanti per tutte le config.
- **Conserva i CSV grezzi**: non sovrascrivere. Il wrapper usa sempre il
  prefisso con data odierna + config + run, quindi non ci sono collisioni
  se lanci più sessioni in giorni diversi.
- **Verifica il clock all'inizio di ogni run**: se sei in Fase A ma il Pi
  è ancora overclockato (o viceversa), tutti i dati sono invalidi. Un
  check rapido è `vcgencmd measure_clock arm` prima di lanciare.
- **Nessun salvataggio attivo** — `saving_node` è stato rimosso. La
  registrazione dati avviene via `nautilus-bag.service` (MCAP, controllato
  da `ENABLE_BAG` in `pipeline_config.env`), fermato dallo `stop` di
  `nautilus-vision.service` (`PartOf`) e dal wrapper con `systemctl stop
  nautilus-bag.service` + `pkill -f "ros2 bag record"`. Nessun I/O
  continuativo su MicroSD durante le misure.
- **Hardware unlock**: il wrapper esegue `sudo fuser -k -9 /dev/video0
  /dev/video1` per liberare i device video prima del launch. Se lanci la
  pipeline a mano (senza wrapper), verifica tu che nessun processo stia
  tenendo occupati `/dev/video0` e `/dev/video1`.
  