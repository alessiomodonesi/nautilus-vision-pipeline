# Fase 7 — Configurazioni e Metodologia dello Stress Test Termico

Questo documento descrive in dettaglio le configurazioni di test, la procedura sperimentale, il funzionamento del wrapper di automazione e gli script dedicati allo stress test termico ad alta durata (**Fase 7 di `docs/TODO.md`**).

Il report completo con i dati sperimentali e l'analisi dei grafici è consultabile in [`RESULTS.md`](RESULTS.md). Per la panoramica generale dell'intera suite di benchmark vedi [`../README.md`](../README.md).

---

## 1. Obiettivo Sperimentale e Contesto Hardware

L'obiettivo fondamentale della **Fase 7** è validare se la pipeline di Computer Vision e il modello di Object Detection possono essere eseguiti in modo continuativo a bordo del Raspberry Pi 5 all'interno dello **scafo stagno sigillato** del veicolo AUV Nautilus, caratterizzato da:

- **Assenza di ventilazione attiva**: Raffreddamento basato esclusivamente sulla conduzione/dissipazione passiva verso le pareti metalliche dello scafo.
- **Rischio di Thermal Throttling**: Raggiunta la soglia di 80 °C (soft limit), il SoC riduce dinamicamente il clock ARM; oltre gli 85 °C (hard limit) si verificano tagli drastici di frequenza che degradano le prestazioni della pipeline.
- **Durata della Prova**: **1 ora continua (3600 secondi)** per ciascuna configurazione, con campionamento telemetrico continuo a frequenza fissa di **1 Hz** (un campione al secondo).

---

## 2. Prerequisiti Operativi Comuni

Prima di avviare ciascun ciclo di test termico, è indispensabile garantire la pulizia della sessione e la stabilità termica iniziale del sistema.

### Pulizia dei Servizi di Background

```bash
# 1. Stop controllato dei servizi di produzione
sudo systemctl stop nautilus-bag.service
sudo systemctl stop nautilus-vision.service
sudo systemctl stop lock-cameras.service

# 2. Disabilitazione per evitare riavvii automatici
sudo systemctl disable nautilus-bag.service
sudo systemctl disable nautilus-vision.service
sudo systemctl disable lock-cameras.service

# 3. Terminazione processi orfani
pkill -f "ros2 launch nautilus_camera" || true
pkill -f camera_node || true
pkill -f detection_node || true
pkill -f enhancement_node || true
pkill -f metrics_node || true
pkill -f "ros2 bag record" || true
sleep 3

# 4. Verifica stato inattivo
ros2 daemon stop  2>/dev/null || true
ros2 daemon start 2>/dev/null || true
```

### Stabilizzazione Termica Iniziale (Idle Plateau)

A differenza dei test prestazionali brevi (Fase 6), lo stress test termico richiede che il sistema parta da una condizione termica stazionaria (plateau a riposo).
Il wrapper `run_thermal_test.sh` implementa un controllo automatico:

- Campiona la temperatura del SoC ogni 5 secondi per un massimo di 60 iterazioni.
- Considera il sistema stabile solo quando la variazione di temperatura ($\Delta T$) tra campioni consecutivi rimane compresa entro **$\pm 1\text{ }^\circ\text{C}$ per almeno 3 controlli consecutivi**.
- Solo una volta raggiunto l'idle plateau autorizza la partenza del test.

---

## 3. Matrice delle Configurazioni di Test

Lo stress test termico valuta le 3 macro-configurazioni architetturali della pipeline a frequenza nominale di **2400 MHz** (governor `performance`):

| ID Config | Descrizione Architetturale | `enable_enhancement` | `enable_detection` | Modello Impiegato | `imgsz` | Durata |
| :--- | :--- | :---: | :---: | :--- | :---: | :---: |
| `T_baseline` | Solo acquisizione stereo (camera_node) | `false` | `false` | — | 640 | 3600 s (1h) |
| `T_detection` | Acquisizione camera + Detection OpenVINO FP32 | `false` | `true` | `yolov8n_640_fp32_openvino_model` | 640 | 3600 s (1h) |
| `T_full` | Pipeline completa (Camera + Enhancement + Detection) | `true` | `true` | `yolov8n_640_fp32_openvino_model` | 640 | 3600 s (1h) |

### Note sui Parametri

- **`T_baseline`**: Rappresenta il consumo energetico e termico minimo dell'hardware video (`camera_ros` a 5 FPS nominali).
- **`T_detection`**: Utilizza il modello di riferimento emerso vincente dalla Fase 6 (`yolov8n_640_fp32_openvino_model`) con `half_res:=false` e input `raw`. È il profilo di carico computazionale massimo continuo sulla CPU per la sola detection.
- **`T_full`**: Attiva `enhancement_node` (Laplacian + CLAHE deterministico) con input reindirizzato su `enhanced` per quantificare il carico combinato di elaborazione immagini e inferenza.

---

## 4. Wrapper di Automazione (`run_thermal_test.sh`)

Lo script `benchmarks/run_thermal_test.sh` standardizza l'intero protocollo sperimentale della Fase 7:

```bash
cd ~/nautilus-vision-pipeline
./benchmarks/run_thermal_test.sh <CONFIG> <RUN_N> [DURATION_SECONDS]
# Esempi:
# ./benchmarks/run_thermal_test.sh T_baseline 1 3600
# ./benchmarks/run_thermal_test.sh T_detection 1 3600
# ./benchmarks/run_thermal_test.sh T_full 1 3600
```

Se omesso, il parametro `DURATION_SECONDS` assume il valore di default di **3600** (1 ora).

### Fasi Operative Eseguite dal Wrapper

