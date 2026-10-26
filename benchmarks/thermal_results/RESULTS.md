# Report Completo Benchmark Termico (1 Ora) — Nautilus Vision

Questo documento rappresenta il report integrato delle sessioni di stress test termico ad alta durata (**Fase 7 di `docs/TODO.md`**), eseguite il **26/10/2026** per una durata di **60 minuti continui (3600 secondi)** per ciascuna configurazione.
L'obiettivo primario è validare la stabilità termica, l'assenza di thermal throttling, l'impegno delle risorse (CPU e RAM) e la costanza del throughput prestazionale della pipeline **Nautilus Vision** su Raspberry Pi 5 all'interno dello scafo stagno a dissipazione puramente passiva.

I dati telemetrici grezzi a frequenza di 1 Hz sono archiviati nella cartella `csv/` (`*_thermal.csv`), mentre i grafici generati da `plot_results_thermal.py` sono disponibili nella cartella `plots/`. Per il setup di lancio e la metodologia operativa vedi [`CONFIGS.md`](CONFIGS.md). Per il confronto con i test prestazionali di Fase 6 vedi [`../benchmark_results/RESULTS.md`](../benchmark_results/RESULTS.md).

---

## 1. Sintesi Esecutiva (TL;DR)

- **Stabilità Termica Assoluta**: **Nessuna configurazione ha causato throttling termico (`get_throttled = 0x0`)**. Il picco massimo registrato sul SoC durante l'intera prova è stato di **69.70 °C** sotto carico massimo di detection (`T_detection`), garantendo oltre **10 °C di margine di sicurezza** rispetto alla soglia di attivazione del soft throttling di Raspberry Pi 5 (80 °C).
- **Risposta al Quesito Progettuale ("La detection può restare sul Pi a box chiusa?")**: **SÌ**. La configurazione con sola detection OpenVINO FP32 (`T_detection`) è pienamente sostenibile a regime continuo, erogando **1.40 FPS** stabili sui target con una latenza di calcolo per frame di **~698 ms**.
- **Baseline di Acquisizione (`T_baseline`)**: Funzionamento impeccabile a **5.00 FPS** costanti. Carico CPU medio ridotto al **29.58%** e temperatura stabilizzata a regime su una media di **56.80 °C** (picco massimo 60.90 °C).
- **Comportamento della Pipeline Completa (`T_full`)**: Mostra una dinamica a due regimi. Nei primi 500 secondi la CPU lavora a saturazione (100%), portando la temperatura a 65.3 °C; successivamente, l'accodamento dei frame e la contesa delle risorse tra l'enhancement stereo e l'inferenza introducono una forte backpressure software in ROS 2, riducendo la CPU al **~42%** e il throughput di detection a **0.08 FPS** (temperatura media a regime **61.07 °C**).
- **Integrità della Memoria (Zero Memory Leak)**: Il profilo di occupazione della RAM rimane perfettamente piatto per tutte le 3 ore complessive di prova, con picco massimo a regime di **32.22%** (~2.58 GB su 8 GB disponibili) per `T_full`.

---

## 2. Contesto Metodologico e Setup Sperimentale

Lo stress test termico simula le condizioni operative reali a bordo dell'AUV Nautilus durante una missione subacquea prolungata:

- **Configurazioni Testate (Clock Nominale 2400 MHz)**:
  1. `T_baseline`: Acquisizione stereo pura a 5 FPS nominali (nessuna elaborazione a valle).
  2. `T_detection`: Acquisizione camera stereo + detection YOLOv8n OpenVINO FP32 a 640px.
  3. `T_full`: Pipeline completa (Acquisizione + Enhancement Laplacian/CLAHE + Detection).
- **Durata e Campionamento**: 3.600 secondi continui per ciascuna configurazione, con campionamento telemetrico sincronizzato a frequenza fissa di **1 Hz** mediante `benchmarks/scripts/thermal_stress_test.py`.
- **Condizioni Ambientali**: Raspberry Pi 5 alloggiato nel case stagno in alluminio, sigillato, dissipazione termica puramente conduttiva/passiva verso la scocca metallica (nessuna ventola attiva), temperatura ambiente al banco ~21 °C.
- **Parametri Tracciati**: Temperatura del SoC (°C via `vcgencmd`), frequenza CPU ARM, flag di throttling (`vcgencmd get_throttled`), carico percentuale CPU aggregato (`psutil`), occupazione memoria RAM, FPS per ciascun topic ROS 2 e tempi medi di pre-processing, inferenza e post-processing ricavati da `/stereo_down/timings`.

