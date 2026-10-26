# Fase 6 — Configurazioni e Metodologia di Benchmark

Questo documento descrive in dettaglio le configurazioni di test, i prerequisiti operativi, il piano sperimentale e la procedura di analisi per il benchmark prestazionale e di accuratezza della pipeline Nautilus Vision (**Fase 6 di `docs/TODO.md`**).

Il report completo con i risultati sperimentali e i grafici è consultabile in [`RESULTS.md`](RESULTS.md). Per la panoramica generale dell'intero suite di test vedi [`../README.md`](../README.md).

Ogni configurazione è stata eseguita **3 volte** sullo stesso target hardware (Raspberry Pi 5, 8 GB RAM, dissipazione passiva, clock nominale 2400 MHz o overclock 2800 MHz), a parità di scena visiva, illuminazione e condizioni di montaggio meccanico.

---

## 1. Prerequisiti Operativi Comuni

Prima di avviare qualsiasi sessione di benchmark sul Raspberry Pi, è indispensabile garantire un ambiente di esecuzione privo di interferenze o contese di risorse.

### Pulizia dei Servizi di Background

```bash
# 1. Stop controllato dei servizi systemd di produzione
sudo systemctl stop nautilus-bag.service
sudo systemctl stop nautilus-vision.service
sudo systemctl stop lock-cameras.service

# 2. Disabilitazione (impedisce il riavvio automatico al boot, essenziale per la Fase B con OC)
sudo systemctl disable nautilus-bag.service
sudo systemctl disable nautilus-vision.service
sudo systemctl disable lock-cameras.service

# 3. Conferma dello stato inattivo
systemctl is-active nautilus-vision.service   # atteso: inactive
systemctl is-enabled nautilus-vision.service  # atteso: disabled

# 4. Terminazione di eventuali processi orfani (solo DOPO lo stop di systemd)
#    Se eseguito prima dello stop, systemd interpreterebbe l'uscita come crash
#    e farebbe ripartire i processi (Restart=on-failure, RestartSec=5).
pkill -f "ros2 launch nautilus_camera" || true
pkill -f camera_node || true
pkill -f detection_node || true
pkill -f enhancement_node || true
pkill -f "ros2 bag record" || true
sleep 3

# 5. Verifica assenza processi residui e publisher sui topic camera
ps aux | grep -E "camera_node|detection_node|enhancement_node|ros2 bag record" | grep -v grep
# non deve stampare nulla

source /opt/ros/jazzy/setup.bash
source ~/nautilus-vision-pipeline/ros2_ws/install/setup.bash
ros2 topic info /stereo/lx/camera/image_raw -v
# atteso: "Publisher count: 0"
```

### Vincoli Operativi di Misura

- **Nessun I/O continuativo su disco**: `saving_node` è escluso dal launch di benchmark e `nautilus-bag.service` è disattivato. Questo evita che la scrittura su MicroSD introduca jitter o rallentamenti di I/O non correlati alla pipeline di visione.
- **`enable_metrics:=true`**: Il nodo di metriche interno rimane attivo per la controprova del throughput (FPS) e dello skew stereo.
- **`enable_debug:=false`**: Nessuna GUI o finestra OpenCV (`cv2.imshow`) aperta, per eliminare il costo di rendering video a schermo.
- **Governor CPU su `performance`**: Fissa la frequenza massima dei 4 core ARM Cortex-A76 eliminando il ritardo di scalatura della CPU.

---

## 2. Piano Sperimentale e Matrice Configurazioni

Il piano si suddivide in due fasi sequenziali:

1. **Fase A (senza overclock, 2400 MHz)**: Baseline di riferimento hardware e confronto software tra modelli e quantizzazioni.
2. **Fase B (con overclock, 2800 MHz)**: Valutazione del beneficio del clock maggiorato sulle configurazioni di detection operative.

### Fase A — Frequenza Nominale (2400 MHz)

6 configurazioni testate 3 volte ciascuna (**18 run totali**):

| # | ID Config | Descrizione Pipeline | Modello / Formato | `half_res` | `imgsz` |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `A_baseline` | Solo acquisizione stereo (camera_node) | — | True | 640 |
| 2 | `B1_pt` | Camera + Detection PyTorch | `yolov8n.pt` | True | 640 |
| 3 | `B2_ov_fp32` | Camera + Detection OpenVINO FP32 | `yolov8n_640_fp32_openvino_model` | False | 640 |
| 4 | `B3_ov_int8_640` | Camera + Detection OpenVINO INT8 (640) | `yolov8n_640_int8_openvino_model` | False | 640 |
| 5 | `B4_ov_int8_416` | Camera + Detection OpenVINO INT8 (416) | `yolov8n_416_int8_openvino_model` | False | 416 |
| 6 | `C_full` | Pipeline completa (Camera + Enh + Det) | `yolov8n_640_fp32_openvino_model` | False | 640 |

### Fase B — Con Overclock (2800 MHz)

Eseguita sulle 3 configurazioni praticabili (**9 run totali**):

