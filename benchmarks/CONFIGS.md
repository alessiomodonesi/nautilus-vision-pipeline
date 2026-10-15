# Fase 6 — Configurazioni di Benchmark

Questo documento descrive le configurazioni di test per il benchmark
prestazionale della pipeline Nautilus Vision (Fase 6 di `docs/TODO.md`).

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

## Le configurazioni di benchmark

### Configurazioni principali (Fase 6 ufficiale)

| # | ID | Config | Modello | half_res | imgsz |
| --- | --- | --- | --- | --- | --- |
| 1 | `A_baseline` | solo camera | — | — | — |
| 2 | `B_pt` | camera + detection | `yolov8n.pt` | True | 640 |
| 3 | `B_ov_fp32` | camera + detection | `yolov8n_openvino_640_fp32` | False | 640 |
| 4 | `C_pt` | camera + enh + detection | `yolov8n.pt` | True | 640 |
| 5 | `C_ov_int8_640` | camera + enh + detection | `yolov8n_openvino_640_int8` | False | 640 |

### Configurazioni di ottimizzazione (esperimento Fase 6.5)

| ID | Config | Modello | imgsz | Note |
| --- | --- | --- | --- | --- |
| `B_ov_int8_640` | camera + detection | `yolov8n_openvino_640_int8` | 640 | Quantizzazione INT8 |
| `B_ov_int8_416` | camera + detection | `yolov8n_openvino_416_int8` | 416 | INT8 + risoluzione ridotta |
| `B_best_fp32` | camera + detection | `best_openvino_416_fp32` | 416 | Modello 4-classi subacqueo (FP32) |
| `C_ov_int8_416` | camera + enh + detection | `yolov8n_openvino_416_int8` | 416 | Pipeline full + INT8 416 |

---

## Lancio manuale (una config)

Wrapper unico per tutte le config: `benchmarks/scripts/run_benchmark.sh`.
Uso:

```bash
cd ~/nautilus-vision-pipeline
./benchmarks/scripts/run_benchmark.sh <config> <run_n>
#   config: A_baseline | B_pt | B_ov_fp32 | B_ov_int8_640 | B_ov_int8_416
#         | B_best_fp32 | C_pt | C_ov_int8_640 | C_ov_int8_416
#   run_n:  1 | 2 | 3
```

Lo script gestisce automaticamente:

- stop dei servizi e cleanup processi
- check temperatura < 55 °C
- lancio pipeline con model_filename_override, half_res_override, imgsz_override corretti
- attesa 5s + `lock_cameras.py`
- warmup 30 s
- `system_monitor.py --duration 300` in background
- `benchmark_pipeline.py --duration 120` in foreground
- scrittura metadata CSV
- cooldown 30 s

I CSV finiscono in `benchmarks/results/csv/` con naming:
`<data>_<config>_run<N>_{latency,system,metadata}.csv`

### Lancio manuale di A_baseline (solo camera)

```bash
ros2 launch nautilus_camera stereo_camera.launch.py \\
  enable_saving:=false enable_metrics:=true
```

### Lancio manuale di B_pt / C_pt (PyTorch)

```bash
# B_pt
ros2 launch nautilus_perception pipeline.launch.py \
  enable_enhancement:=false enable_detection:=true \
  enable_saving:=false enable_metrics:=true enable_debug:=false \
  model_filename_override:=yolov8n.pt \
  half_res_override:=true imgsz_override:=640

# C_pt
ros2 launch nautilus_perception pipeline.launch.py \
  enable_enhancement:=true enable_detection:=true \
  enable_saving:=false enable_metrics:=true enable_debug:=false \
  model_filename_override:=yolov8n.pt \
  half_res_override:=true imgsz_override:=640
```

### Lancio manuale di B_ov_int8_416 / C_ov_int8_416 (OpenVINO INT8)

```bash
# B_ov_int8_416
ros2 launch nautilus_perception pipeline.launch.py \
  enable_enhancement:=false enable_detection:=true \
  enable_saving:=false enable_metrics:=true enable_debug:=false \
  model_filename_override:=yolov8n_openvino_416_int8 \
  half_res_override:=false imgsz_override:=416
```

---

## Verifica topic (dopo il lancio)

