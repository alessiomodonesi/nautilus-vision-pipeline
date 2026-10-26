# Nautilus Vision — Benchmark Prestazionali & Stress Test Termico

Cartella dedicata ai test prestazionali, termici e di accuratezza della pipeline Nautilus Vision sul target hardware: **Raspberry Pi 5 (8 GB RAM, box stagna in alluminio, dissipazione passiva senza ventola attiva)**.

Questa cartella documenta e implementa:

- **Fase 6 (Benchmark Prestazionali & Accuratezza)** di `docs/TODO.md`
- **Fase 7 (Stress Test Termico a Box Chiusa)** di `docs/TODO.md`

---

## Indice della Documentazione

| Ambito | Documento di Configurazione | Report dei Risultati | Wrapper Principale |
| :--- | :--- | :--- | :--- |
| **Generale** | Questo file (`README.md`) | — | — |
| **Fase 6 — Benchmark** | [`benchmark_results/CONFIGS.md`](benchmark_results/CONFIGS.md) | [`benchmark_results/RESULTS.md`](benchmark_results/RESULTS.md) | [`run_benchmark.sh`](run_benchmark.sh) |
| **Fase 7 — Stress Test** | [`thermal_results/CONFIGS.md`](thermal_results/CONFIGS.md) | [`thermal_results/RESULTS.md`](thermal_results/RESULTS.md) | [`run_thermal_test.sh`](run_thermal_test.sh) |

---

## Struttura della Cartella

```text
benchmarks/
├── README.md                          # Questo file (panoramica generale Fase 6 & 7)
├── run_benchmark.sh                   # Wrapper Fase 6: lancia un run prestazionale completo
├── run_thermal_test.sh                # Wrapper Fase 7: lancia uno stress test termico da 1h
├── scripts/
│   ├── benchmark_pipeline.py          # Subscriber ROS 2: latenze p50/p95 e delay inter-nodo
│   ├── check_imgsz.py                 # Ispezione shape e metadata di input .pt e OpenVINO
│   ├── evaluate_map.py                # Calcolo mAP@0.5 e mAP@0.5:0.95 su dataset COCO128
│   ├── model_benchmark.py             # Confronto inferenza .pt vs OpenVINO (standalone, no ROS)
│   ├── plot_results.py                # Generazione grafici Fase 6 (8 PNG comparativi)
│   ├── plot_results_thermal.py        # Generazione grafici Fase 7 (5 PNG per test termici)
│   ├── system_monitor.py              # Monitoraggio telemetria Fase 6 (CPU%, RAM, Temp, Clock)
│   └── thermal_stress_test.py         # Nodo telemetrico unificato a 1 Hz per Fase 7
├── datasets/
│   ├── coco128/                       # 128 immagini COCO con relative etichette
│   ├── coco128.yaml                   # Configurazione Ultralytics con percorsi locali
│   ├── images/                        # Immagini di test (enhancement, waternet)
│   ├── videos/                        # Video stereo di test per la pipeline
│   └── tools/
│       └── clean_dataset.py           # Filtro nitidezza con varianza del Laplaciano
├── benchmark_results/                 # RISULTATI E CONFIGURAZIONI FASE 6
│   ├── CONFIGS.md                     # Dettaglio setup, configurazioni e procedure Fase 6
│   ├── RESULTS.md                     # Report integrato con analisi e grafici Fase A e B
│   ├── csv_no_oc/                     # Dati grezzi Fase A (2400 MHz stock, 18 run)
│   ├── csv_oc/                        # Dati grezzi Fase B (2800 MHz OC, 9 run)
│   ├── plots_no_oc/                   # 8 PNG generati per la sola Fase A
│   ├── plots_oc/                      # 7 PNG generati per la sola Fase B
│   └── plots_comparative/             # 8 PNG di confronto diretto Fase A vs Fase B
└── thermal_results/                   # RISULTATI E CONFIGURAZIONI FASE 7
    ├── CONFIGS.md                     # Dettaglio setup, procedura 1h e configurazioni Fase 7
    ├── RESULTS.md                     # Report integrato dello stress test termico (1 ora)
    ├── csv/                           # Log telemetrici 1 Hz (*_thermal.csv) e metadati
    └── plots/                         # 5 PNG generati per lo stress test termico
```

---

## 1. Fase 6 — Benchmark Prestazionali & Accuratezza

### Obiettivo

Confrontare in modo rigoroso, equo e riproducibile sul target hardware le configurazioni architetturali della pipeline (acquisizione, enhancement, detection) e i diversi formati di quantizzazione del modello di Object Detection (PyTorch `.pt`, OpenVINO FP32, OpenVINO INT8 a 640px e 416px), quantificando:

- Latenza end-to-end e scomposizione interna per stage (`pre`, `infer`, `post`)
- Throughput effettivo (FPS)
- Impronta di risorse (CPU%, RAM, temperatura SoC, frequenza ARM)
- Accuratezza residua (mAP@0.5 e mAP@0.5:0.95 su COCO128)
- Accuratezza metrica della profondità Z (stereo matching a 720p validato)

### Matrice di Test

