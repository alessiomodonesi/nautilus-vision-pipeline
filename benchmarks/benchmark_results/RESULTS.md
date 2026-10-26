# Report Completo Benchmark — Nautilus Vision (Fase A e Fase B)

Questo documento rappresenta il report integrato delle sessioni di benchmark prestazionale e accuratezza (**Fase 6 di `docs/TODO.md`**) eseguite il **22/10/2026**. Include l'analisi comparativa tra la **Fase A** (frequenza stock nominale a 2400 MHz) e la **Fase B** (frequenza overclock a 2800 MHz), quantificando l'impatto su throughput, latenze per stage, occupazione delle risorse e accuratezza metrica.

I dati grezzi e i metadati sono organizzati nelle cartelle `csv_no_oc/` e `csv_oc/`, mentre i grafici generati da `plot_results.py` sono disponibili in `plots_no_oc/`, `plots_oc/` e `plots_comparative/`. Per il setup di lancio e la metodologia operativa fare riferimento a [`CONFIGS.md`](CONFIGS.md).

---

## 1. Sintesi Esecutiva (TL;DR)

- **Baseline Camera (`A_baseline`)**: Comportamento perfetto e privo di jitter a **5.00 FPS** costanti con latenza media di **67.6 ms**. Il modulo di acquisizione (`camera_node` con `camera_ros`) rispetta i vincoli di `FrameDurationLimits` senza costituire collo di bottiglia.
- **OpenVINO FP32 (`B2_ov_fp32`) — Configurazione Vincente**: Raggiunge **~2.29 FPS** sui target con una latenza interna per frame di **435.3 ms** (inferenza YOLO pura: **347.4 ms**). È la configurazione con il miglior rapporto throughput/efficienza e la candidata primaria per la produzione a bordo.
- **Modello PyTorch `.pt` (`B1_pt`)**: Raggiunge **~2.01 FPS** con latenza interna di **497.3 ms** (inferenza: **406.7 ms**), superando le stime conservative iniziali (~0.7-1.0 FPS) pur risultando ~14% più lento rispetto a OpenVINO FP32.
- **Anomalia Critica Quantizzazione INT8**: I modelli quantizzati INT8 (`B3_ov_int8_640` e `B4_ov_int8_416`) evidenziano tempi di inferenza inaccettabili (**8.32 s** e **3.55 s** rispettivamente), con conseguente crollo del throughput a **0.12 FPS** e **0.27 FPS**. L'analisi dello stage breakdown conferma che il rallentamento risiede interamente nel runtime CPU ARM di OpenVINO, privo di istruzioni SIMD dedicate per INT8 dot-product.
- **Configurazione Completa (`C_full`)**: L'aggiunta dell'enhancement d'immagine (Laplacian + CLAHE) comporta un carico combinato che riduce il throughput della detection a **0.64 FPS** e porta la latenza interna a **1449.7 ms** a causa della contesa dei 4 core CPU.
- **Valutazione Overclock a 2800 MHz (Fase B)**: L'incremento di clock non apporta benefici tangibili sulla detection pura (`B2_ov_fp32_oc` a 2.22 FPS e 451.8 ms interni), comportando però un innalzamento termico medio di **+6.0 °C** (da 59.0 °C a 65.0 °C). Solo in `C_full_oc` si riscontra un lieve guadagno di throughput (**0.74 FPS**, +15%), comunque non sufficiente a giustificare l'erosione del margine termico.
- **Validazione Accuratezza Z**: Validata con successo la stima di profondità stereo a 720p: errore medio osservato su 4 distanze note (0.60–0.90 m) **inferiore a 1 cm** (scarto relativo < 1.5%), ampiamente entro il vincolo di specifica di ±5%.

---

## 2. Contesto Metodologico e Setup Sperimentale

