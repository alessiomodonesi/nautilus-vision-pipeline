# Nautilus — Benchmark & Validation

Cartella dedicata ai test prestazionali, termici e di accuratezza della pipeline Nautilus Vision sul target hardware (Raspberry Pi 5, 8 GB RAM, no dissipazione attiva, box stagna).

Questa cartella implementa la **Fase 6 (Benchmark)** e la **Fase 7 (Stress test termico)** della roadmap in `docs/TODO.md`.

---

## Struttura

```text
benchmarks/
├── scripts/
│   ├── benchmark_pipeline.py    # Profilazione latenze p50/p95 e delay inter-nodo
│   ├── system_monitor.py        # Logging CPU%, RAM, temperatura, vcgencmd throttled
│   ├── evaluate_map.py          # Calcolo mAP sul validation set per ogni variante
│   ├── plot_results.py          # Grafici comparativi a partire dai CSV
│   ├── model_benchmark.py       # Confronto .pt vs OpenVINO standalone (no ROS)
│   ├── check_imgsz.py           # Ispeziona shape input di .pt e .ov
│   └── run_benchmark.sh         # Wrapper: lancia un run completo di una config
├── datasets/
│   ├── coco128/                 # 128 immagini COCO + labels (scaricate)
│   ├── coco128.yaml             # config Ultralytics con path assoluto
│   ├── images/                  # Immagini di test (enhancement, waternet)
│   ├── videos/                  # Video stereo di test per pipeline
│   ├── raw/                     # Dataset grezzi annotati
│   ├── processed/               # Output di clean_dataset.py
│   └── tools/
│       └── clean_dataset.py     # Filtro varianza Laplaciano per selezione frame
├── results/
│   ├── csv/                     # Dati grezzi temporizzati + metadata
│   └── plots/                   # PNG dei grafici generati
├── CONFIGS.md                   # Dettaglio delle 5 configurazioni di test
└── README.md
```

---

## Configurazioni di test (Fase 6)

Cinque configurazioni principali, da eseguire **3 volte ciascuna** sullo
stesso hardware, con la stessa scena e la stessa illuminazione:

| # | ID | Config | Modello | half_res | imgsz |
| --- | --- | --- | --- | --- | --- |
| 1 | `A_baseline` | solo camera | — | — | — |
| 2 | `B_pt` | camera + detection | `yolov8n.pt` | True | 640 |
| 3 | `B_ov_fp32` | camera + detection | `yolov8n_openvino_640_fp32` | False | 640 |
| 4 | `C_pt` | camera + enh + detection | `yolov8n.pt` | True | 640 |
| 5 | `C_ov_int8_640` | camera + enh + detection | `yolov8n_openvino_640_int8` | False | 640 |

Il confronto `.pt` vs OpenVINO FP32 è l'unica variabile tra B_pt/B_ov_fp32
e C_pt/C_ov_int8_640. Dettaglio completo in [`CONFIGS.md`](CONFIGS.md).

### Uso rapido del wrapper

```bash
cd ~/nautilus-vision-pipeline
./benchmarks/scripts/run_benchmark.sh <config> <run_n>
# es: ./benchmarks/scripts/run_benchmark.sh B_ov_fp32 1
```

Il wrapper gestisce: stop servizi, check temperatura, lancio pipeline con
`include_stereo_camera:=true`, lock fotometrico, warmup 30s, monitor
sistema 300s, benchmark latenze 120s, scrittura metadata, cooldown 30s.

### Batch completo (15 run, ~1 h)

```bash
for cfg in A_baseline B_pt B_ov_fp32 C_pt C_ov_int8_640; do
    for n in 1 2 3; do
        ./benchmarks/scripts/run_benchmark.sh "$cfg" "$n"
    done
done
```

Da lanciare in `tmux` o `screen`. Al termine, in `results/csv/` ci sono
15 × 3 file (latency, system, metadata) più i log di launch.

---

## Metriche raccolte

### Prestazioni (Fase 6)

- **Latenza** media, p50, p95 — con `perf_counter` a bordo del subscriber
  (`benchmark_pipeline.py`), calcolata come `now - header.stamp`.
- **FPS** effettivi per stage (`raw`, `enhanced`, `targets`).
- **CPU%** per processo (`psutil` + `/proc/stat` da `system_monitor.py`).
- **RAM** residente.
- **Frequenza CPU** (`vcgencmd measure_clock arm`).
- **Flag di throttling** (`vcgencmd get_throttled`).

### Termica (Fase 7)

- Temperatura SoC (`vcgencmd measure_temp`).
- Log ogni secondo per 1 h a box chiusa, nelle stesse 5 configurazioni.

### Accuratezza (Fase 6)

- **mAP@0.5** e **mAP@0.5:0.95** su COCO128 per `yolov8n.pt` e
  `yolov8n_openvino_model` — test di non-regressione dell'export OpenVINO.