| # | ID Config | Descrizione Pipeline | Modello / Formato | `half_res` | `imgsz` |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `B1_pt_oc` | Camera + Detection PyTorch | `yolov8n.pt` | True | 640 |
| 2 | `B2_ov_fp32_oc` | Camera + Detection OpenVINO FP32 | `yolov8n_640_fp32_openvino_model` | False | 640 |
| 3 | `C_full_oc` | Pipeline completa (Camera + Enh + Det) | `yolov8n_640_fp32_openvino_model` | False | 640 |

> [!NOTE]
> **Esclusione dei modelli INT8 in Fase B**: I risultati della Fase A hanno rivelato un tempo di inferenza per frame anomalo sui modelli quantizzati INT8 (8.32 s su `B3` e 3.55 s su `B4`), dovuto all'assenza di accelerazione vettoriale INT8 nel plugin CPU ARM di OpenVINO. Un incremento di clock CPU del +16.7% (da 2400 a 2800 MHz) non avrebbe colmato un ritardo di 8 secondi, surriscaldando inutilmente il SoC. Di conseguenza, le configurazioni `B3_ov_int8_640_oc` e `B4_ov_int8_416_oc` sono state escluse dal batch Fase B.

---

## 3. Gestione dell'Overclock (Fase B)

Il controllo dei clock di Raspberry Pi 5 risiede nel file `/boot/firmware/config.txt`.

### Configurazione Nominale (2400 MHz — Fase A)

```ini
[pi5]
arm_freq=2400
```

### Configurazione Overclock (2800 MHz — Fase B)

```ini
[pi5]
arm_freq=2800
gpu_freq=1000
over_voltage_delta=50000
```

### Applicazione e Verifica

Dopo aver modificato il file:

```bash
sudo reboot
```

Al riavvio, confermare la frequenza di clock attiva:

```bash
vcgencmd measure_clock arm
# Risposta per 2400 MHz: frequency(0)=2400000000
# Risposta per 2800 MHz: frequency(0)=2800000000
```

### Decodifica dei Flag di Throttling (`vcgencmd get_throttled`)

La presenza di sottotensioni o surriscaldamenti invalida le misurazioni di benchmark. Il comando restituisce una maschera a bit in formato esadecimale:

| Bit | Valore Hex | Significato |
| :---: | :---: | :--- |
| **0** | `0x1` | Sottotensione rilevata (Under-voltage) |
| **1** | `0x2` | Frequenza ARM limitata (ARM frequency capped) |
| **2** | `0x4` | Throttling attualmente attivo |
| **3** | `0x8` | Raggiunto soft temperature limit |
| **16** | `0x10000` | Sottotensione verificatasi dopo il boot |
| **17** | `0x20000` | Frequenza ARM limitata dopo il boot |
| **18** | `0x40000` | Throttling verificatosi dopo il boot |
| **19** | `0x80000` | Soft temperature limit raggiunto dopo il boot |

Qualsiasi run in cui uno dei bit **16–19** risulti asserito nel file di log di sistema (`*_system.csv`) o nei metadati finali è da considerare compromessa e non valida. Nelle nostre sessioni, tutti i run hanno mantenuto rigorosamente il flag `0x0`.

---

## 4. Requisiti della Scena Visiva e Validazione Stereo Z

Per garantire la riproducibilità e l'attendibilità dei benchmark sul post-processing (stereo matching e stima 3D), la scena inquadrata deve soddisfare i seguenti requisiti:

1. **Target Riconoscibili**: La camera stereo deve inquadrare oggetti con feature e classi note a YOLO (es. lattine, bottiglie, boe). Se inquadrasse una parete bianca vuota, la rete non produrrebbe bounding box e il matcher stereo (`core_detection.py`) verrebbe saltato, falsando a zero il tempo dello stage `post`.
2. **Algoritmo di Enhancement Deterministico**: In `C_full`, il nodo `enhancement_node` non esegue reti neurali pesanti (come WaterNet), ma un pipeline deterministico basato su **Laplacian Sharpening + CLAHE**. L'elaborazione non risente del contenuto specifico dell'immagine, garantendo tempi di calcolo riproducibili.
3. **Accuratezza Z Validata**: La calibrazione stereo a 1280x720 (focale rettificata $f_x = 1500.89\text{ px}$, baseline $B = 120\text{ mm}$, RMS di reproiezione **0.125 px**) è stata preventivamente validata su 4 distanze note:
   - 0.60 m, 0.70 m, 0.80 m, 0.90 m
   - Errore residuo osservato: **< 1 cm** (scarto relativo < 1.5%), ampiamente entro la specifica richiesta di ±5%.

---

## 5. Wrapper di Lancio (`run_benchmark.sh`)

Lo script `benchmarks/run_benchmark.sh` standardizza l'esecuzione di ciascuna run garantendo condizioni ambientali identiche:

```bash
cd ~/nautilus-vision-pipeline
./benchmarks/run_benchmark.sh <CONFIG_ID> <RUN_NUMBER>
# Esempio:
# ./benchmarks/run_benchmark.sh B2_ov_fp32 1
# ./benchmarks/run_benchmark.sh B2_ov_fp32_oc 1
```