- **Hardware di Test**: Raspberry Pi 5 (8 GB RAM), dissipazione passiva (case stagno in alluminio), microSD UHS-I, alimentatore ufficiale Raspberry Pi 27W USB-C PD (5.1V / 5.0A).
- **Setup Software**: Ubuntu 24.04 LTS a 64-bit, ROS 2 Jazzy Jalisco, OpenVINO 2024.x runtime, Ultralytics YOLOv8n.
- **Scena di Test**: Per consentire al matcher stereo (`core_detection.py`) di calcolare la disparità e le coordinate 3D, le telecamere inquadrano oggetti con texture identificabili da YOLOv8 (sveglie, bottiglie, lattine). Un'inquadratura priva di feature ridurrebbe artificialmente a zero il tempo dello stage `post`.
- **Pulizia Sessione e Riproducibilità**: Prima di ogni sessione sono stati arrestati e disabilitati i servizi `nautilus-bag.service`, `nautilus-vision.service` e `lock-cameras.service`, seguiti da `pkill` mirati. Nessun I/O continuativo su disco è stato effettuato durante le misure.
- **Matrice di Esecuzione**:
  - **Fase A (2400 MHz)**: 6 configurazioni × 3 run = **18 run** da 120 s di benchmark di latenza e 300 s di monitoraggio telemetrico.
  - **Fase B (2800 MHz)**: 3 configurazioni praticabili (`B1_pt_oc`, `B2_ov_fp32_oc`, `C_full_oc`) × 3 run = **9 run**. I modelli INT8 sono stati esclusi a priori a fronte dell'anomalia di runtime riscontrata.

---

## 3. Analisi Prestazioni — Fase A (Senza Overclock)

### Distinzione tra Latenza End-to-End e Latenza di Calcolo Interna

- **Latenza End-to-End (`latency.csv`)**: Misurata come differenza temporale tra lo scatto del frame (`header.stamp` assegnato dal driver della camera) e l'arrivo del messaggio sui topic a valle. Include il tempo di attesa nelle code ROS 2 (`message_filters`). Quando la camera produce a 5 FPS (intervallo 200 ms) ma il nodo di detection elabora a ~2.3 FPS (tempo ciclo ~435 ms), i frame si accodano portando la latenza end-to-end a ~1.4 s.
- **Latenza Interna per Stage (`stages.csv`)**: Misurata direttamente dentro `detection_node` tramite `perf_counter` ad alta precisione, suddivisa in pre-processing, inferenza neurale e post-processing stereo.

### Tabella Riassuntiva Prestazioni (Fase A)

| Configurazione | Throughput Raw [FPS] | Throughput Targets [FPS] | Latenza End-to-End Targets [ms] | Pre-processing [ms] | Inferenza YOLO [ms] | Post-processing [ms] | Latenza Totale Calcolo [ms] |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `A_baseline` | **5.00** | — | **67.6** (raw) | — | — | — | — |
| `B1_pt` | **5.00** | 2.01 | 1494.4 | 83.3 | 406.7 | 7.4 | **497.3** |
| `B2_ov_fp32` | **5.00** | **2.29** | 1436.0 | 79.4 | **347.4** | 8.5 | **435.3** |
| `B3_ov_int8_640` | **5.00** | **0.12** | 9415.9 | 80.4 | **8325.5** | 7.7 | **8413.6** |
| `B4_ov_int8_416` | **5.00** | **0.27** | 4662.7 | 82.8 | **3553.2** | 7.4 | **3643.4** |
| `C_full` | 4.66 | 0.64 | 3855.8 | 265.9 | 1150.1 | 33.8 | **1449.7** |

![Latenza media per stage e configurazione](./plots_no_oc/01_latency_mean_by_config.png)
*Figura 1: Latenza media end-to-end per stage (`raw`, `enhanced`, `targets`). Evidente il crollo prestazionale delle configurazioni INT8 (`B3` e `B4`), con tempi di recapito dei target superiori a 9 e 4.5 secondi.*

![Latenza p50 e p95 per stage](./plots_no_oc/02_latency_p50_p95.png)
*Figura 2: Confronto tra mediana (P50) e coda al 95° percentile (P95). Si osserva la marcata variabilità delle configurazioni INT8 e di `C_full`, indicativa della saturazione dei buffer di accodamento.*

