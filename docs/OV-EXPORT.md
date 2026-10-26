# OpenVINO Export — Modelli YOLOv8n e best per Nautilus Vision

Questo documento descrive la procedura di export dei modelli YOLOv8 in
formato OpenVINO (FP32 e INT8) per la pipeline Nautilus Vision sul
Raspberry Pi 5, e come testare la risoluzione di inferenza (`imgsz`).

---

## 1. Premessa: quando ha senso l'INT8

La quantizzazione INT8 con NNCF non comprime i pesi: **ricalibra i range
di attivazione** layer per layer, osservando min/max su un set di immagini
di calibrazione. La qualità dell'INT8 dipende criticamente dalla
**rappresentatività del dataset di calibrazione** rispetto al dominio di
deployment.

| Modello | Dominio | Dataset di calibrazione corretto |
| --- | --- | --- |
| `yolov8n.pt` | COCO (80 classi generiche) | COCO128 (o COCO completo) |
| `best.pt` | Subacqueo (4 classi: Glass, Metal, Plastic, Trash) | Frame subacquei reali |

**Conseguenza operativa:**

- `yolov8n.pt` → INT8 con calibrazione COCO128 è corretto.
- `best.pt` → INT8 con calibrazione COCO128 è **concettualmente sbagliato**.
  I range di attivazione osservati su COCO (cani, auto, interni) non
  rispecchiano il dominio subacqueo. Il modello risultante può degradare
  sensibilmente su immagini reali.

**Regola:** INT8 di `best.pt` si esporta **solo** con calibrazione su
frame subacquei. Se non ne hai a sufficienza (≥ 100), esporta solo FP32.

L'INT8 non richiede etichette, solo immagini. Frame subacquei non
etichettati sono perfettamente validi per la calibrazione.

---

## 2. Prerequisiti

### 2.1 Virtual environment dedicato all'export

Su Ubuntu 24.04 il Python di sistema è protetto (PEP 668). Non installare
`nncf` con `--break-system-packages`: ROS 2 Jazzy usa il Python di sistema
e un upgrade di `torch`/`openvino` può rompere `cv_bridge` o `rclpy`.

```bash
cd ~/nautilus-vision-pipeline
python3 -m venv .venv_ov
source .venv_ov/bin/activate
pip install --upgrade pip
pip install "ultralytics>=8.4" "openvino>=2026.0.0" "nncf>=2.14.0" "packaging>=23.2"
```

Attivare il venv **solo** per gli export. Per i benchmark e la pipeline
ROS 2 usare il Python di sistema.

### 2.2 Dataset di calibrazione

**Per `yolov8n.pt`:** COCO128, già presente in `benchmarks/datasets/`.
Verificare che `coco128.yaml` contenga un path assoluto:

```yaml
path: /home/nautilus/nautilus-vision-pipeline/benchmarks/datasets/coco128
train: images/train2017
val: images/train2017
```

**Per `best.pt`:** creare un dataset di frame subacquei (non etichettati).

```bash
CALIB_DIR=benchmarks/datasets/subsea_calib
mkdir -p $CALIB_DIR/images/train $CALIB_DIR/labels/train

# Opzione A: da immagini esistenti
cp benchmarks/datasets/processed/clean_output/**/*.jpg $CALIB_DIR/images/train/

# Opzione B: estrarre frame da video
ffmpeg -i benchmarks/datasets/videos/test_video_1.mp4 \
    -vf fps=2 $CALIB_DIR/images/train/frame_%04d.jpg

# Ultralytics richiede che esistano label (anche vuote)
for f in $CALIB_DIR/images/train/*.jpg; do
    touch "$CALIB_DIR/labels/train/$(basename "${f%.jpg}").txt"
done

ls $CALIB_DIR/images/train/ | wc -l   # target: ≥ 100
```

Creare `benchmarks/datasets/subsea_calib.yaml`:

```yaml
path: /home/nautilus/nautilus-vision-pipeline/benchmarks/datasets/subsea_calib
train: images/train
val: images/train
nc: 4
names: ['Glass', 'Metal', 'Plastic', 'Trash']
```

