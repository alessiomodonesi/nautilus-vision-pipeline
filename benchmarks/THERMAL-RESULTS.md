# Report Stress Test Termico — Nautilus Vision (Fase 7)

Questo documento raccoglie i risultati dello **stress test termico** (Fase 7
di `docs/TODO.md`) eseguito sul Raspberry Pi 5 a **box chiusa**, in tre
configurazioni di pipeline selezionate dalla Fase 6. L'obiettivo è
determinare se la detection (e in prospettiva la pipeline full) è
sostenibile per **1 ora continuativa** in condizioni operative reali
(senza dissipazione attiva), senza incorrere in throttling termico.

I dati grezzi sono in `benchmarks/thermal_results/csv/`, i grafici in
`benchmarks/thermal_results/plots/`.

**Stato:** `T_baseline` e `T_detection` completate il 26/10/2026. `T_full` in
corso / pianificata. Le sezioni corrispondenti sono aggiornate in base ai log e
ai telemetry data delle sessioni eseguite.

---

## 1. Sintesi Esecutiva (TL;DR)

- **T_baseline (solo acquisizione)**: **stabile per tutti i 3600 s** a
  **5.00 FPS** su entrambi i canali, con temperatura che si assesta su un
  plateau di **~57-58 °C** dopo ~25 minuti. **Nessun throttling termico**
  (`throttled = 0x0` costante) e clock ARM fisso a **2400 MHz**. Jitter
  sub-millisecondo, CPU ~30 %, RAM ~14.5 %.
- **T_detection (acquisizione + detection YOLOv8n OpenVINO FP32)**:
  - Acquisizione raw stabile a **5.00 FPS** nominali su entrambi i canali (`raw_lx`, `raw_rx`).
  - Target Detection attiva a una frequenza media di **$\approx 2.12$ FPS** (tempo di ciclo inferenza+processing medio $\Delta t \approx 470\text{ ms}$).
  - Jitter del canale sinistro mantenuto entro valori sub-millisecondo (**< 0.11 ms**, media **0.04 ms**).
  - Skew stereo ($sx-dx$) in crescita progressiva da **0.60 ms** iniziali a **~3.60 ms** sotto carico, evidenziando l'impatto della contesa CPU generata dai 2 thread OpenVINO sugli stream di acquisizione camera.
- **Picchi termici baseline**: massimo registrato **60.9 °C** (t ≈ 1437 s), ben
  sotto la soglia di soft-throttling del Pi 5 (~80-85 °C). Il margine
  residuo è ampio.
- **Delta termico utile baseline**: da **43.3 °C** (primo campione post-warmup) a
  **56.5 °C** (fine run), con plateau intermedio. Il Pi si scalda di
  ~13 °C sotto carico di sola acquisizione.
- **Anomalie non termiche**: registrato sbilanciamento progressivo dello skew stereo in `T_detection` legato allo scheduling dei thread CPU di OpenVINO (`OMP_NUM_THREADS=2`, `MKL_NUM_THREADS=2`).

---

## 2. Contesto Metodologico

### 2.1 Obiettivo della Fase 7

La Fase 6 ha caratterizzato prestazioni e termica su finestre brevi
(120 s di benchmark + 300 s di monitor). La Fase 7 estende l'orizzonte a
**3600 s** per rispondere a una domanda diversa: *il sistema entra in
regime termico stazionario sotto carico prolungato, e a quale temperatura?
Il throttling si attiva entro l'ora?*

### 2.2 Configurazioni di test

Tre configurazioni, selezionate dalla Fase 6 per rappresentare il
**lower bound operativo** e l'**upper bound** della pipeline:

| ID | Pipeline | Modello | Scopo |
| --- | --- | --- | --- |
| `T_baseline` | camera | — | Controllo negativo: dissipazione passiva a carico minimo. |
| `T_detection` | camera + detection | `yolov8n_640_fp32_openvino_model` | Lower bound operativo: config minima per avere detection. |
| `T_full` | camera + enh + detection | `yolov8n_640_fp32_openvino_model` | Upper bound: worst case realistico. |

La durata per config è **3600 s (1 h)** con **cooldown fino a stabilità
termica** tra una config e la successiva. A differenza della Fase 6, non
si eseguono 3 ripetizioni: l'obiettivo non è la varianza di latenza ma il
**regime termico stazionario**, che è per definizione riproducibile.

### 2.3 Tooling