### Ciclo Operativo dello Script

1. **Controllo Termico Bloccante**: Misura la temperatura con `vcgencmd measure_temp`. Se SoC > 55 °C, il run viene abortito per evitare accumulo termico iniziale.
2. **CPU Governor**: Imposta automaticamente tutti i core su `performance` via sysfs.
3. **Pulizia e Daemon**: Ferma i servizi systemd, killa eventuali nodi orfani e riavvia `ros2 daemon`.
4. **Hardware Unlock**: Sblocca i device camera (`/dev/video0` e `/dev/video1`) con `fuser -k -9`.
5. **Launch Pipeline**: Avvia `pipeline.launch.py` con gli opportuni override di modello, risoluzione e tipo di input (`raw` o `enhanced`).
6. **Lock Fotometrico**: Esegue `deploy/lock_cameras.py` dopo 5 s per fissare l'esposizione e il guadagno.
7. **Warmup di 30 s**: Consente alla pipeline, alle code ROS 2 e alle cache di runtime di entrare a regime.
8. **Monitoraggio Parallelo**:
   - `benchmarks/scripts/system_monitor.py`: Registra per 300 s CPU%, RAM, temperatura e clock ARM ogni 1.0 s.
   - `benchmarks/scripts/benchmark_pipeline.py`: Registra per 120 s le latenze di arrivo frame e la scomposizione `pre`/`infer`/`post`.
9. **Chiusura e Cooldown**: Termina la pipeline con `kill -9`, registra il file `*_metadata.csv` e attende 10 s di cooldown.

### File Prodotti per Ciascun Run

I dati generati dal wrapper vengono salvati con la seguente convenzione di naming:

- `<DATE>_<CONFIG>_run<N>_latency.csv`: Statistiche latenza end-to-end e FPS per topic
- `<DATE>_<CONFIG>_run<N>_stages.csv`: Tempi medi e percentili per gli stage `pre`, `infer`, `post`, `total`
- `<DATE>_<CONFIG>_run<N>_system.csv`: Campionamento temporale di temperatura SoC, clock ARM, CPU% e RAM
- `<DATE>_<CONFIG>_run<N>_metadata.csv`: Metadati di riproducibilità (commit hash, configurazione, temperature iniziale/finale, throttling flags)
- `<DATE>_<CONFIG>_run<N>_launch.log`: Log completo di output del launch file ROS 2

---

## 6. Esecuzione Batch Completa

### Fase A (senza overclock, ~2.5 ore)

```bash
for cfg in A_baseline B1_pt B2_ov_fp32 B3_ov_int8_640 B4_ov_int8_416 C_full; do
    for n in 1 2 3; do
        ./benchmarks/run_benchmark.sh "$cfg" "$n"
    done
done
```

### Fase B (con overclock, ~1.5 ore)

```bash
# Dopo aver impostato arm_freq=2800 in config.txt e riavviato
for cfg in B1_pt_oc B2_ov_fp32_oc C_full_oc; do
    for n in 1 2 3; do
        ./benchmarks/run_benchmark.sh "$cfg" "$n"
    done
done
```

---

## 7. Generazione dei Grafici (`plot_results.py`)

Al termine della raccolta dei dati, lo script `benchmarks/scripts/plot_results.py` aggrega i CSV e genera i grafici:

```bash
# 1. Grafici Fase A (stock 2400 MHz)
python3 benchmarks/scripts/plot_results.py \
    --csv benchmarks/benchmark_results/csv_no_oc/ \
    --out benchmarks/benchmark_results/plots_no_oc/

# 2. Grafici Fase B (overclock 2800 MHz)
python3 benchmarks/scripts/plot_results.py \
    --csv benchmarks/benchmark_results/csv_oc/ \
    --out benchmarks/benchmark_results/plots_oc/

# 3. Grafici Comparativi Diretti (Fase A vs Fase B)
python3 benchmarks/scripts/plot_results.py \
    --csv benchmarks/benchmark_results/csv_no_oc/ \
    --out benchmarks/benchmark_results/plots_comparative/
```

### Elenco dei Grafici Generati

1. `01_latency_mean_by_config.png`: Latenza media per stage e configurazione
2. `02_latency_p50_p95.png`: Confronto tra mediana (P50) e coda del 95° percentile (P95)
3. `03_fps_by_config.png`: Throughput effettivo (FPS) per topic
4. `04_soc_temp.png`: Andamento della temperatura del SoC nel tempo
5. `05_cpu.png`: Utilizzo della CPU (%) nel tempo
6. `06_ram.png`: Occupazione della memoria RAM (MB) nel tempo
7. `07_map_comparison.png`: Confronto mAP@0.5 e mAP@0.5:0.95 su COCO128 (non applicabile in `plots_oc`)
8. `08_detection_stages.png`: Scomposizione temporale interna (`pre`, `inferenza`, `post`)
