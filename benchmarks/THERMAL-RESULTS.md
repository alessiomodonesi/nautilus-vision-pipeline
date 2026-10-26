# Report Stress Test Termico — Nautilus Vision (Fase 7)

Questo documento raccoglie i risultati dello **stress test termico** (Fase 7
di `docs/TODO.md`) eseguito sul Raspberry Pi 5 a **box chiusa**, in tre
configurazioni di pipeline selezionate dalla Fase 6. L'obiettivo è
determinare se la detection (e in prospettiva la pipeline full) è
sostenibile per **1 ora continuativa** in condizioni operative reali
(senza dissipazione attiva), senza incorrere in throttling termico.

I dati grezzi sono in `benchmarks/thermal_results/csv/`, i grafici in
`benchmarks/thermal_results/plots/`.

**Stato:** T_baseline completata il 26/10/2026. T_detection e T_full in
corso / pianificate. Le sezioni corrispondenti saranno popolate al termine
delle rispettive sessioni.

---

## 1. Sintesi Esecutiva (TL;DR)

- **T_baseline (solo acquisizione)**: **stabile per tutti i 3600 s** a
  **5.00 FPS** su entrambi i canali, con temperatura che si assesta su un
  plateau di **~57-58 °C** dopo ~25 minuti. **Nessun throttling termico**
  (`throttled = 0x0` costante) e clock ARM fisso a **2400 MHz**. Jitter
  sub-millisecondo, CPU ~30 %, RAM ~14.5 %.
- **Picchi termici**: massimo registrato **60.9 °C** (t ≈ 1437 s), ben
  sotto la soglia di soft-throttling del Pi 5 (~80-85 °C). Il margine
  residuo è ampio.
- **Delta termico utile**: da **43.3 °C** (primo campione post-warmup) a
  **56.5 °C** (fine run), con plateau intermedio. Il Pi si scalda di
  ~13 °C sotto carico di sola acquisizione.
- **Anomalie non termiche**: due cluster di "FPS desync" tra lx e rx
  (t ≈ 1301-1303 s e t ≈ 2150-2170 s), che si compensano sulla media e
  **non** correlano con eventi termici. Da annotare per confronto con
  T_detection/T_full.
- **Nota sul metadata**: `soc_temp_initial_c = 38.4` è la temperatura
  idle *prima* del launch (fine del loop di stabilità termica). La
  temperatura al primo campione del CSV è **43.3 °C** perché i 30 s di
  warmup con i due `camera_node` attivi scaldano ~5 °C. Per i plot va
  usato il CSV, non il metadata.

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
  secondo, sottoscrivendo `/stereo_down/timings` (assente in
  `T_baseline`).

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

### 2.5 Nota sulla temperatura iniziale

Il wrapper attende un **plateau di stabilità termica** prima di iniziare
(3 letture consecutive entro ±1 °C) e cattura la temperatura in quel
momento come `soc_temp_initial_c`. Il launch della pipeline segue, e i
**30 s di warmup** portano la temperatura ~5 °C più in alto. Ne
consegue che:

- `soc_temp_initial_c` nel metadata = temperatura **pre-launch** (idle
  stabile, nessun nodo ROS attivo);
- primo campione del CSV = temperatura **post-warmup** (camera attive,
  pipeline avviata).

Per i grafici e per il confronto tra configurazioni, il riferimento è il
**CSV** (primo campione). Il metadata serve a documentare la condizione
di partenza pulita.

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

### 3.2 Profilo termico

![Temperatura SoC nel tempo — T_baseline](./thermal_results/plots/T_baseline_temp.png)
*(Grafico da generare dopo le 3 run; descrizione sotto)*

**Descrizione attesa**: curva che sale da 43 °C a ~57 °C in ~20-25 minuti
con andamento asintotico, poi oscilla tra 56 e 58 °C per il resto
dell'ora. I picchi isolati a 60-61 °C (t ≈ 1437 s e t ≈ 1440-1450 s)
corrispondono a brevi burst di attività di sistema (probabile `journald`
o I/O) e rientrano nel plateau entro 1-2 s. **Nessun trend crescente**
nella seconda metà della run: la temperatura è stazionaria.

**Interpretazione**: la sola acquisizione (2 × `camera_node` a 5 FPS)
non è un carico termico significativo per il Pi 5 a box chiusa. Il
sistema raggiunge il plateau in ~25 minuti e non lo abbandona. Il margine
rispetto al soft-throttling è **>20 °C**: la baseline è
**termicamente sicura** a oltranza.

### 3.3 Clock e throttling

![Clock ARM e flag throttled — T_baseline](./thermal_results/plots/T_baseline_clock.png)
*(Grafico da generare dopo le 3 run)*

**Descrizione attesa**: due pannelli — `clock_mhz` fisso a 2400 per tutti
i 3600 campioni, `throttled` fisso a `0x0`. Nessun bit 16-19 settato,
nessun taglio di frequenza. La CPU non è mai stata costretta a scendere
sotto il valore nominale.