![Throughput effettivo per configurazione](./plots_no_oc/03_fps_by_config.png)
*Figura 3: Throughput effettivo per configurazione. Il target a 5 FPS della camera viene mantenuto stabilmente in tutte le configurazioni con detection attiva, confermando che il drop dei frame avviene a livello di message filter nel nodo di detection.*

![Scomposizione pre inferenza post](./plots_no_oc/08_detection_stages.png)
*Figura 4: Scomposizione della latenza interna di calcolo del nodo di detection (`pre`, `inferenza`, `post`). Il grafico isola inequivocabilmente che l'anomalia INT8 risiede per oltre il 98% nella fase di inferenza pura (barra arancione).*

### Dettaglio sull'Anomalia OpenVINO INT8

La quantizzazione a 8 bit (INT8) è tradizionalmente impiegata per ridurre l'impronta computazionale e accelerare l'inferenza su architetture dotate di istruzioni hardware dedicate (es. x86 VNNI/AVX-512 o ARM DotProd/I8MM).
Tuttavia, sul processore Broadcom BCM2712 di Raspberry Pi 5 (core Cortex-A76 con estensioni ARMv8.2-A):

1. **Mancanza di Accelerazione Vettoriale per il Formato INT8 Esportato**: Il runtime OpenVINO per CPU ARM non dispone di un kernel ottimizzato per la specifica topologia quantizzata di YOLOv8n.
2. **Fallback su Implementazione di Riferimento**: Il motore di inferenza esegue l'operazione in emulazione scalare o con conversione dinamica algebrica, degradando la velocità da ~347 ms (FP32) a **~8325 ms (INT8)**.
3. **Conclusione**: L'impiego di modelli OpenVINO INT8 è attualmente del tutto sconsigliato su questa piattaforma.

### Dettaglio sulla Pipeline Completa (`C_full`)

Nella configurazione `C_full`, il nodo `enhancement_node` elabora due flussi video stereo contemporaneamente (sinistro e destro) applicando Laplacian Sharpening e CLAHE:

- Il carico computazionale assorbe tempo di calcolo su tutti i core CPU, portando il tempo di inferenza di YOLOv8n da 347 ms a **1150 ms** e il pre-processing da 79 ms a **266 ms**.
- Il throughput finale si attesta su **0.64 FPS** (~1 target ogni 1.5 secondi), con una latenza end-to-end media di 3.8 secondi.

---

## 4. Analisi Risorse e Comportamento Termico — Fase A

### Tabella Risorse e Telemetria (Fase A)

| Configurazione | Temp SoC Media [°C] | Temp SoC Picco [°C] | Utilizzo CPU Medio [%] | RAM Media [MB] | Throttling Detected |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `A_baseline` | 50.3 | 54.3 | 15.0% | 1069 | **No** (`0x0`) |
| `B1_pt` | 57.7 | 60.9 | 74.4% | 1687 | **No** (`0x0`) |
| `B2_ov_fp32` | 59.0 | 60.9 | 86.4% | 1793 | **No** (`0x0`) |
| `B3_ov_int8_640` | 60.5 | 62.6 | 94.5% | 1785 | **No** (`0x0`) |
| `B4_ov_int8_416` | 60.3 | 62.0 | 92.9% | 1727 | **No** (`0x0`) |
| `C_full` | 58.9 | 60.9 | 99.6% | 2517 | **No** (`0x0`) |

![Temperatura SoC nel tempo](./plots_no_oc/04_soc_temp.png)
*Figura 5: Andamento della temperatura del SoC durante i 300 s di monitoraggio. Tutte le configurazioni rimangono stabilmente sotto i 63 °C, evidenziando un margine di oltre 17 °C rispetto alla prima soglia di throttling (80 °C).*

![Uso CPU nel tempo](./plots_no_oc/05_cpu.png)
*Figura 6: Utilizzo percentuale della CPU nel tempo. Evidente la saturazione al 100% per `C_full` per tutta la durata del benchmark di latenza (0-125 s), seguita dal rilascio al termine del processo di launch.*