---

## 3. Export dei 5 modelli

Tutti i comandi vanno eseguiti con il venv attivo, dalla root del progetto.

```bash
cd ~/nautilus-vision-pipeline
source .venv_ov/bin/activate

WEIGHTS=ros2_ws/src/nautilus_perception/nautilus_perception/data/weights
CALIB_COCO=benchmarks/datasets/coco128.yaml
CALIB_SUBSEA=benchmarks/datasets/subsea_calib.yaml
```

> **Nota sui nomi di output (Ultralytics 8.4.177):**
>
> - FP32 → `<stem>_openvino_model/`
> - INT8 → `<stem>_int8_openvino_model/`

### 3.1 yolov8n FP32 @ 640

```bash
yolo export model=$WEIGHTS/yolov8n.pt format=openvino imgsz=640
mv $WEIGHTS/yolov8n_openvino_model $WEIGHTS/yolov8n_640_fp32_openvino_model
```

### 3.2 yolov8n INT8 @ 640

```bash
yolo export model=$WEIGHTS/yolov8n.pt format=openvino int8=True imgsz=640 data=$CALIB_COCO
mv $WEIGHTS/yolov8n_int8_openvino_model $WEIGHTS/yolov8n_640_int8_openvino_model
```

### 3.3 yolov8n INT8 @ 416

```bash
yolo export model=$WEIGHTS/yolov8n.pt format=openvino int8=True imgsz=416 data=$CALIB_COCO
mv $WEIGHTS/yolov8n_int8_openvino_model $WEIGHTS/yolov8n_416_int8_openvino_model
```

### 3.4 best FP32 @ 416

```bash
yolo export model=$WEIGHTS/best.pt format=openvino imgsz=416
mv $WEIGHTS/best_openvino_model $WEIGHTS/best_416_fp32_openvino_model
```

### 3.5 best INT8 @ 416

**Solo se `benchmarks/datasets/subsea_calib/` contiene ≥ 100 frame
subacquei.** Se il dataset non esiste o è troppo piccolo, saltare questo
passo e usare solo FP32.

```bash
yolo export model=$WEIGHTS/best.pt format=openvino int8=True imgsz=416 data=$CALIB_SUBSEA
mv $WEIGHTS/best_int8_openvino_model $WEIGHTS/best_416_int8_openvino_model
```

**Fallback (sconsigliato):** se mancano frame subacquei e si vuole
comunque un INT8 di `best.pt` come esperimento di benchmark, usare
`data=$CALIB_COCO` e **documentare esplicitamente** nei metadata CSV
che la calibrazione è domain-mismatched. Il modello risultante **non
va usato in produzione**.

### 3.6 Riepilogo output atteso

```bash
ls -d $WEIGHTS/*openvino* 2>/dev/null
```

| Cartella | Modello | imgsz | Quantizzazione | Dim. ~ |
| --- | --- | --- | --- | --- |
| `yolov8n_640_fp32_openvino_model/` | yolov8n | 640 | FP32 | 12 MB |
| `yolov8n_640_int8_openvino_model/` | yolov8n | 640 | INT8 | 3.6 MB |
| `yolov8n_416_int8_openvino_model/` | yolov8n | 416 | INT8 | 3.6 MB |
| `best_416_fp32_openvino_model/` | best | 416 | FP32 | 12 MB |
| `best_416_int8_openvino_model/` | best | 416 | INT8 | 3.6 MB |

Disattivare il venv:

```bash
deactivate
```

---

## 4. Verifica delle shape

```bash
python3 -c "
import openvino as ov
from pathlib import Path

WEIGHTS = Path('ros2_ws/src/nautilus_perception/nautilus_perception/data/weights')
core = ov.Core()

for d in sorted(WEIGHTS.glob('*_openvino_*')):
    xmls = list(d.glob('*.xml'))
    if not xmls:
        continue
    m = core.read_model(str(xmls[0]))
    inp = m.input(0)
    print(f'{d.name:35s} input={list(inp.shape)} type={inp.element_type}')
"
```

