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
│   ├── model_benchmark.py       # Confronto YOLOv8 nativo vs OpenVINO su frame dummy
│   ├── yolo_inference.py        # Wrapper inferenza YOLOv8 (Ultralytics)
│   ├── ov_inference.py          # Wrapper inferenza OpenVINO
│   └── infer_best_openvino.py   # Demo inferenza best_openvino_model (marine debris)
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
│   ├── csv/                     # Dati grezzi temporizzati
│   └── plots/                   # PNG dei grafici generati
└── README.md
```

---

## Configurazioni di test (Fase 6)

Tre configurazioni di pipeline, da eseguire in sequenza sullo stesso hardware e con la stessa scena:

| # | Configurazione | Comando |
| --- | --- | --- |
| 1 | Solo acquisizione (baseline) | `ros2 launch nautilus_perception pipeline.launch.py enable_enhancement:=false enable_detection:=false enable_saving:=false enable_metrics:=true` |
| 2 | Acquisizione + Detection | `ros2 launch nautilus_perception pipeline.launch.py enable_enhancement:=false enable_detection:=true enable_saving:=false enable_metrics:=true` |
| 3 | Pipeline completa | `ros2 launch nautilus_perception pipeline.launch.py enable_enhancement:=true enable_detection:=true enable_saving:=false enable_metrics:=true` |

Ogni configurazione va eseguita **almeno 3 volte** per valutare la varianza.

---

## Metriche raccolte

### Prestazioni (Fase 6)

- **Latenza** media, p50, p95 — con `time.perf_counter`, separata in
  pre-processing, inferenza, post-processing.
- **FPS** effettivi per nodo (`metrics_node`).
- **CPU%** per processo (`psutil` o `/proc/stat`).
- **RAM** residente per nodo.

### Termica (Fase 7)

- Temperatura SoC (`vcgencmd measure_temp`).
- Frequenza CPU (`vcgencmd measure_clock arm`).
- Flag di throttling (`vcgencmd get_throttled`).
- Log ogni secondo per 1 ora a box chiusa.

### Accuratezza (Fase 6)

- **mAP@0.5** e **mAP@0.5:0.95** sul validation set, per ogni variante
  (YOLOv8n `.pt` vs `yolov8n_openvino_model`, con/senza enhancement).
- **Errore su Z**: oggetto a 0.6 / 0.7 / 0.8 / 0.9 m → verifica entro ±5%.
  ✅ Validato il 13/10/2026 su calibrazione 720p (RMS 0.125 px), errore osservato < 1 cm.

---

## Uso rapido

### Benchmark modello (YOLO vs OpenVINO, senza ROS)

```bash
cd benchmarks/scripts
python3 model_benchmark.py
```

Stampa latenza media e throughput per 100 frame dummy a 1280×720.

### Monitor di sistema (in parallelo alla pipeline)

```bash
python3 benchmarks/scripts/system_monitor.py \
    --duration 3600 \
    --out benchmarks/results/csv/thermal_run1.csv
```

Lascia girare in un secondo terminale mentre la pipeline è attiva.

### mAP sul validation set

```bash
python3 benchmarks/scripts/evaluate_map.py \
    --weights ros2_ws/src/nautilus_perception/nautilus_perception/data/weights/yolov8n.pt \
    --data benchmarks/datasets/coco128.yaml \
    --imgsz 640 --tag yolov8n_pt \
    --out benchmarks/results/csv/map_yolov8n_pt.csv
```

### Grafici

```bash
python3 benchmarks/scripts/plot_results.py \
    --csv benchmarks/results/csv/ \
    --out benchmarks/results/plots/
```

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

Per ogni sessione di benchmark, registrare in `results/csv/` un file
`<data>_<config>.csv` con:

- Commit hash del repo (`git rev-parse HEAD`).
- Configurazione pipeline (i tre flag `enable_*`).
- Modello e precisione (`.pt` / OpenVINO FP32 / FP16).
- Numero di thread (`num_threads` in `detection_params.yaml`).
- Temperatura iniziale del SoC.

Senza questi metadati i dati non sono confrontabili tra sessioni.

---

## Note

- Tutti gli script sono **headless** (nessuna GUI) per non falsare i benchmark
  con l'overhead di `cv2.imshow`.
- Il salvataggio su MicroSD è **disabilitato** durante i benchmark di timing:
  l'I/O introduce jitter e falsa le misure di latenza.
- Per lo stress test termico, il salvataggio può essere riabilitato per
  replicare la condizione di missione reale, ma va documentato.