**Interpretazione**: il throttling termico (bit `0x4`, `0x40000`,
`0x80000`) **non è mai occorso** durante l'ora di baseline. Questo è il
comportamento atteso per carichi sotto i ~5 W sul Pi 5 con dissipazione
passiva: il calore dissipato è inferiore a quello generato e il firmware
non interviene.

### 3.4 FPS e jitter

![FPS per topic e jitter — T_baseline](./thermal_results/plots/T_baseline_fps.png)
*(Grafico da generare dopo le 3 run)*

**Descrizione attesa**: quattro linee — `fps_raw_lx` e `fps_raw_rx`
praticamente sovrapposte a 5.0, `fps_enhanced` e `fps_targets` a 0.0
(topic assenti). Un pannello sottostante per `jitter_ms` intorno a
0.00-0.03 ms.

**Osservazioni**:

- **Primo secondo**: `raw_lx = 5.405`, `raw_rx = 4.504`. È il transiente
  di warmup: la pipeline è appena partita e i due nodi consegnano i primi
  frame in ordine non sincronizzato.
- **Dal secondo 2 in poi**: entrambi i canali stabilmente a 5.0 (±0.005).
  Piccole oscillazioni (4.996-5.004) sono rumore di quantizzazione del
  conteggio per-secondo.
- **Anomalie desync**: due cluster in cui lx e rx si scambiano il
  "surplus" di frame (vedi §3.6).
- **Jitter**: sub-millisecondo, come atteso a 5 FPS con
  `FrameDurationLimits: [200000, 200000]`.

### 3.5 CPU e RAM

![CPU e RAM nel tempo — T_baseline](./thermal_results/plots/T_baseline_cpu_ram.png)
*(Grafico da generare dopo le 3 run)*

**Descrizione attesa**: `cpu_pct` con valore medio ~29-30 % e spike
isolati a 36 % (t ≈ 186 s) e 46 % (t ≈ 2097 s), rientro immediato in 1 s.
`ram_pct` con crescita monotona da 14.2 % a 14.7 % (≈ +40 MB su 8 GB).
Nessun segno di degrado progressivo o memory leak.

**Interpretazione**: la baseline non satura la CPU. Lo spike al 46 % è
probabilmente un burst di `journald` o di un processo di sistema
concorrente con il flush del CSV. Non è correlato a eventi termici e non
ha effetti misurabili su FPS o jitter.

### 3.6 Anomalie non termiche

**FPS desync lx/rx**: due cluster in cui i due canali si scambiano
~1 frame al secondo, compensandosi sulla media triennale.

```text
Cluster 1 — t ≈ 1301-1303 s
  t=1301: lx=4.924  rx=5.909
  t=1302: lx=5.079  rx=4.063
  t=1303: lx=4.928  rx=5.914

Cluster 2 — t ≈ 2150-2170 s (ripetuto 6-7 volte in 20 s)
  t=2150: lx=5.915  rx=4.929
  t=2151: lx=4.060  rx=5.075
  t=2153: lx=5.915  rx=4.930
  ...
```

**Possibili cause** (in ordine di probabilità):

1. **Contesa di sistema transiente**: un processo concorrente
   (`journald`, kernel worker, flush I/O) ruba CPU a uno dei due
   `camera_node` per ~200 ms, ritardando la consegna di un frame al
   subscriber del monitor. Il frame arriva nel secondo successivo e
   sbilancia i due conteggi.
2. **Riordino DDS**: un frame LX arriva con pochi ms di ritardo rispetto
   al tick del timer di monitoraggio, e viene attribuito al secondo
   successivo.
3. **MicroSD stall**: improbabile in assenza di `saving_node`, ma
   possibile se qualche processo di sistema scrive in background.

**Stato**: **non termico**. `clock_mhz` resta a 2400 e `throttled = 0x0`
durante entrambi i cluster. `temp_c` non mostra correlazione (anzi, il
primo cluster avviene in fase di salita termica, il secondo vicino al
plateau).

**Azione**: annotato. Da confrontare con T_detection e T_full. Se il
pattern **sparisce** con carico maggiore, è masking del rumore di
sistema. Se **peggiora**, è indice di contesa di risorse che la Fase 7
sta correttamente catturando.

---

## 4. Analisi Termica — T_detection (in corso)

*Sezione da popolare al termine della run. Struttura prevista:*

- Tabella riepilogo metriche (temp initial/final/max, plateau, delta
  termico, `clock_mhz`, `throttled`, FPS raw/targets, `infer_ms_mean`,
  CPU%, RAM%)
- Profilo termico (grafico + descrizione)
- **`infer_ms_mean` vs tempo**: analisi del ginocchio termico
- Confronto con T_baseline: quanto scalda in più la detection?
- Tempo al throttling (se avviene)

**Domanda a cui risponderà**: la detection FP32 (~2.3 FPS in Fase 6) è
sostenibile per 1 h a box chiusa senza throttling?

---

## 5. Analisi Termica — T_full (in corso)