- **Errore su Z**: oggetto a 0.6 / 0.7 / 0.8 / 0.9 m → verifica entro ±5%.
  ✅ Validato il 13/10/2026 su calibrazione 720p (RMS 0.125 px), errore osservato < 1 cm.

---

## Uso rapido degli script

### Benchmark modello standalone (no ROS)

```bash
cd benchmarks/scripts
python3 model_benchmark.py --frames 100 \
    --out ../results/csv/model_benchmark.csv
```

Misura latenza media, p50, p95 e FPS per 4 varianti:
`yolov8n_pt` (imgsz 640), `yolov8n_ov` (640), `best_pt` (416), `best_ov` (416).
Stampa il boost % OpenVINO per ogni coppia `.pt`/`.ov`.

### Ispezione shape modelli

```bash
python3 check_imgsz.py
```

Mostra input/output shape di `.pt` e directory OpenVINO.

### Monitor di sistema (in parallelo alla pipeline)

```bash
python3 benchmarks/scripts/system_monitor.py \
    --duration 300 \
    --out benchmarks/results/csv/<run>_system.csv
```

### Benchmark latenze (in parallelo alla pipeline)

```bash
python3 benchmarks/scripts/benchmark_pipeline.py \
    --duration 120 \
    --out benchmarks/results/csv/<run>_latency.csv \
    --raw-topic /stereo/lx/camera/image_raw \
    --enhanced-topic "" \
    --targets-topic /stereo_down/targets
```

Per config A: `--enhanced-topic "" --targets-topic ""`.
Per config C: `--enhanced-topic /stereo/lx/image_enhanced`.

### mAP sul validation set (non-regressione export OpenVINO)

```bash
# yolov8n.pt
python3 benchmarks/scripts/evaluate_map.py \
    --weights ros2_ws/src/nautilus_perception/nautilus_perception/data/weights/yolov8n.pt \
    --data benchmarks/datasets/coco128.yaml \
    --imgsz 640 --tag yolov8n_pt \
    --out benchmarks/results/csv/map_yolov8n_pt.csv

# yolov8n_openvino_model
python3 benchmarks/scripts/evaluate_map.py \
    --weights ros2_ws/src/nautilus_perception/nautilus_perception/data/weights/yolov8n_openvino_model \
    --data benchmarks/datasets/coco128.yaml \
    --imgsz 640 --tag yolov8n_ov \
    --out benchmarks/results/csv/map_yolov8n_ov.csv
```

Atteso: le due `map50` differiscono di meno di 0.5 punti (test di non-regressione).

### Grafici comparativi

```bash
python3 benchmarks/scripts/plot_results.py \
    --csv benchmarks/results/csv/ \
    --out benchmarks/results/plots/
```

Genera 7 PNG:

1. `01_latency_mean_by_config.png` — latenza media per stage e config
2. `02_latency_p50_p95.png` — p50 e p95 per stage
3. `03_fps_by_config.png` — FPS effettivi per config
4. `04_soc_temp.png` — temperatura SoC nel tempo
5. `05_cpu.png` — CPU% nel tempo
6. `06_ram.png` — RAM usata nel tempo
7. `07_map_comparison.png` — mAP (se presenti CSV `map_*.csv`)

---

## Preparazione dataset

`clean_dataset.py` filtra le coppie stereo per nitidezza (varianza del
Laplaciano) e le copia in cartelle `keep_*` / `discard_*`. Non modifica mai
i file originali.

```bash
cd benchmarks/datasets/tools
python3 clean_dataset.py --serie 2/serie-1 --threshold 1.99
```

Output in `benchmarks/datasets/processed/clean_output/<serie>/`.

---

## Riproducibilità

Il wrapper `run_benchmark.sh` genera automaticamente per ogni run un
`<data>_<config>_run<N>_metadata.csv` con:

- Commit hash del repo (`git rev-parse HEAD`)
- Config ID e numero di run
- Flag `enable_*` usati
- `params_file` (quale YAML detection)
- Temperatura SoC iniziale e finale

Senza questi metadati i dati non sono confrontabili tra sessioni.

---

## Note operative

- Tutti gli script sono **headless** (nessuna GUI). Il wrapper lancia sempre
  con `enable_debug:=false` per non falsare le latenze con l'overhead di
  `cv2.imshow`.
- Il salvataggio su MicroSD è **disabilitato** durante i benchmark
  (`enable_saving:=false`): l'I/O introduce jitter e falsa le misure.
- ⚠️ La detection YOLOv8n su Pi 5 **non tiene i 5 FPS** a 720p. Il rate
  effettivo di `/stereo_down/targets` è ~2.7 Hz con `.pt` e ~3.2 Hz con
  OpenVINO. Questo è il collo di bottiglia documentato dalla Fase 6.
- ⚠️ Skew stereo misurato il 15/10/2026: **~6.6–7.9 ms** (storico: ~1.5 ms
  in `DEBUG.md`). Da indagare post-Fase 6, non blocca i run.
