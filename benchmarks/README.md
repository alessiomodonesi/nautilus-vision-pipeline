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
├── CONFIGS.md                   # Dettaglio delle configurazioni di test
└── README.md
```

---

## Piano di test (Fase 6 e 7)

Il piano si articola in **due fasi sequenziali** che separano il contributo
del clock CPU da quello delle scelte software (modello, quantizzazione,
risoluzione).

### Fase A — senza overclock (riferimento)

6 configurazioni con la CPU a **2400 MHz** (nominale Pi 5), da eseguire
**3 volte ciascuna**:

| # | ID | Config | Modello | half_res | imgsz |
| --- | --- | --- | --- | --- | --- |
| 1 | `A_baseline` | solo camera | — | — | — |
| 2 | `B1_pt` | camera + detection | `yolov8n.pt` | True | 640 |
| 3 | `B2_ov_fp32` | camera + detection | `yolov8n_openvino_640_fp32` | False | 640 |
| 4 | `B3_ov_int8_640` | camera + detection | `yolov8n_openvino_640_int8` | False | 640 |
| 5 | `B4_ov_int8_416` | camera + detection | `yolov8n_openvino_416_int8` | False | 416 |
| 6 | `C_full` | camera + enh + detection | `yolov8n_openvino_640_fp32` | False | 640 |

### Fase B — con overclock (2800 MHz)

5 configurazioni, tutte con detection attiva, da eseguire **3 volte
ciascuna**. `A_baseline` è esclusa: il collo di bottiglia dell'acquisizione
non è la CPU e l'overclock sprecherebbe solo budget termico.

| # | ID | Config | Modello | half_res | imgsz |
| --- | --- | --- | --- | --- | --- |
| 1 | `B1_pt_oc` | camera + detection | `yolov8n.pt` | True | 640 |
| 2 | `B2_ov_fp32_oc` | camera + detection | `yolov8n_openvino_640_fp32` | False | 640 |
| 3 | `B3_ov_int8_640_oc` | camera + detection | `yolov8n_openvino_640_int8` | False | 640 |
| 4 | `B4_ov_int8_416_oc` | camera + detection | `yolov8n_openvino_416_int8` | False | 416 |
| 5 | `C_full_oc` | camera + enh + detection | `yolov8n_openvino_640_fp32` | False | 640 |

### Totale

- **Fase A**: 18 run (6 config × 3)
- **Fase B**: 15 run (5 config × 3)
- **Totale**: 33 run, ~4.5 h stimate

L'obiettivo della Fase B è quantificare se l'overclock porta un guadagno
in FPS/latenza sufficiente a giustificare l'aumento di temperatura e il
rischio di throttling a box chiusa. Il confronto chiave è `B*` vs `B*_oc`
e `C_full` vs `C_full_oc`.

Per i dettagli su come attivare/disattivare l'overclock, sulla verifica
dei flag di throttling e sui valori attesi, vedi [`CONFIGS.md`](CONFIGS.md).

### Uso rapido del wrapper

```bash
cd ~/nautilus-vision-pipeline
./benchmarks/scripts/run_benchmark.sh <config> <run_n>
# es: ./benchmarks/scripts/run_benchmark.sh B2_ov_fp32 1
#     ./benchmarks/scripts/run_benchmark.sh B2_ov_fp32_oc 1
```

Il wrapper gestisce: stop servizi, check temperatura, lancio pipeline con
`include_stereo_camera:=true`, lock fotometrico, warmup 30s, monitor
sistema 300s, benchmark latenze 120s, scrittura metadata, cooldown 30s.

### Batch completo

```bash
# Fase A — senza OC (assicurati che config.txt sia a 2400 MHz e riavvia)
for cfg in A_baseline B1_pt B2_ov_fp32 B3_ov_int8_640 B4_ov_int8_416 C_full; do
    for n in 1 2 3; do
        ./benchmarks/scripts/run_benchmark.sh "$cfg" "$n"
    done
done

# Fase B — con OC (modifica config.txt a 2800 MHz, riavvia, verifica clock)
for cfg in B1_pt_oc B2_ov_fp32_oc B3_ov_int8_640_oc B4_ov_int8_416_oc C_full_oc; do
    for n in 1 2 3; do
        ./benchmarks/scripts/run_benchmark.sh "$cfg" "$n"
    done
done
```

Da lanciare in `tmux` o `screen`. Al termine, in `results/csv/` ci sono
33 × 3 file (latency, system, metadata) più i log di launch.

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
- Log ogni secondo per 1 h a box chiusa, nelle stesse configurazioni di
  Fase A e B (l'obiettivo è verificare se l'OC è sostenibile).

### Accuratezza (Fase 6)

- **mAP@0.5** e **mAP@0.5:0.95** su COCO128 per `yolov8n.pt` e
  `yolov8n_openvino_640_fp32` — test di non-regressione dell'export OpenVINO.
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

Misura latenza media, p50, p95 e FPS per le varianti `.pt` e OpenVINO.
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

Per `A_baseline`: `--enhanced-topic "" --targets-topic ""`.
Per `C_full`: `--enhanced-topic /stereo/lx/image_enhanced`.

### mAP sul validation set (non-regressione export OpenVINO)

```bash
# yolov8n.pt
python3 benchmarks/scripts/evaluate_map.py \
    --weights ros2_ws/src/nautilus_perception/nautilus_perception/data/weights/yolov8n.pt \
    --data benchmarks/datasets/coco128.yaml \
    --imgsz 640 --tag yolov8n_pt \
    --out benchmarks/results/csv/map_yolov8n_pt.csv

# yolov8n_openvino_640_fp32
python3 benchmarks/scripts/evaluate_map.py \
    --weights ros2_ws/src/nautilus_perception/nautilus_perception/data/weights/yolov8n_openvino_640_fp32 \
    --data benchmarks/datasets/coco128.yaml \
    --imgsz 640 --tag yolov8n_ov_fp32 \
    --out benchmarks/results/csv/map_yolov8n_ov_fp32.csv
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

**Nota sul clock CPU**: il metadata NON registra il clock attivo al boot.
Va verificato manualmente con `vcgencmd measure_clock arm` prima di ogni
sessione, oppure controllato a posteriori nella colonna `cpu_clock_mhz`
del CSV `_system.csv`. Se il clock non corrisponde alla fase attesa, la
run è da scartare.

---

## Note operative

- Tutti gli script sono **headless** (nessuna GUI). Il wrapper lancia sempre
  con `enable_debug:=false` per non falsare le latenze con l'overhead di
  `cv2.imshow`.
- Il salvataggio su MicroSD è **disabilitato** durante i benchmark
  (`enable_saving:=false`): l'I/O introduce jitter e falsa le misure.
- ⚠️ La detection YOLOv8n su Pi 5 **non tiene i 5 FPS** a 720p. Il rate
  effettivo di `/stereo_down/targets` è ~2.7 Hz con `.pt` e ~3.2 Hz con
  OpenVINO FP32 (senza OC). Questo è il collo di bottiglia documentato
  dalla Fase 6.
- ⚠️ Skew stereo misurato il 15/10/2026: **~6.6–7.9 ms** (storico: ~1.5 ms
  in `DEBUG.md`). Da indagare post-Fase 6, non blocca i run.
- ⚠️ Con OC attivo (2800 MHz), verifica `vcgencmd get_throttled` sui CSV
  system: se uno dei bit `16`-`19` è settato, la run è compromessa e va
  scartata.