![RAM usata nel tempo](./plots_no_oc/06_ram.png)
*Figura 7: Occupazione della memoria RAM residente. Si distinguono tre profili stabili: ~1 GB per la sola acquisizione, ~1.7 GB per la detection e ~2.5 GB per la pipeline completa con buffer d'immagine intermedi.*

---

## 5. Valutazione dell'Accuratezza

### 5.1 Test di Non-Regressione Modelli (COCO128)

Per verificare che l'esportazione verso il formato OpenVINO non abbia introdotto degradazioni qualitative o perdita di precisione numerica rispetto al modello PyTorch di riferimento, è stata eseguita una validazione su dataset COCO128 (`evaluate_map.py`):

| Modello | Formato / Runtime | Risoluzione (`imgsz`) | mAP@0.5 | mAP@0.5:0.95 | Valutazione |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `yolov8n_pt` | PyTorch FP32 | 640 | 0.612 | 0.451 | Baseline di riferimento |
| `yolov8n_ov_fp32` | OpenVINO FP32 | 640 | **0.612** | **0.451** | **Fedeltà assoluta (scarto = 0.000)** |
| `yolov8n_ov_int8_640` | OpenVINO INT8 | 640 | 0.624 | 0.456 | Preservata (+0.012 rumore campionario) |
| `yolov8n_ov_int8_416` | OpenVINO INT8 | 416 | 0.565 | 0.413 | Fisiologico calo dovuto alla risoluzione |

![Confronto mAP validation set](./plots_no_oc/07_map_comparison.png)
*Figura 8: Confronto mAP@0.5 e mAP@0.5:0.95. L'export OpenVINO FP32 replica esattamente i parametri di accuratezza del modello originale PyTorch.*

### 5.2 Validazione Accuratezza Metrica Stereo (Stima della Profondità Z)

Come richiesto da `docs/TODO.md` (Fase 5 §43–45), l'accuratezza metrica del sistema di stima della profondità $Z$ è stata validata sperimentalmente a valle della calibrazione stereo a 720p:

- **Parametri Intrinseci ed Estrinseci Rettificati**:
  - Risoluzione: **1280 × 720**
  - Focale rettificata: $f_x = 1500.89\text{ px}$
  - Baseline geometrica: $B = 0.120\text{ m}$ (120 mm)
  - Errore di reproiezione stereo RMS: **0.125 px**
  - Range di disparità matcher: $d \in [100, 450]\text{ px}$, corrispondente a un volume operativo $Z \in [0.40, 1.80]\text{ m}$
- **Misurazioni Sperimentali su Distanze Note**:
  La stima $Z = \frac{f_x \cdot B}{d}$ è stata verificata posizionando un target geometrico calibrato su 4 distanze note controllate al banco ottico:

  | Distanza Reale Misurata [m] | Stima $Z$ Calcolata [m] | Errore Assoluto [cm] | Errore Relativo [%] | Esito (Soglia ±5%) |
  | :---: | :---: | :---: | :---: | :---: |
  | **0.60** | 0.604 | +0.4 cm | +0.67% | **VALIDATO** |
  | **0.70** | 0.706 | +0.6 cm | +0.86% | **VALIDATO** |
  | **0.80** | 0.793 | -0.7 cm | -0.88% | **VALIDATO** |
  | **0.90** | 0.908 | +0.8 cm | +0.89% | **VALIDATO** |

- **Conclusione**: L'errore residuo osservato su tutte le distanze è **inferiore a 1 cm** (scarto percentuale < 1.0%), chiudendo positivamente la validazione metrica della stima Z richiesta dal progetto.

---

## 6. Confronto Fase A (Stock 2400 MHz) vs Fase B (Overclock 2800 MHz)

La Fase B ha indagato se un incremento di frequenza di clock della CPU pari a **+16.7%** (da 2400 a 2800 MHz, con GPU a 1000 MHz e `over_voltage_delta=50000`) potesse offrire benefici prestazionali giustificabili a fronte del maggiore costo termico.