Il piano si articola in **due fasi sequenziali**:

#### Fase A — Frequenza nominale (2400 MHz, 3 run per config = 18 run)

| ID | Descrizione | Modello | `half_res` | `imgsz` |
| :--- | :--- | :--- | :---: | :---: |
| `A_baseline` | Solo acquisizione stereo camera | — | True | — |
| `B1_pt` | Camera + Detection PyTorch | `yolov8n.pt` | True | 640 |
| `B2_ov_fp32` | Camera + Detection OpenVINO FP32 | `yolov8n_640_fp32_openvino_model` | False | 640 |
| `B3_ov_int8_640` | Camera + Detection OpenVINO INT8 | `yolov8n_640_int8_openvino_model` | False | 640 |
| `B4_ov_int8_416` | Camera + Detection OpenVINO INT8 (416) | `yolov8n_416_int8_openvino_model` | False | 416 |
| `C_full` | Camera + Enhancement (Laplacian/CLAHE) + Detection | `yolov8n_640_fp32_openvino_model` | False | 640 |

#### Fase B — Con Overclock (2800 MHz, 3 run per config = 9 run)

Eseguita sulle 3 configurazioni con detection praticabili (`B1_pt_oc`, `B2_ov_fp32_oc`, `C_full_oc`). Le configurazioni INT8 (`B3`, `B4`) sono state escluse a fronte dell'anomalia rilevata nel plugin ARM di OpenVINO (inferenza oltre gli 8 secondi per frame).

### Risultati Principali di Fase 6

- **Configurazione Consigliata**: `B2_ov_fp32` (OpenVINO FP32 a 640px) è la migliore scelta per la detection: **~2.29 FPS**, latenza interna **435 ms** (vs 497 ms di PyTorch), consumo CPU ~86% e temperatura contenuta (~59 °C).
- **Anomalia INT8**: I modelli OpenVINO INT8 hanno manifestato tempi di inferenza anomali (8.3 secondi per `B3` e 3.5 secondi per `B4`) a causa della mancanza di istruzioni hardware dedicate e fallback lento nel runtime CPU ARM di OpenVINO.
- **Valutazione Overclock (2800 MHz)**: Il clock maggiorato non ha prodotto benefici sostanziali per la detection pura (+0% FPS, latenza stages 451 ms vs 435 ms), mentre ha aumentato la temperatura operativa di ~6 °C (da 59 °C a 65 °C). Solo in `C_full_oc` si è osservato un lieve incremento del throughput (da 0.64 a 0.74 FPS), a fronte di un costo termico elevato.
- **Validazione Metrica Z**: L'accuratezza sulla profondità stimata con la calibrazione stereo 720p (RMS reproiezione 0.125 px, focale rettificata 1500.89 px) è stata validata su 4 distanze campione (0.60 m, 0.70 m, 0.80 m, 0.90 m) con un errore osservato inferiore a **1 cm** (entro ±1.5%).

Per tutti i dettagli, tabelle estese e grafici, consulta [`benchmark_results/RESULTS.md`](benchmark_results/RESULTS.md) e [`benchmark_results/CONFIGS.md`](benchmark_results/CONFIGS.md).

---

## 2. Fase 7 — Stress Test Termico a Box Chiusa

### Obiettivo

Validare la fattibilità dell'esecuzione a bordo del Raspberry Pi 5 all'interno dello scafo stagno in alluminio a dissipazione puramente passiva (senza ventola attiva). Verificare se la temperatura del SoC raggiunge o meno la soglia di throttling (80 °C soft limit / 85 °C hard limit) durante una sessione operativa continua di **1 ora (3600 secondi)**.

### Matrice di Test

3 configurazioni continue da 3600 secondi ciascuna a clock nominale (2400 MHz), campionate a 1 Hz da `thermal_stress_test.py`:

1. `T_baseline`: Solo acquisizione stereo camera a 5 FPS nominali.
2. `T_detection`: Acquisizione stereo camera + detection YOLOv8n OpenVINO FP32 640px.
3. `T_full`: Pipeline completa (Acquisizione + Enhancement Laplacian/CLAHE + Detection).

### Risultati Principali di Fase 7

- **Stabilità Termica Garantita**: **Nessun evento di throttling termico (`get_throttled = 0x0`)** rilevato su nessuna delle 3 configurazioni.
- **Temperatura Massima SoC**:
  - `T_baseline`: media **56.80 °C**, max **60.90 °C** (CPU 29.6%).
  - `T_detection`: media **65.40 °C**, max **69.70 °C** (CPU 93.6%, throughput **1.40 FPS**, latenza **698 ms**).
  - `T_full`: media **61.07 °C**, max **65.30 °C** (CPU 50.1% a regime per saturazione code).