```bash
ros2 topic list | grep -E "stereo.*image|stereo_down"

# A:
#   /stereo/lx/camera/image_raw
#   /stereo/rx/camera/image_raw

# B_*:
#   ... + /stereo_down/targets

# C_*:
#   ... + /stereo/lx/image_enhanced
#   ... + /stereo/rx/image_enhanced

ros2 topic hz /stereo_down/targets
# Atteso: ~2.7 Hz con .pt, ~3.2 Hz con OpenVINO
```

---

## Valori attesi (dai test preliminari del 15/10/2026)

| Config | Stage | n | fps | Note |
| --- | --- | --- | --- | --- |
| A_baseline | raw | ~600 | 5.00 | baseline camera_ros |
| B_pt | raw | ~600 | 5.00 | camera continua a 5 Hz |
| B_pt | targets | ~330 | **~2.7** | inferenza PyTorch ~350 ms/frame |
| B_ov_fp32 | raw | ~600 | 5.00 | |
| B_ov_fp32 | targets | ~380 | **~3.2** | OpenVINO FP32 ~250 ms/frame |
| C_pt | raw | ~600 | 5.00 | |
| C_pt | enhanced | ~550 | ~4.5 | enhancement ~65 ms/frame |
| C_pt | targets | ~300 | **~2.5** | |
| C_ov_int8_640 | raw | ~600 | 5.00 | |
| C_ov_int8_640 | enhanced | ~550 | ~4.5 | |
| C_ov_int8_640 | targets | ~TBD | **~TBD** | da misurare (INT8) |

⚠️ La detection **non tiene i 5 FPS** su Pi 5 a 720p. Il collo di bottiglia è
l'inferenza YOLO su CPU ARM. Il `metrics_node` continuerà a mostrare 5 Hz
sul topic `image_raw` (le camere non rallentano), ma `/stereo_down/targets`
avrà rate inferiore: frame droppati dal `message_filters` a valle.

⚠️ Skew stereo misurato nel test di oggi: **~6.6–7.9 ms** (storico documentato
in `DEBUG.md`: ~1.5 ms). Da annotare nel metadata; da indagare post-Fase 6.

---

## Ripetizione dei test

Le 5 configurazioni principali (A_baseline, B_pt, B_ov_fp32, C_pt, C_ov_int8_640)
vanno eseguite **3 volte ciascuna** per un totale di 15 run.
Le configurazioni di ottimizzazione (Fase 6.5) si eseguono con 1 run esplorativo
e, se il guadagno è significativo, 3 run complete.
Il wrapper lo fa automaticamente:

```bash
# Batch principale (5 config × 3 run = 15 run, ~1h)
for cfg in A_baseline B_pt B_ov_fp32 C_pt C_ov_int8_640; do
    for n in 1 2 3; do
        ./benchmarks/scripts/run_benchmark.sh "$cfg" "$n"
    done
done
```

Suggerito l'uso di `tmux` o `screen` (durata totale ~3 h):

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
config,B_ov_fp32
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
notes,OpenVINO FP32 640
```

---

## Analisi dei risultati

Dopo aver raccolto tutti i CSV:

```bash
python3 benchmarks/scripts/plot_results.py \\
  --csv benchmarks/results/csv/ \\
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

### mAP sul validation set (opzionale, fuori dal loop dei 15 run)

Test di non-regressione dell'export OpenVINO su COCO128:

```bash
python3 benchmarks/scripts/evaluate_map.py \\
  --weights ros2_ws/src/nautilus_perception/nautilus_perception/data/weights/yolov8n.pt \\
  --data benchmarks/datasets/coco128.yaml \\
  --imgsz 640 --tag yolov8n_pt \\
  --out benchmarks/results/csv/map_yolov8n_pt.csv

python3 benchmarks/scripts/evaluate_map.py \
  --weights ros2_ws/src/nautilus_perception/nautilus_perception/data/weights/yolov8n_openvino_640_fp32 \
  --data benchmarks/datasets/coco128.yaml \
  --imgsz 640 --tag yolov8n_ov_fp32 \
  --out benchmarks/results/csv/map_yolov8n_ov_fp32.csv

# INT8 640
python3 benchmarks/scripts/evaluate_map.py \
  --weights ros2_ws/src/nautilus_perception/nautilus_perception/data/weights/yolov8n_openvino_640_int8 \
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
  devono essere costanti per tutte le 5 config.
- **Conserva i CSV grezzi**: non sovrascrivere. Il wrapper usa sempre il
  prefisso con data odierna + config + run, quindi non ci sono collisioni
  se lanci più sessioni in giorni diversi.
  