---

## 3. Analisi Termica e Comportamento delle Risorse

### Tabella Riassuntiva Risorse e Termica (Media su 1 Ora di Test)

| Configurazione | Temp. Media [°C] | Temp. Picco [°C] | Temp. Min Iniziale [°C] | Uso CPU Medio [%] | Uso RAM Medio [%] | Throttling Detected |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `T_baseline` | 56.80 | 60.90 | 42.20 | 29.58% | 14.36% (~1.15 GB) | **No** (`0x0`) |
| `T_detection` | **65.40** | **69.70** | 43.30 | **93.56%** | 22.87% (~1.83 GB) | **No** (`0x0`) |
| `T_full` | 61.07 | 65.30 | 46.10 | 50.12%* | **32.22%** (~2.58 GB) | **No** (`0x0`) |

*\*Nota: `T_full` impegna il 100% della CPU nei primi 500 s di transitorio; superata tale soglia, il carico medio scende a ~42% a causa della contesa software e del blocco dei buffer nelle code di sincronizzazione stereo.*

![Temperatura SoC nel tempo](./plots/01_soc_temp.png)
*Figura 1: Andamento della temperatura del SoC nei 60 minuti di test. Tutte le configurazioni mostrano un transitorio iniziale ripido (0-600 s) seguito da un plateau stazionario. `T_detection` (linea arancione) opera al regime termico più alto (~67-69 °C), mantenendosi stabilmente al di sotto della soglia di sicurezza.*

![Uso CPU nel tempo](./plots/02_cpu_usage.png)
*Figura 2: Profilo di utilizzo della CPU (media mobile a 30 secondi). Si evidenzia la saturazione continua al 93-96% di `T_detection`, a fronte del profilo costante al ~30% della baseline e della transizione a due regimi di `T_full` (100% nei primi 500 s, poi ~42%).*

![Uso RAM nel tempo](./plots/03_ram_usage.png)
*Figura 3: Occupazione della memoria RAM nel tempo. L'assoluta planarità delle curve conferma l'eccellente stabilità del software e l'assenza totale di leak di memoria o accumulo nei descrittori di file durante un'intera ora di funzionamento.*

---

## 4. Analisi Prestazioni — Throughput (FPS) e Latenza di Calcolo

Il monitoraggio telemetrico continuativo ha permesso di calcolare le medie di throughput reale e la scomposizione esatta dei tempi di calcolo a regime termico.

### Tabella Riassuntiva Prestazioni e Latenza

| Configurazione | Throughput Raw [FPS] | Throughput Enhanced [FPS] | Throughput Targets [FPS] | Latenza Pre [ms] | Inferenza YOLO [ms] | Latenza Post [ms] | Latenza Totale Calcolo [ms] |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `T_baseline` | **5.00** | — | — | — | — | — | — |
| `T_detection` | **5.00** | — | **1.40** | 107.26 | 578.37 | 12.81 | **698.45** |
| `T_full` | 0.38 | 0.33 | **0.08** | 270.40 | 1229.34 | 34.46 | **1534.20** |

![Throughput effettivo per configurazione](./plots/04_fps_comparison.png)
*Figura 4: Throughput effettivo medio sui topic principali rispetto alla linea target dei 5 FPS. `T_baseline` e `T_detection` sostengono i 5 FPS sul canale raw. Su `T_detection`, l'inferenza eroga 1.40 FPS sostenuti. Su `T_full` l'intero throughput crolla a causa del collo di bottiglia introdotto dal nodo di enhancement.*

![Scomposizione latenza per stage](./plots/05_latency_stages.png)
*Figura 5: Scomposizione della latenza interna per frame nei tre stadi (`pre`, `inferenza`, `post`). In `T_full` tutti gli stadi subiscono un forte degrado: il pre-processing sale a 270 ms e l'inferenza YOLO sale a 1229 ms a causa della contesa delle cache e dei core CPU con l'enhancement.*

---

## 5. Approfondimento dei Risultati Sperimentali

### 1. Dinamica Termica e Margine di Sicurezza a Regime

