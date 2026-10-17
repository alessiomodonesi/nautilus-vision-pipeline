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
sudo systemctl stop nautilus-vision.service
sudo systemctl stop lock-cameras.service
source /opt/ros/jazzy/setup.bash
source ~/nautilus-vision-pipeline/ros2_ws/install/setup.bash
ls ~/nautilus-vision-pipeline/ros2_ws/src/nautilus_perception/nautilus_perception/data/weights/
```

Sessione pulita:

```bash
ps aux | grep -E "camera_node|metrics_node|detection_node|enhancement_node" | grep -v grep
# Non deve stampare nulla
ros2 node list
# Non deve stampare nulla (o solo /rosout)
```

Durante i benchmark:

- **`enable_saving` sempre a `false`** — l'I/O su MicroSD introduce jitter
- **`enable_metrics` sempre a `true`** — controprova FPS dal nodo metriche
- **`enable_debug` sempre a `false`** — nessuna finestra OpenCV

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
| 3 | `B2_ov_fp32` | camera + detection | `yolov8n_openvino_640_fp32` | False | 640 |
| 4 | `B3_ov_int8_640` | camera + detection | `yolov8n_openvino_640_int8` | False | 640 |
| 5 | `B4_ov_int8_416` | camera + detection | `yolov8n_openvino_416_int8` | False | 416 |
| 6 | `C_full` | camera + enh + detection | `yolov8n_openvino_640_fp32` | False | 640 |

### Fase B — con overclock (senza baseline)

5 configurazioni, con la CPU **overclockata** (2800 MHz). `A_baseline` è
esclusa: il collo di bottiglia dell'acquisizione non è la CPU, e
l'overclock non porterebbe beneficio spendendo budget termico.

Ogni config ha la stessa parametrizzazione della Fase A ma con suffisso
`_oc` per non collidere nei CSV.

| # | ID | Config | Modello | half_res | imgsz |
| --- | --- | --- | --- | --- | --- |
| 1 | `B1_pt_oc` | camera + detection | `yolov8n.pt` | True | 640 |
| 2 | `B2_ov_fp32_oc` | camera + detection | `yolov8n_openvino_640_fp32` | False | 640 |
| 3 | `B3_ov_int8_640_oc` | camera + detection | `yolov8n_openvino_640_int8` | False | 640 |
| 4 | `B4_ov_int8_416_oc` | camera + detection | `yolov8n_openvino_416_int8` | False | 416 |
| 5 | `C_full_oc` | camera + enh + detection | `yolov8n_openvino_640_fp32` | False | 640 |

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

- stop dei servizi e cleanup processi
- check temperatura < 55 °C
- lancio pipeline con `include_stereo_camera:=true` e gli override corretti
- attesa 5 s + `lock_cameras.py`
- warmup 30 s
- `system_monitor.py --duration 300` in background
- `benchmark_pipeline.py --duration 120` in foreground
- scrittura metadata CSV
- cooldown 30 s

I CSV finiscono in `benchmarks/results/csv/` con naming:
`<data>_<config>_run<N>_{latency,system,metadata}.csv`

### Lancio manuale di A_baseline (solo camera)

```bash
ros2 launch nautilus_camera stereo_camera.launch.py \
  enable_saving:=false enable_metrics:=true
```

### Lancio manuale di B2_ov_fp32 (OpenVINO FP32 640)

```bash
# include_stereo_camera:=true è necessario perché i servizi sono stati
# fermati: le camere non sono attive e pipeline.launch.py di default
# assume che lo siano già.
ros2 launch nautilus_perception pipeline.launch.py \
  include_stereo_camera:=true \
  enable_enhancement:=false enable_detection:=true \
  enable_saving:=false enable_metrics:=true enable_debug:=false \
  model_filename_override:=yolov8n_640_fp32_openvino_model \
  half_res_override:=false imgsz_override:=640
```

### Lancio manuale di C_full (full + OpenVINO FP32 640)

```bash
ros2 launch nautilus_perception pipeline.launch.py \
  include_stereo_camera:=true \
  enable_enhancement:=true enable_detection:=true \
  enable_saving:=false enable_metrics:=true enable_debug:=false \
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
# Atteso: ~2.7 Hz con .pt, ~3.2 Hz con OpenVINO FP32 (senza OC)
```

---

## Valori attesi (dai test preliminari del 15/10/2026, no OC)

| Config | Stage | n | fps | Note |
| --- | --- | --- | --- | --- |
| A_baseline | raw | ~600 | 5.00 | baseline camera_ros |
| B1_pt | raw | ~600 | 5.00 | camera continua a 5 Hz |
| B1_pt | targets | ~330 | **~2.7** | inferenza PyTorch ~350 ms/frame |
| B2_ov_fp32 | raw | ~600 | 5.00 | |
| B2_ov_fp32 | targets | ~380 | **~3.2** | OpenVINO FP32 ~250 ms/frame |
| C_full | raw | ~600 | 5.00 | |
| C_full | enhanced | ~550 | ~4.5 | enhancement ~65 ms/frame |
| C_full | targets | ~300 | **~2.5** | |
| B3_ov_int8_640 | targets | ~TBD | **~TBD** | da misurare (INT8) |
| B4_ov_int8_416 | targets | ~TBD | **~TBD** | da misurare (INT8 + imgsz ridotto) |

Per la Fase B (OC), i valori attesi sono **superiori** se il throttling
non morde: tipicamente +10–20% sugli FPS di detection. Se il throttling
interviene entro i 120 s di benchmark, il guadagno si annulla.

⚠️ La detection **non tiene i 5 FPS** su Pi 5 a 720p. Il collo di bottiglia
è l'inferenza YOLO su CPU ARM. Il `metrics_node` continuerà a mostrare 5 Hz
sul topic `image_raw` (le camere non rallentano), ma `/stereo_down/targets`
avrà rate inferiore: frame droppati dal `message_filters` a valle.

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

- aspetta il cooldown del run precedente (30 s)
- verifica temperatura con `vcgencmd measure_temp` (deve essere < 55 °C)
- scrive un metadata CSV con commit hash, config, run, modello, flag
  `enable_*`, risoluzione (`imgsz`) e temperature

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

```csv
field,value
commit_hash,<output di git rev-parse HEAD>
config,B2_ov_fp32
run,1
enable_enhancement,false
enable_detection,true
enable_saving,false
enable_metrics,true
model_filename,yolov8n_openvino_640_fp32
half_res,false
imgsz,640
soc_temp_initial_c,47.5
soc_temp_final_c,49.9
notes,OpenVINO FP32 640 (no OC)
```

Il clock CPU effettivo è registrato colonna per colonna nel CSV
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

Grafici generati:

1. `01_latency_mean_by_config.png` — latenza media per stage e config
2. `02_latency_p50_p95.png` — p50 e p95 per stage
3. `03_fps_by_config.png` — FPS effettivi per config
4. `04_soc_temp.png` — temperatura SoC nel tempo
5. `05_cpu.png` — CPU% nel tempo
6. `06_ram.png` — RAM usata nel tempo
7. `07_map_comparison.png` — mAP (se presenti CSV `map_*.csv`)

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
