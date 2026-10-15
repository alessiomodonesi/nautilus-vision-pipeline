# Fase 6 — Configurazioni di Benchmark

Questo documento descrive le tre configurazioni di test per il benchmark
prestazionale della pipeline Nautilus Vision (Fase 6 di `docs/TODO.md`).

Ogni configurazione va eseguita **almeno 3 volte** sullo stesso hardware,
con la stessa scena e la stessa illuminazione, per valutare la varianza.

---

## Prerequisiti comuni

Prima di ogni sessione di benchmark:

```bash
# 1. Ferma i servizi di produzione
sudo systemctl stop nautilus-vision.service
sudo systemctl stop lock-cameras.service

# 2. Source ambiente ROS 2
source /opt/ros/jazzy/setup.bash
source ~/nautilus-vision-pipeline/ros2_ws/install/setup.bash

# 3. Verifica modelli e pesi
ls ~/nautilus-vision-pipeline/ros2_ws/src/nautilus_perception/nautilus_perception/data/weights/
```

Verifica che la sessione sia pulita:

```bash
ps aux | grep -E "camera_node|metrics_node|detection_node|enhancement_node" | grep -v grep
# Non deve stampare nulla

ros2 node list
# Non deve stampare nulla (o solo /rosout)
```

Durante i benchmark di latenza:

- **`enable_saving` sempre a `false`**: l'I/O su MicroSD introduce jitter
- **`enable_metrics` sempre a `true`**: serve come controprova dell'FPS
- Latenza e FPS vanno misurati contemporaneamente al `system_monitor`

---

## Configurazione A — Solo acquisizione (baseline)

**Obiettivo:** misurare la latenza end-to-end del driver `camera_ros` senza
carico di enhancement o detection. Serve come baseline per capire quanto
aggiungono le altre configurazioni.

### Lancio pipeline (Terminale 1)

```bash
ros2 launch nautilus_camera stereo_camera.launch.py \
  enable_saving:=false \
  enable_metrics:=true
```

### Lock fotometrico (Terminale 2, dopo 5s)

```bash
python3 ~/nautilus-vision-pipeline/deploy/lock_cameras.py
```

### Monitor di sistema (Terminale 3)

```bash
cd ~/nautilus-vision-pipeline
python3 benchmarks/scripts/system_monitor.py \
  --duration 300 \
  --out benchmarks/results/csv/$(date +%Y-%m-%d)_A_baseline_run1_system.csv
```

### Benchmark latenze (Terminale 4)

```bash
cd ~/nautilus-vision-pipeline
python3 benchmarks/scripts/benchmark_pipeline.py \
  --duration 120 \
  --out benchmarks/results/csv/$(date +%Y-%m-%d)_A_baseline_run1_latency.csv \
  --raw-topic /stereo/lx/camera/image_raw \
  --enhanced-topic "" \
  --targets-topic ""
```

### Valori attesi

| Stage | n | mean | p50 | p95 | fps |
| --- | --- | --- | --- | --- | --- |
| raw | ~600 | ~45 ms | ~45 ms | ~46 ms | 5.00 |

Se FPS < 4.5 → problema di subscriber, controllare che `rclpy.spin` sia usato
e non `spin_once` in loop.

---

## Configurazione B — Acquisizione + Detection

**Obiettivo:** misurare il costo della detection IA + stereovisione sul
frame grezzo, senza enhancement. Il topic `targets` misura la latenza
end-to-end dalla cattura del frame alla pubblicazione dei target.

### Lancio pipeline (Terminale 1)

```bash
ros2 launch nautilus_perception pipeline.launch.py \
  enable_enhancement:=false \
  enable_detection:=true \
  enable_saving:=false \
  enable_metrics:=true \
  enable_debug:=false
```

### Verifica topic (Terminale 2)

```bash
ros2 topic list | grep -E "stereo_down|stereo.*image"
# Atteso:
#   /stereo/lx/camera/image_raw
#   /stereo/rx/camera/image_raw
#   /stereo_down/targets

ros2 topic hz /stereo_down/targets
# Atteso: ~5 Hz se detection gira a pieno regime
```

### Lock fotometrico (Terminale 3)

```bash
python3 ~/nautilus-vision-pipeline/deploy/lock_cameras.py
```

### Monitor di sistema (Terminale 4)

```bash
cd ~/nautilus-vision-pipeline
python3 benchmarks/scripts/system_monitor.py \
  --duration 300 \
  --out benchmarks/results/csv/$(date +%Y-%m-%d)_B_detection_run1_system.csv
```

### Benchmark latenze (Terminale 5)

```bash
cd ~/nautilus-vision-pipeline
python3 benchmarks/scripts/benchmark_pipeline.py \
  --duration 120 \
  --out benchmarks/results/csv/$(date +%Y-%m-%d)_B_detection_run1_latency.csv \
  --raw-topic /stereo/lx/camera/image_raw \
  --enhanced-topic "" \
  --targets-topic /stereo_down/targets
```

### Valori attesi

| Stage | n | mean | p50 | p95 | fps |
| --- | --- | --- | --- | --- | --- |
| raw | ~600 | ~45 ms | ~45 ms | ~46 ms | 5.00 |
| targets | ~600 | > raw | > raw | > raw | 5.00 |

Il valore di `targets.mean - raw.mean` è la **latenza aggiunta dal detection
node** (inferenza + stereovisione + post-processing + DDS).

⚠️ Verifica che `detection_node.py` preservi `header.stamp` dell'immagine di
input nel messaggio `Detection2DArray` in uscita. Senza quello, la latenza
misurata su `targets` non è end-to-end.

```bash
grep -n "header.stamp\|stamp =\|get_clock().now" \
  ~/nautilus-vision-pipeline/ros2_ws/src/nautilus_perception/nautilus_perception/detection_node.py
```