Output atteso:

```text
best_416_fp32_openvino_model        input=[1, 3, 416, 416] type=<Type.f32: 'f32'>
yolov8n_416_int8_openvino_model     input=[1, 3, 416, 416] type=<Type.f32: 'f32'>
yolov8n_640_fp32_openvino_model     input=[1, 3, 640, 640] type=<Type.f32: 'f32'>
yolov8n_640_int8_openvino_model     input=[1, 3, 640, 640] type=<Type.f32: 'f32'>
```

L'input resta `f32` anche per i modelli INT8: OpenVINO quantizza i pesi
internamente, ma l'interfaccia resta float per compatibilità con il
pre-processing. Comportamento atteso.

---

## 5. Test di `imgsz` nella pipeline

### 5.1 Perché è necessario

Ultralytics fa un letterbox interno verso `imgsz` (default 640). Se il
modello è esportato a 416 ma `predict()` riceve `imgsz=640`, OpenVINO
applica un secondo resize che spreca calcolo e può degradare l'accuratezza.
`imgsz` in `predict()` **deve combaciare** con la risoluzione di export.

Inoltre, passare `imgsz=416` a un modello esportato a 416 riduce i FLOPs
del forward pass di ~58% rispetto a 640 (`(416/640)² ≈ 0.42`), a fronte
di una perdita di accuratezza tipicamente contenuta su oggetti grandi.

### 5.2 Implementazione di `imgsz` nel codice della pipeline

Il parametro `imgsz` è pienamente integrato sia in `core_detection.py` sia in `detection_node.py`:

- `YoloDetector` accetta `imgsz` e lo passa direttamente al metodo `predict(..., imgsz=self.imgsz)` di Ultralytics.
- `detection_node.py` dichiara il parametro `imgsz` (letto da `detection_params.yaml` o sovrascrivibile da launch con `imgsz_override:=...`) e lo inoltra al detector.
- I modelli OpenVINO a 416px (come `yolov8n_416_int8_openvino_model` o `best_416_fp32_openvino_model`) vengono quindi eseguiti alla loro risoluzione nativa senza resize spuri.

### 5.4 YAML di configurazione

Creare un YAML per ogni combinazione modello + imgsz. Esempi:

**`detection_params_ov_int8_416.yaml`**

```yaml
detection_node:
  ros__parameters:
    model_filename: 'yolov8n_416_int8_openvino_model'
    conf_threshold: 0.4
    input_type: 'raw'
    enable_debug: False
    half_res: False
    imgsz: 416
    num_threads: 4
    sync_slop_sec: 0.05
```

**`detection_params_ov_int8_640.yaml`**

```yaml
detection_node:
  ros__parameters:
    model_filename: 'yolov8n_640_int8_openvino_model'
    conf_threshold: 0.4
    input_type: 'raw'
    enable_debug: False
    half_res: False
    imgsz: 640
    num_threads: 4
    sync_slop_sec: 0.05
```

**`detection_params_best_416.yaml`**

```yaml
detection_node:
  ros__parameters:
    model_filename: 'best_416_fp32_openvino_model'
    conf_threshold: 0.4
    input_type: 'raw'
    enable_debug: False
    half_res: False
    imgsz: 416
    num_threads: 4
    sync_slop_sec: 0.05
```

### 5.5 Test rapido standalone (senza ROS)

Prima di lanciare la pipeline completa, misurare il boost con un test
diretto su OpenVINO:

```bash
python3 -c "
import time, numpy as np, openvino as ov
from pathlib import Path

W = Path('ros2_ws/src/nautilus_perception/nautilus_perception/data/weights')
core = ov.Core()

for name in ['yolov8n_640_fp32_openvino_model', 'yolov8n_640_int8_openvino_model',
             'yolov8n_416_int8_openvino_model', 'best_416_fp32_openvino_model']:
    d = W / name
    if not d.exists():
        print(f'{name}: MISSING'); continue
    xml = next(d.glob('*.xml'))
    m = core.compile_model(str(xml), 'CPU')
    inp = m.input(0)
    shape = list(inp.shape)
    dummy = np.zeros(shape, dtype=np.float32)

    # warmup
    for _ in range(3):
        m([dummy])

    # misura
    n = 30
    t0 = time.perf_counter()
    for _ in range(n):
        m([dummy])
    dt = (time.perf_counter() - t0) / n * 1000
    print(f'{name:35s} imgsz={shape[2]:4d}  {dt:7.1f} ms  ({1000/dt:5.1f} FPS)')
"
```

Questo dà una stima del **solo forward pass OpenVINO**, senza remap,
senza enhancement, senza ROS. È il tetto massimo raggiungibile nella
pipeline reale.

### 5.6 Test end-to-end con il wrapper di benchmark

L'esecuzione dei benchmark completi sulla pipeline è gestita da `benchmarks/run_benchmark.sh`:

```bash
# Esempio esecuzione benchmark su modello esportato
./benchmarks/run_benchmark.sh B2_ov_fp32 1
./benchmarks/run_benchmark.sh B3_ov_int8_640 1
./benchmarks/run_benchmark.sh B4_ov_int8_416 1
```

> [!WARNING]
> **Esito Empirico dei Benchmark di Fase 6**:
> Le misure sul Raspberry Pi 5 (Cortex-A76) hanno evidenziato che i modelli quantizzati INT8 (`B3` a 640px e `B4` a 416px) impiegano rispettivamente **8.32 s** e **3.55 s** di inferenza per frame a causa del fallback software del runtime CPU ARM di OpenVINO. Al contrario, **`yolov8n_640_fp32_openvino_model`** raggiunge **~2.29 FPS** con soli **347 ms** di inferenza pura e mAP identica a PyTorch (0.612@0.5). Il modello **FP32** è pertanto la scelta di produzione raccomandata. Vedi [`benchmarks/benchmark_results/RESULTS.md`](../benchmarks/benchmark_results/RESULTS.md).

---

## 6. Warning comuni e come interpretarli

| Warning | Significato | Azione |
| --- | --- | --- |
| `'int8' is deprecated, use 'quantize'` | Cosmetico (Ultralytics ≥ 8.4) | Ignorare |
| `>300 images recommended, found 128` | Calibrazione su set ridotto | Accettabile per benchmark |
| `Slow image access detected` | Lettura lenta da disco | Ignorare |
| `34 ignored nodes were found` | NNCF salta i layer di post-processing (Reshape, Concat, Softmax) | Comportamento corretto |
| `val: New cache created` | Ultralytics ha creato il cache delle label | Ignorare |

---

## 7. Limitazioni note

- La calibrazione INT8 di `yolov8n.pt` su COCO128 è un proxy: per la
  produzione andrebbe usato un set rappresentativo del dominio operativo.
- La calibrazione INT8 di `best.pt` su COCO128 è **domain-mismatched**:
  il modello risultante va trattato come esperimento di benchmark, non
  come artefatto di produzione.
- L'export INT8 su architetture ARM Cortex-A76 è sconsigliato in produzione
  fino a quando il backend OpenVINO non integrerà ottimizzazioni SIMD dedicate.

---

## 8. Riferimenti

- [`benchmarks/benchmark_results/CONFIGS.md`](../benchmarks/benchmark_results/CONFIGS.md) — Configurazioni e setup di benchmark
- [`benchmarks/benchmark_results/RESULTS.md`](../benchmarks/benchmark_results/RESULTS.md) — Report completo dei benchmark prestazionali
- [`benchmarks/README.md`](../benchmarks/README.md) — Panoramica della suite di test
- [`ros2_ws/src/nautilus_perception/README.md`](../ros2_ws/src/nautilus_perception/README.md) — Guida ai nodi di percezione
- [`docs/TODO.md`](TODO.md) — Roadmap di sviluppo (Fase 6 = benchmark)