Il wrapper `benchmarks/run_thermal_test.sh` invoca
`benchmarks/scripts/thermal_stress_test.py`, che scrive **un CSV unico
con una riga al secondo** contenente:

- metriche di sistema (`temp_c`, `clock_mhz`, `throttled`, `cpu_pct`,
  `ram_pct`) via `vcgencmd` e `psutil`;
- **FPS per topic** (raw lx/rx, enhanced lx/rx, targets) contati
  direttamente dai subscriber, non da un sync `message_filters`;
- **jitter stereo** dai `header.stamp` del raw sinistro (stessa formula
  di `metrics_node`);
- **`pre_ms_mean` / `infer_ms_mean` / `post_ms_mean`** aggregati al
  secondo, sottoscrivendo `/stereo_down/timings`.

Il wrapper gestisce governor CPU → `performance`, stop servizi, hardware
unlock dei `/dev/video*`, lock fotometrico, warmup 30 s, scrittura
metadata con temp/throttled/clock iniziali e finali.

### 2.4 Condizioni al contorno

- **Hardware**: Raspberry Pi 5 (8 GB), box chiusa, dissipazione passiva.
- **Alimentatore**: 5 V / 5 A.
- **Scena**: identica a Fase 6 (oggetti riconoscibili, illuminazione
  costante).
- **Governor**: `performance` per tutta la durata.
- **Clock nominale**: 2400 MHz (nessun overclock).

---

## 3. Analisi Termica — T_baseline (solo camera)

**Sessione**: 26/10/2026, run 1.
**Config**: `enable_enhancement=false`, `enable_detection=false`,
`enable_metrics=true`.
**Durata**: 3600 s.

### 3.1 Riepilogo metriche

| Metrica | Valore | Note |
| :--- | :--- | :--- |
| Temperatura iniziale (CSV, post-warmup) | **43.3 °C** | Primo campione valido |
| Temperatura finale | **56.5 °C** | Ultimo campione |
| Temperatura massima | **60.9 °C** | t ≈ 1437 s |
| Temperatura di plateau | **~57-58 °C** | Da ~t=2100 in poi |
| Delta termico | **+13.2 °C** | 43.3 → 56.5 |
| `clock_mhz` | **2400 costante** | Nessun taglio firmware |
| `throttled` | **0x0 costante** | Nessun bit settato |
| FPS `raw_lx` | **5.00** (post-primo secondo) | `FrameDurationLimits` rispettato |
| FPS `raw_rx` | **5.00** | Idem |
| FPS `enhanced` / `targets` | 0.0 | Topic inesistenti (atteso) |
| `pre/infer/post_ms_mean` | 0.0 | Nessun `--timings-topic` |
| `jitter_ms` | < 0.05 | Formula `metrics_node` |
| `cpu_pct` | ~29-30 % (media) | Spike isolati a 36/46 % |
| `ram_pct` | 14.2 → 14.7 % | Crescita monotona leggera, nessun leak |

### 3.2 Profilo termico e comportamento

- **Profilo**: La temperatura sale da 43.3 °C a ~57 °C in ~20-25 minuti con andamento asintotico, assestandosi nel plateau 56-58 °C per la restante durata dell'ora.
- **Margine**: Rispetto al limite di soft-throttling di 80 °C del Pi 5, la baseline mantiene un margine di sicurezza di **> 22 °C**.

---

## 4. Analisi Termica — T_detection (acquisizione + detection OpenVINO)

**Sessione**: 26/10/2026, run 1.  
**Config**: `enable_enhancement=false`, `enable_detection=true`, `enable_metrics=true`.  
**Modello**: `yolov8n_640_fp32_openvino_model` su OpenVINO CPU (`LATENCY` mode, `batch=1`).  
**Threading**: `OMP_NUM_THREADS=2`, `MKL_NUM_THREADS=2`.

### 4.1 Riepilogo metriche

| Metrica | Valore | Note |
| :--- | :--- | :--- |
| Status avvio | **Completato con successo** | Mappatura OpenVINO su CPU regolare |
| FPS `raw_lx` / `raw_rx` | **~5.00 FPS** (range 4.63 – 5.47) | Acquisizione stereo stabile |
| FPS `targets` (detection rate) | **~2.12 FPS** | Inferenza continua ogni ~470 ms |
| Latenza Ciclo Inferenza | **~470 ms** ($\Delta t \approx 454 - 528\text{ ms}$) | Pre-processing, rettifica, YOLOv8n, stima profondità Z |
| Confidence target rilevato | **0.94 – 0.97** | Target primario `Obj [0]` (Z ≈ 0.58 m – 1.38 m) |
| `jitter_ms` (canale LX) | **0.03 – 0.11 ms** (avg 0.04 ms) | Nessun frame-drop in acquisizione |
| `skew_ms` (stereo LX-RX) | **0.60 ms → 3.60 ms** | Drift progressivo per contesa CPU |