*Sezione da popolare al termine della run. Struttura prevista:*

- Tabella riepilogo metriche (come sopra, con anche `enhanced` FPS)
- Profilo termico
- **`infer_ms_mean`**: impatto dell'enhancement sulla latenza della
  detection sotto stress termico
- Confronto con T_detection: quanto costa l'enhancement in termini di
  temperatura e di FPS di detection?
- Tempo al throttling (se avviene)

**Domanda a cui risponderà**: il worst case (`enhancement + detection`)
è compatibile con 1 h a box chiusa?

---

## 6. Confronto tra configurazioni (rimandato)

*Sezione da completare dopo T_detection e T_full. Struttura prevista:*

- Tabella comparativa: temp plateau, delta termico, tempo al plateau,
  FPS targets, `infer_ms_mean` a fine run, `throttled` bit 16-19
- Plot sovrapposti temperatura vs tempo per le 3 config
- Plot sovrapposti `infer_ms_mean` vs tempo
- Curva "FPS di detection vs temperatura": esiste una soglia oltre la
  quale le prestazioni degradano?
- Indicazione della config di produzione raccomandata

**Criterio di accettazione (già definito in fase di progettazione)**:

- `T_detection` e `T_full` restano con `clock_mhz = 2400` e `throttled`
  senza bit 16-19 per tutti i 3600 s → detection sostenibile a box
  chiusa.
- `T_full` mostra throttling dopo N minuti → l'enhancement non è
  sostenibile; la produzione deve restare su `T_detection`.
- Anche `T_baseline` va in throttling → problema hardware
  (dissipatore/alimentazione), non software. **Non è il caso** di questa
  sessione: T_baseline è passata indenne.

---

## 7. Conclusioni e Prossimi Passi

### T_baseline (chiusa)

- ✅ **La sola acquisizione è termicamente sicura a box chiusa per 1 h**.
  Plateau a 57-58 °C, margine >20 °C al soft-throttling, zero flag di
  throttling, zero tagli di clock.
- ✅ FPS stabili a 5.00, jitter trascurabile, CPU ~30 %, RAM stabile.
- 📝 **Due anomalie desync FPS** annotate (t ≈ 1301 s e t ≈ 2150-2170 s),
  non termiche, da confrontare con le config successive.
- 📝 **Nota metodologica**: `soc_temp_initial_c` = idle pre-launch
  (38.4 °C), primo campione CSV = post-warmup (43.3 °C). Usare il CSV
  per i plot.

### Prossimi passi

1. **Lanciare T_detection** e popolare §4. Monitorare `infer_ms_mean`
   come segnale principale del ginocchio termico: se sale prima che
   `clock_mhz` scenda, è l'inizio del soft-throttling.
2. **Lanciare T_full** e popolare §5.
3. **Popolare §6** con il confronto tra le tre config.
4. **Generare i grafici** con uno script `plot_thermal.py` dedicato (non
   `plot_results.py`, che è tarato sulla Fase 6), oppure con uno snippet
   ad-hoc. Le immagini vanno in `benchmarks/thermal_results/plots/` con
   naming coerente (`T_baseline_*.png`, ecc.).
5. **Aggiornare `docs/TODO.md`**: spuntare la Fase 7 una volta completate
   le tre config.
6. **Considerazioni sulla Fase 8** (integrazione con stack Nautilus):
   la baseline conferma che il Pi 5 non ha problemi termici in
   acquisizione. Il vincolo sarà la detection, che T_detection
   quantificherà.

---

## 8. Appendice — Grafici (da generare)

I grafici per questa sessione vanno prodotti a partire da
`benchmarks/thermal_results/csv/2026-10-26_T_baseline_run1_thermal.csv`
e salvati in `benchmarks/thermal_results/plots/`. Naming suggerito:

| File | Contenuto |
| :--- | :--- |
| `T_baseline_temp.png` | `temp_c` vs `t_elapsed_s`, con linee verticali ai picchi >60 °C |
| `T_baseline_clock.png` | `clock_mhz` e `throttled` vs `t_elapsed_s` |
| `T_baseline_fps.png` | `fps_raw_lx`, `fps_raw_rx`, `fps_enhanced`, `fps_targets` vs `t_elapsed_s` |
| `T_baseline_cpu_ram.png` | `cpu_pct` e `ram_pct` vs `t_elapsed_s` |
| `T_baseline_jitter.png` | `jitter_ms` vs `t_elapsed_s` |

Quando `T_detection` e `T_full` saranno disponibili, verranno aggiunti:

| File | Contenuto |
| :--- | :--- |
| `comparison_temp.png` | 3 curve `temp_c` sovrapposte |
| `comparison_infer_ms.png` | `infer_ms_mean` per T_detection e T_full |
| `comparison_fps_targets.png` | `fps_targets` per T_detection e T_full |
| `fps_vs_temp.png` | Scatter FPS targets vs temp_c |

---

*Report iniziato il 26/10/2026. T_baseline completata. T_detection e
T_full in corso.*