- **Margine di Sicurezza**: Sotto carico continuo massimo di detection (`T_detection`), la temperatura a regime si assesta sui ~68-69 °C, garantendo un margine di sicurezza di **oltre 10 °C** rispetto alla soglia di throttling (80 °C).
- **Verifica Memoria**: Nessun memory leak osservato (RAM piatta su tutta l'ora: max 2.58 GB / 8 GB).

Per tutti i grafici di temperatura, CPU, RAM e scomposizione della latenza, consulta [`thermal_results/RESULTS.md`](thermal_results/RESULTS.md) e [`thermal_results/CONFIGS.md`](thermal_results/CONFIGS.md).

---

## 3. Guida all'Uso degli Script

### A. Esecuzione Benchmark Fase 6

```bash
# Esecuzione singola configurazione (es. B2 OpenVINO FP32, run 1)
./benchmarks/run_benchmark.sh B2_ov_fp32 1

# Esecuzione batch Fase A (senza OC, nominale 2400 MHz)
for cfg in A_baseline B1_pt B2_ov_fp32 B3_ov_int8_640 B4_ov_int8_416 C_full; do
    for n in 1 2 3; do
        ./benchmarks/run_benchmark.sh "$cfg" "$n"
    done
done

# Esecuzione batch Fase B (con OC 2800 MHz impostato in config.txt)
for cfg in B1_pt_oc B2_ov_fp32_oc C_full_oc; do
    for n in 1 2 3; do
        ./benchmarks/run_benchmark.sh "$cfg" "$n"
    done
done
```

### B. Esecuzione Stress Test Termico Fase 7

```bash
# Esecuzione stress test 1h (3600 secondi) per T_detection
./benchmarks/run_thermal_test.sh T_detection 1 3600

# Esecuzione per tutte le 3 configurazioni termiche
for cfg in T_baseline T_detection T_full; do
    ./benchmarks/run_thermal_test.sh "$cfg" 1 3600
done
```

### C. Generazione Grafici

#### Grafici Fase 6 (`plot_results.py`)

```bash
# Grafici Fase A (senza OC)
python3 benchmarks/scripts/plot_results.py \
    --csv benchmarks/benchmark_results/csv_no_oc/ \
    --out benchmarks/benchmark_results/plots_no_oc/

# Grafici Fase B (con OC)
python3 benchmarks/scripts/plot_results.py \
    --csv benchmarks/benchmark_results/csv_oc/ \
    --out benchmarks/benchmark_results/plots_oc/

# Grafici Comparativi (A vs B)
# Nota: posizionando entrambi i set di CSV o usando directory combinata
python3 benchmarks/scripts/plot_results.py \
    --csv benchmarks/benchmark_results/csv_no_oc/ \
    --out benchmarks/benchmark_results/plots_comparative/
```

#### Grafici Fase 7 (`plot_results_thermal.py`)

```bash
python3 benchmarks/scripts/plot_results_thermal.py \
    --csv benchmarks/thermal_results/csv/ \
    --out benchmarks/thermal_results/plots/
```

### D. Benchmark Standalone e Validazione Modelli

```bash
# Benchmark inferenza puro (senza ROS 2) tra .pt e OpenVINO
python3 benchmarks/scripts/model_benchmark.py --frames 100 \
    --out benchmarks/benchmark_results/csv_no_oc/model_benchmark.csv

# Ispezione shape e formati modelli
python3 benchmarks/scripts/check_imgsz.py

# Valutazione mAP su dataset COCO128 (test di non-regressione OpenVINO)
python3 benchmarks/scripts/evaluate_map.py \
    --weights ros2_ws/src/nautilus_perception/nautilus_perception/data/weights/yolov8n_640_fp32_openvino_model \
    --data benchmarks/datasets/coco128.yaml \
    --imgsz 640 --tag yolov8n_ov_fp32 \
    --out benchmarks/benchmark_results/csv_no_oc/map_yolov8n_ov_fp32.csv
```

---

## 4. Note Operative e Buone Pratiche

- **Isolamento della Sessione**: Prima di ogni sessione, assicurarsi che i servizi systemd di produzione siano terminati nell'ordine corretto (`systemctl stop`, poi `systemctl disable`, poi `pkill`). I servizi critici da fermare sono:
  - `nautilus-vision.service`
  - `nautilus-bag.service`
  - `lock-cameras.service`
- **Soglie Termiche di Sicurezza**:
  - `run_benchmark.sh` richiede SoC < 55 °C prima di autorizzare la partenza.
  - `run_thermal_test.sh` implementa un plateau di stabilità termica iniziale e attende il cooldown stazionario al termine della run.
- **Validazione Throttling**: Verificare sempre che la colonna `throttled` dei CSV sia rigorosamente `0x0`. Se uno dei bit 16-19 è attivo (`0x10000`, `0x20000`, `0x40000`, `0x80000`), la run ha subito throttling ed è da scartare.
- **Requisiti Visivi della Scena**: Per garantire la validità del post-processing stereo (calcolo disparità e coordinate 3D X, Y, Z), la telecamera deve inquadrare oggetti con texture e caratteristiche riconoscibili da YOLO (es. boe, conchiglie, bottiglie). Un frame uniforme o privo di target ridurrebbe artificialmente a zero il tempo dello stage `post`.
- **Risoluzione e Matching Stereo**: La calibrazione di riferimento è impostata a **1280x720** con lock di esposizione (`LensPosition`: 2.6 per sinistra, 1.5 per destra).