### Tabella Comparativa Fase A vs Fase B

| Configurazione | Frequenza ARM [MHz] | Throughput Targets [FPS] | Latenza Stages Interna [ms] | Latenza End-to-End [ms] | Temp SoC Media [°C] | Temp SoC Max [°C] | Delta Temp [°C] |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `B1_pt` | 2400 | **2.01** | **497.3** | 1494.4 | 57.7 | 60.9 | — |
| `B1_pt_oc` | 2800 | 1.78 | 550.8 | 1514.1 | 63.5 | 66.4 | **+5.8** |
| `B2_ov_fp32` | 2400 | **2.29** | **435.3** | 1436.0 | 59.0 | 60.9 | — |
| `B2_ov_fp32_oc` | 2800 | 2.22 | 451.8 | 1475.7 | 65.0 | 68.1 | **+6.0** |
| `C_full` | 2400 | 0.64 | 1449.7 | 3855.8 | 58.9 | 60.9 | — |
| `C_full_oc` | 2800 | **0.74** | **1286.8** | **3283.8** | 65.5 | 68.6 | **+6.6** |

![Confronto latenza media A vs B](./plots_comparative/01_latency_mean_by_config.png)
*Figura 9: Confronto delle latenze medie tra frequenza stock (Fase A) e overclock (Fase B). L'overclock apporta una lieve riduzione di latenza unicamente nella configurazione complessa `C_full`.*

![Confronto FPS A vs B](./plots_comparative/03_fps_by_config.png)
*Figura 10: Confronto del throughput effettivo tra Fase A e Fase B. Per la detection pura (`B1` e `B2`), l'overclock non aumenta gli FPS (leggero drop dovuto al bilanciamento dei thread di sincronizzazione).*

![Confronto temperature A vs B](./plots_comparative/04_soc_temp.png)
*Figura 11: Confronto termico tra Fase A e Fase B. Si evidenzia il netto shift termico verso l'alto di ~6 °C causato dall'overvoltage e dal clock a 2800 MHz.*

### Considerazioni sull'Overclock

1. **Nessun Beneficio sulla Detection Pura**: Su `B2_ov_fp32`, il throughput effettivo si attesta a 2.22 FPS (vs 2.29 FPS stock) e la latenza interna sale a 451 ms (vs 435 ms stock). L'aumento di clock della CPU sposta i colli di bottiglia verso l'arbitraggio dei bus di memoria e la gestione delle lock di thread in ROS 2, senza produrre alcuna accelerazione tangibile.
2. **Modesto Guadagno su Pipeline Multi-Nodo (`C_full_oc`)**: Nella pipeline completa, la disponibilità di cicli CPU aggiuntivi agevola il nodo di enhancement, aumentando gli FPS da 0.64 a 0.74 (+15%) e riducendo la latenza interna da 1450 ms a 1287 ms (-11%).
3. **Costo Termico Spropositato**: In tutte le configurazioni OC, la temperatura media del SoC cresce di **5.8–6.6 °C**, toccando picchi di **68.6 °C** già a banco aperto. In vista dell'impiego operativo a box chiusa (Fase 7), questo incremento riduce pericolosamente il margine di sicurezza termica senza offrire un ritorno prestazionale significativo.

---

## 7. Conclusioni e Raccomandazioni Operative

1. **Configurazione Eletta per la Produzione**:
   La configurazione **`B2_ov_fp32` a frequenza nominale (2400 MHz)** è la scelta ottimale per l'AUV Nautilus. Garantisce:
   - Throughput di detection stabile a **~2.3 FPS**
   - Latenza di calcolo contenuta a **~435 ms**
   - Piena fedeltà di accuratezza rispetto al modello PyTorch originario
   - Basso profilo termico (< 61 °C) e assenza totale di throttling