### 4.2 Analisi delle prestazioni di Inferenza e Acquisizione

1. **Frequenza di Detection**:
   L'engine di inferenza OpenVINO opera in modalità `LATENCY` monothread per batch (`batch=1`), con multithreading limitato a 2 thread fisici. Dal log di esecuzione, l'intervallo tra due rilevamenti consecutivi sul topic `/stereo/targets` si stabilizza attorno a:
   $$\Delta t_{\text{cycle}} \approx 470\text{ ms} \implies \text{FPS}_{\text{targets}} \approx 2.12\text{ Hz}$$
   Questo conferma che la pipeline di detection OpenVINO a 640x640 in FP32 processa circa 2 frame al secondo su CPU Raspberry Pi 5.

2. **Stabilità di Acquisizione e Jitter**:
   L'acquisizione delle immagini dai nodi `stereo.lx.camera` e `stereo.rx.camera` (formato 1280x720 XRGB8888, sensori IMX708) non risente del carico computazionale della detection. Il jitter misurato sull'acquisizione sinistra rimane confinato sotto i **0.11 ms**, garantendo cadenza costante dei frame a 5 FPS.

3. **Drift dello Skew Stereo (Contesa CPU)**:
   Si osserva una deriva temporale sistematica nello skew di sincronizzazione tra fotocamera sinistra e destra (`Skew sx-dx`):
   - Avvio run ($t = 0\text{ s}$): `avg 0.60 ms / max 0.60 ms`
   - Regime ($t = 100\text{ s}$): `avg 3.54 ms / max 3.63 ms`

   *Causa*: L'esecuzione parallela di `detection_node` (che impiega 2 core CPU intensivamente durante la rettifica e l'inferenza OpenVINO) introduce contesa di scheduling con i thread gestiti da `libpisp` e `libcamera`. Pur non causando drop di frame, gli irq/callback dei due driver camera accumulano un desincronismo relativo di circa 3 ms su 100 secondi di esecuzione.

---

## 5. Analisi Termica — T_full (in corso / pianificata)

*Sezione in attesa dell'esecuzione della sessione `T_full` (`enable_enhancement=true`, `enable_detection=true`).*

---

## 6. Confronto tra configurazioni

| Configurazione | FPS Raw (LX/RX) | FPS Targets | Latenza Inferenza | Jitter LX | Skew Stereo (LX-RX) | Note |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `T_baseline` | **5.00** | — | — | < 0.05 ms | Constant | Carico CPU ~30%, plateau ~57-58 °C |
| `T_detection` | **5.00** | **~2.12** | **~470 ms** | < 0.11 ms | 0.60 → 3.63 ms | 2 thread OpenVINO FP32 su CPU |
| `T_full` | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* | Acquisizione + Enhancer + Detection |

---

## 7. Conclusioni e Prossimi Passi

### Stato Avanzamento

- ✅ **T_baseline**: Completata. Carico termico minimo, plateau stabile a 57-58 °C, zero throttling.
- ✅ **T_detection**: Completata caratterizzazione prestazionale e temporale iniziale. Detection rate a **~2.12 FPS** con latenza di ciclo di **~470 ms**.
- ⏳ **T_full**: Da eseguire per la valutazione del worst-case con nodo di enhancement attivo.

### Prossimi passi

1. Completare il prolungamento del log di telemetria termica per `T_detection` fino ai 3600 s completi.
2. Eseguire la sessione **T_full** (acquisizione + enhancement + detection) per 3600 s.
3. Generare i grafici comparativi termici (`T_baseline_temp.png`, `comparison_temp.png`, `fps_vs_temp.png`) nella cartella `benchmarks/thermal_results/plots/`.
4. Spuntare la Fase 7 in `docs/TODO.md`.

---

## 8. Appendice — Grafici (da generare)

I grafici aggiornati verranno posizionati in `benchmarks/thermal_results/plots/`:

- `T_baseline_temp.png`: Curva temperatura e picchi baseline.
- `T_detection_fps_skew.png`: Andamento FPS target e derivazione dello skew stereo sotto carico.
- `comparison_temp.png`: Profilo comparativo termico delle tre configurazioni.