---

## Configurazione C — Pipeline completa

**Obiettivo:** misurare il costo dell'intera pipeline (acquisizione +
enhancement + detection). È la configurazione di produzione attuale.

### Lancio pipeline (Terminale 1)

```bash
ros2 launch nautilus_perception pipeline.launch.py \
  enable_enhancement:=true \
  enable_detection:=true \
  enable_saving:=false \
  enable_metrics:=true \
  enable_debug:=false
```

### Verifica topic (Terminale 2)

```bash
ros2 topic list | grep -E "stereo.*image|stereo_down"
# Atteso:
#   /stereo/lx/camera/image_raw
#   /stereo/rx/camera/image_raw
#   /stereo/lx/image_enhanced
#   /stereo/rx/image_enhanced
#   /stereo_down/targets

ros2 topic hz /stereo/lx/image_enhanced
ros2 topic hz /stereo_down/targets
```

### Lock fotometrico (Terminale 3)

```bash
python3 ~/nautilus-vision-pipeline/deploy/lock_cameras.py
```

### Monitor di sistema (Terminale 4)

```bash
cd ~/nautilus-vision-pipeline
python3 benchmarks/scripts/system_monitor.py \
  --duration 300 \
  --out benchmarks/results/csv/$(date +%Y-%m-%d)_C_full_run1_system.csv
```

### Benchmark latenze (Terminale 5)

```bash
cd ~/nautilus-vision-pipeline
python3 benchmarks/scripts/benchmark_pipeline.py \
  --duration 120 \
  --out benchmarks/results/csv/$(date +%Y-%m-%d)_C_full_run1_latency.csv \
  --raw-topic /stereo/lx/camera/image_raw \
  --enhanced-topic /stereo/lx/image_enhanced \
  --targets-topic /stereo_down/targets
```

### Valori attesi

| Stage | n | mean | p50 | p95 | fps |
| --- | --- | --- | --- | --- | --- |
| raw | ~600 | ~45 ms | ~45 ms | ~46 ms | 5.00 |
| enhanced | ~600 | > raw | > raw | > raw | 5.00 |
| targets | ~600 | > enhanced | > enhanced | > enhanced | 5.00 |

Latenze incrementali:

- `enhanced.mean - raw.mean` → costo dell'enhancement node
- `targets.mean - enhanced.mean` → costo del detection (con input enhanced)
- `targets.mean - raw.mean` → costo end-to-end totale

⚠️ Come per B, verifica che sia `enhancement_node.py` che `detection_node.py`
preservino `header.stamp` dell'input.

```bash
grep -n "header.stamp\|stamp =\|get_clock().now" \
  ~/nautilus-vision-pipeline/ros2_ws/src/nautilus_perception/nautilus_perception/enhancement_node.py \
  ~/nautilus-vision-pipeline/ros2_ws/src/nautilus_perception/nautilus_perception/detection_node.py
```

---

## Ripetizione dei test

Per ogni configurazione (A, B, C) eseguire **3 run** in sequenza, cambiando
solo il suffisso `run1` → `run2` → `run3` nei nomi dei file:

```bash
... _A_baseline_run1_latency.csv
... _A_baseline_run2_latency.csv
... _A_baseline_run3_latency.csv
```

Stessa cosa per `_system.csv`.

Prima di ogni run:

- Aspetta 30s da fine run precedente (raffreddamento SoC)
- Verifica temperatura con `vcgencmd measure_temp` (deve essere < 55°C)
- Annota la temperatura iniziale in un file `metadata.csv`

---

## Metadata di riproducibilità

Per ogni sessione di benchmark crea un file
`benchmarks/results/csv/<data>_metadata.csv` con:

```csv
field,value
commit_hash,<output di git rev-parse HEAD>
config,A
run,1
model,N/A
precision,N/A
num_threads,N/A
soc_temp_initial_c,47.5
soc_temp_final_c,49.9
notes,configurazione baseline senza detection né enhancement
```

Per Config B e C aggiungi:

```csv
model,yolov8n.pt
precision,FP32
num_threads,2
imgsz,640
half_res,true
```

(Il valore di `num_threads` è in `detection_params.yaml`.)

---

## Analisi dei risultati

Dopo aver raccolto tutti i CSV, eseguire:

```bash
python3 benchmarks/scripts/plot_results.py \
  --csv benchmarks/results/csv/ \
  --out benchmarks/results/plots/
```

Grafici attesi:

1. **Latenza media per configurazione** (bar chart, A/B/C)
2. **Box plot p50/p95 per stage** (raw/enhanced/targets)
3. **FPS per configurazione** (bar chart)
4. **Temperatura SoC nel tempo** (line chart, sovrapposte A/B/C)
5. **CPU% nel tempo** (line chart)
6. **RAM usata nel tempo** (line chart)

Per la mAP (accuratezza detection):

```bash
python3 benchmarks/scripts/evaluate_map.py \
  --weights ros2_ws/src/nautilus_perception/nautilus_perception/data/weights/best_openvino_model \
  --data benchmarks/datasets/raw/<dataset>/data.yaml \
  --out benchmarks/results/csv/map_best_openvino.csv
```

---

## Note operative

- **Non mischiare run**: se un run va male (es. FPS anomali, throttling),
  va scartato e rifatto. Non mediare run buoni e cattivi.
- **Non toccare l'hardware tra run**: box aperto/chiuso, posizione
  cavi, alimentazione devono essere costanti per A/B/C.
- **Salva i log**: `journalctl -u nautilus-vision.service -n 500 > <run>_journal.log`
  per ogni run, utile in caso di anomalie.
- **Conserva i CSV grezzi**: non sovrascrivere, usa timestamp diversi nei nomi.