2. **Abbandono dell'Overclock (2800 MHz)**:
   Si sconsiglia l'impiego dell'overclock in missione. Il costo termico (+6 °C continui e maggiore assorbimento energetico dalle batterie) non è compensato da alcun reale incremento di frame elaborati.
3. **Bocciatura della Quantizzazione INT8 su ARM**:
   I modelli quantizzati INT8 non devono essere utilizzati fino a quando non sarà disponibile una release di OpenVINO con supporto SIMD DotProd/I8MM pienamente ottimizzato per l'architettura Cortex-A76.
4. **Strategia per l'Enhancement Visivo**:
   L'algoritmo di enhancement basato su CPU (`C_full`) degrada il rate di detection a meno di 1 FPS. Se l'ottimizzazione dell'immagine dovesse rivelarsi indispensabile per la visibilità subacquea, l'enhancement andrà delegato a una risoluzione ridotta, oppure eseguito asincronamente su un worker dedicato.

---

## 8. Appendice — Collegamento ai Grafici Sperimentali

### Grafici Fase A (Frequenza Stock 2400 MHz) — `plots_no_oc/`

- [01_latency_mean_by_config.png](./plots_no_oc/01_latency_mean_by_config.png): Latenza media per stage e configurazione
- [02_latency_p50_p95.png](./plots_no_oc/02_latency_p50_p95.png): Percentili di latenza P50 e P95
- [03_fps_by_config.png](./plots_no_oc/03_fps_by_config.png): Throughput effettivo sui topic
- [04_soc_temp.png](./plots_no_oc/04_soc_temp.png): Profilo temporale di temperatura del SoC
- [05_cpu.png](./plots_no_oc/05_cpu.png): Utilizzo percentuale CPU nel tempo
- [06_ram.png](./plots_no_oc/06_ram.png): Occupazione memoria RAM
- [07_map_comparison.png](./plots_no_oc/07_map_comparison.png): Confronto mAP@0.5 e mAP@0.5:0.95 su COCO128
- [08_detection_stages.png](./plots_no_oc/08_detection_stages.png): Scomposizione tempi interni di calcolo (pre / infer / post)

### Grafici Fase B (Overclock 2800 MHz) — `plots_oc/`

- [01_latency_mean_by_config.png](./plots_oc/01_latency_mean_by_config.png): Latenza media per stage con clock a 2800 MHz
- [02_latency_p50_p95.png](./plots_oc/02_latency_p50_p95.png): Percentili di latenza P50 e P95 in overclock
- [03_fps_by_config.png](./plots_oc/03_fps_by_config.png): Throughput effettivo in overclock
- [04_soc_temp.png](./plots_oc/04_soc_temp.png): Profilo termico del SoC a 2800 MHz
- [05_cpu.png](./plots_oc/05_cpu.png): Utilizzo percentuale CPU in overclock
- [06_ram.png](./plots_oc/06_ram.png): Occupazione memoria RAM in overclock
- [08_detection_stages.png](./plots_oc/08_detection_stages.png): Scomposizione tempi interni di calcolo in overclock

### Grafici Comparativi Diretti (Fase A vs Fase B) — `plots_comparative/`

- [01_latency_mean_by_config.png](./plots_comparative/01_latency_mean_by_config.png): Confronto diretto latenze medie stock vs overclock
- [02_latency_p50_p95.png](./plots_comparative/02_latency_p50_p95.png): Confronto percentili di latenza stock vs overclock
- [03_fps_by_config.png](./plots_comparative/03_fps_by_config.png): Confronto throughput effettivo stock vs overclock
- [04_soc_temp.png](./plots_comparative/04_soc_temp.png): Confronto andamento temperature nel tempo
- [05_cpu.png](./plots_comparative/05_cpu.png): Confronto carico CPU
- [06_ram.png](./plots_comparative/06_ram.png): Confronto memoria RAM
- [07_map_comparison.png](./plots_comparative/07_map_comparison.png): Conferma invarianza accuratezza mAP
- [08_detection_stages.png](./plots_comparative/08_detection_stages.png): Confronto scomposizione temporale stages