1. **Validazione Parametri**: Controllo di congruità degli argomenti e del tempo di test.
2. **Arresto Servizi & Cleanup**: Pulizia completa dei nodi camera residui e riavvio del daemon ROS 2.
3. **CPU Governor**: Impostazione automatica su `performance` su tutti i core CPU.
4. **Attesa Stabilità Termica Iniziale**: Ciclo di polling a riposo fino al plateau $\Delta T \le 1\text{ }^\circ\text{C}$.
5. **Hardware Unlock & Launch**:
   - Rilascio dei device video con `sudo fuser -k -9 /dev/video0 /dev/video1`.
   - Lancio in background di `ros2 launch nautilus_perception pipeline.launch.py` con `enable_metrics:=true` e `enable_debug:=false`.
   - Esecuzione di `deploy/lock_cameras.py` dopo 5 s per fissare l'esposizione.
6. **Warmup di 30 s**: Stabilizzazione dei flussi di pubblicazione ROS 2.
7. **Esecuzione dello Stress Test**:
   - Avvio di `benchmarks/scripts/thermal_stress_test.py` per l'esatta durata richiesta.
   - Sottoscrizione a `/stereo_down/timings` attiva per le configurazioni con detection.
8. **Terminazione e Pulizia**: Arresto del processo di launch e kill forzato dei nodi (`kill -9`).
9. **Salvataggio Metadati**: Creazione del file `<DATE>_<CONFIG>_run<N>_metadata.csv` contenente commit Git, temperature di inizio/fine, frequenze e flag di throttling.
10. **Cooldown Automatico Post-Test**: Ciclo di attesa attiva (fino a 15 minuti) fino a quando la temperatura del SoC non torna a stabilizzarsi a riposo prima di autorizzare la run successiva.

---

## 5. Script di Monitoraggio Telemetrico (`thermal_stress_test.py`)

A differenza della Fase 6 (che impiegava due script separati per risorse e latenza), la Fase 7 impiega `benchmarks/scripts/thermal_stress_test.py` come **osservatore unico unificato**:

- È un nodo ROS 2 (`ThermalMonitor`) a basso impatto computazionale che sottoscrive i topic in modalità `BEST_EFFORT` per non introdurre latenza o ritardi artificiali.
- Esegue un loop sincrono a **1 Hz** e salva un unico file CSV (`*_thermal.csv`) con una riga per ogni secondo di test.

### Colonne Registrate nel File CSV

- `t_iso`: Timestamp ISO-8601 del campione
- `t_elapsed_s`: Secondi trascorsi dall'inizio del test
- `temp_c`: Temperatura istantanea del SoC in °C (`vcgencmd measure_temp`)
- `clock_mhz`: Frequenza effettiva della CPU ARM in MHz (`vcgencmd measure_clock arm`)
- `throttled`: Registro flag di throttling in esadecimale (`vcgencmd get_throttled`)
- `cpu_pct`: Utilizzo percentuale aggregato dei 4 core CPU (`psutil.cpu_percent`)
- `ram_pct`: Utilizzo percentuale della memoria RAM di sistema (`psutil.virtual_memory`)
- `jitter_ms`: Jitter temporale inter-frame sul flusso raw della telecamera sinistra
- `pre_ms_mean`: Tempo medio di pre-processing (ms) nell'ultimo secondo da `/stereo_down/timings`
- `infer_ms_mean`: Tempo medio di inferenza YOLO (ms) nell'ultimo secondo
- `post_ms_mean`: Tempo medio di post-processing stereo (ms) nell'ultimo secondo
- `fps_/stereo/lx/camera/image_raw`: Throughput istantaneo camera raw sinistra
- `fps_/stereo/rx/camera/image_raw`: Throughput istantaneo camera raw destra
- `fps_/stereo/lx/image_enhanced`: Throughput istantaneo immagini migliorate
- `fps_/stereo/rx/image_enhanced`: Throughput istantaneo immagini migliorate destra
- `fps_/stereo_down/targets`: Throughput effettivo delle predizioni e coordinate 3D

---

## 6. Generazione dei Grafici (`plot_results_thermal.py`)

Lo script `benchmarks/scripts/plot_results_thermal.py` elabora i log da 3600 campioni ciascuno e genera i grafici comparativi salvandoli in `benchmarks/thermal_results/plots/`:

```bash
python3 benchmarks/scripts/plot_results_thermal.py \
    --csv benchmarks/thermal_results/csv/ \
    --out benchmarks/thermal_results/plots/
```

### Grafici Prodotti

1. `01_soc_temp.png`: Andamento continuo della temperatura del SoC (°C) durante l'ora di test per le 3 configurazioni.
2. `02_cpu_usage.png`: Profilo temporale di carico CPU con media mobile su finestra di 30 secondi per smussare i picchi istantanei.
3. `03_ram_usage.png`: Andamento dell'occupazione percentuale della RAM per evidenziare eventuali memory leak.
4. `04_fps_comparison.png`: Throughput medio effettivo (FPS) a confronto sui canali Raw, Enhanced e Targets rispetto alla linea nominale dei 5 FPS.
5. `05_latency_stages.png`: Istogramma a barre impilate con scomposizione media della latenza (`pre`, `infer`, `post`) per `T_detection` e `T_full`.

---

## 7. Verifica dei Flag di Throttling

Come per la Fase 6, la validità del test termico richiede la totale assenza di interventi del governor di protezione termica o sottotensione:

- Il valore `throttled` deve risultare costantemente uguale a `0x0`.
- Se nel CSV o nel metadata finale compare uno dei bit di evento (`0x10000`, `0x20000`, `0x40000`, `0x80000`), il test segnala una condizione termica o di alimentazione instabile.
- Nelle misurazioni effettuate, tutte e 3 le configurazioni hanno mantenuto rigorosamente `throttled = 0x0` per tutti i 3600 secondi.