Il comportamento di dissipazione termica del box in alluminio passivo ha risposto pienamente alle aspettative progettuali:

- Nei primi 10 minuti di prova, la temperatura del SoC cresce rapidamente (gradiente $dT/dt \approx 2.5\text{ }^\circ\text{C/min}$), passando da ~43 °C a ~62 °C.
- Raggiunti i ~65 °C, il gradiente termico si appiattisce progressivamente grazie alla maggiore cessione di calore per conduzione verso l'alluminio dello scafo.
- Tra i 1.500 s e i 3.600 s, `T_detection` oscilla stabilmente nell'intervallo **67–69.7 °C**. Poiché il soft throttling del Pi 5 scatta a **80 °C**, il sistema dispone di un **margine termico residuo di oltre 10 °C**, sufficiente ad assorbire eventuali fluttuazioni della temperatura dell'acqua marina.

### 2. Meccanismo di Saturazione in `T_full`

Il comportamento di `T_full` evidenzia una criticità architetturale software ben precisa:

- **Transitorio (0–500 s)**: Il nodo di enhancement elabora entrambi i flussi stereo raw a piena frequenza, saturando tutti e 4 i core CPU (100%).
- **Regime Stazionario (> 500 s)**: La combinazione di enhancement sincrono e message synchronization stereo (`message_filters::ApproximateTimeSynchronizer`) genera un accumulo di frame nei buffer interni. Quando la frequenza di arrivo delle immagini supera la capacità di svuotamento dei nodi, le code ROS 2 si saturano, introducendo ritardi di schedulazione e context-switching continuo.
- **Esito**: Il rate di pubblicazione delle immagini raw crolla a 0.38 FPS, l'enhancement a 0.33 FPS e i target a 0.08 FPS (~1 rilevamento ogni 12.5 secondi). L'abbassamento della temperatura media a regime (61.07 °C vs 65.40 °C di `T_detection`) è la conseguenza diretta del fatto che i core rimangono in stallo in attesa dei buffer bloccati.

---

## 6. Conclusioni e Raccomandazioni Progettuali

1. **Promozione Definitiva dell'Hardware Raspberry Pi 5**:
   Il Raspberry Pi 5 all'interno dello scafo stagno in alluminio senza ventola supera con successo la prova di stabilità termica continua di 1 ora. Nessun evento di thermal throttling o calo di clock si è verificato.
2. **Architettura di Bordo Consigliata**:
   La configurazione **`T_detection` (Stereo Raw + YOLOv8n OpenVINO FP32)** è la candidata ideale e validata per le missioni operative di Nautilus. Garantisce:
   - Throughput continuo di **1.40 FPS** sui target
   - Latenza interna per frame **< 700 ms**
   - Temperatura del SoC **< 70 °C** (margine di sicurezza > 10 °C)
   - Stabilità di memoria assoluta (1.83 GB occupati, zero leak)
3. **Indicazioni per il Nodo di Enhancement**:
   La configurazione `T_full` non deve essere attivata in produzione nella formulazione attuale. Per integrare l'enhancement senza compromettere la detection si raccomanda di:
   - Ridurre la risoluzione di ingresso dell'enhancement (downsampling a 640x360).
   - Eseguire l'enhancement su un thread o processo disaccoppiato a frequenza ridotta (es. 1 FPS per il log visivo dei biologi), lasciando la detection alimentata direttamente dal flusso raw.

---

## 7. Appendice — Elenco dei Grafici Generati

Tutti i grafici generati da `plot_results_thermal.py` sono accessibili nella cartella [`plots/`](plots/):

- [01_soc_temp.png](./plots/01_soc_temp.png): Profilo temporale di temperatura del SoC per le 3 configurazioni durante la run di 1 ora
- [02_cpu_usage.png](./plots/02_cpu_usage.png): Profilo temporale dell'utilizzo CPU (%) con media mobile su 30 secondi
- [03_ram_usage.png](./plots/03_ram_usage.png): Profilo temporale dell'occupazione della memoria RAM (%)
- [04_fps_comparison.png](./plots/04_fps_comparison.png): Throughput effettivo medio in FPS a confronto sui principali topic
- [05_latency_stages.png](./plots/05_latency_stages.png): Scomposizione dettagliata della latenza di calcolo per stage (pre, inferenza, post)
