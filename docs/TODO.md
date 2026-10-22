# TO DO

## Fase 1 — Acquisizione con ROS2

- [x] Passa a ROS invece che usare il demon (mi pare si usi camera\_ros <https://github.com/christianrauch/camera_ros> e poi lo imposti a quello che serve).
- [x] Misurare FPS reali, jitter e skew temporale tra camera sinistra e destra.

## Fase 2 — Nodo di enhancement

Obiettivo: un nodo in `nautilus_perception` che legge le immagini e ci applica l'enhancement.

- [x] Realizza il nodo che prende le immagini e le migliora (applica l'algoritmo in pratica).
- [x] Misurare FPS reali e delay entrata-uscita da questo nodo.

## Fase 3 — Nodo di salvataggio

Obiettivo: un nodo in `nautilus_camera` che legge le immagini (enhanced o no, a seconda della configurazione) e le salva in una cartella per uso futuro.

- [x] Realizza il nodo che prende le immagini e le salva.
- [x] Misurare FPS reali e delay entrata-uscita da questo nodo.
- [x] Valutare prima `ros2 bag record` (mcap, immagini compresse). Il nodo serve se i biologi vogliono JPEG in cartelle; in quel caso numerazione incrementale dei file, perché manca l'RTC.
- [x] Estrattore post-missione `tools/extract_bag_frames.py` (MCAP → JPEG passthrough, zero ricompressione, `metadata.csv`, `--copy-calibration`). Chiude il requisito "i biologi vogliono JPEG in cartelle" senza mantenere `saving_node` attivo in produzione.

## Fase 4 — Nodo di detection

Obiettivo: un nodo in `nautilus_perception` che legge le immagini e pubblica i target.

- [x] Realizza il nodo che fa la stereovisione e trova i target.
- [x] Pubblicazione su `/stereo_down/targets` con `vision_msgs/Detection2DArray`.
- [x] Parametri (soglie, modello, device) in YAML e launch file funzionante.
- [x] Input configurabile: immagini raw o enhanced.

## Fase 5 — Calibrazione stereo a 720p

- [x] Board ChArUco generata e stampata (8×11 quadrati, 15/11 mm, `DICT_4X4_50`, legacy pattern) con `generate_charuco.py`.
- [x] Script di cattura allineati a 720p con lock di `LensPosition` e opzionale lock AE/AWB: `capture_calibration_pairs.py` (GUI) e `capture_calibration_pairs_web.py` (headless).
- [x] Rimosso mismatch di default: risoluzione, `--min-shared-corners` a 15 su entrambi gli script.
- [x] Catturare 30–40 coppie L/R con varietà di tilt (non solo traslazione) e buona copertura del frame.
- [x] Rigenerare `stereo_calib_720p.npz` con `stereo_calibrate.py` alla risoluzione 1280×720. Verificare RMS di reproiezione < 1 px (per-camera e stereo).
- [x] Estrarre nuovi valori di `baseline_m` (= `||T||` o `-P2[0,3]/P2[0,0]`) e `focal_length` (= `P1[0,0]` rettificata) e aggiornare `config.py`.
- [x] Aggiornare `SparseBlockMatcher` in `core_detection.py` con `min_disparity`/`max_disparity` coerenti con la nuova focale (1500.89 px rettificata a 720p → range 100–450 px, Z in [0.40, 1.80] m).
- [x] Sostituire il file nel pacchetto installato e rebuildare `nautilus_perception`.
- [x] Validare: oggetto a distanze note → `Z` stimato entro ±5% (misura su 4 distanze: 0.60 m, 0.70 m, 0.80 m, 0.90 m — errore osservato < 1 cm).
- [x] LensPosition di produzione fissate tramite `calibration/find_focus.py`: lx=2.6, rx=1.5 (entrambe a fuoco a ~0.65 m). Scoperto offset meccanico di +1.05 diottrie sulla lente sinistra, documentato in `DEBUG.md` §3.2.
- [x] Documentare i valori finali e l'errore residuo nel report di benchmark (chiude il gap "accuratezza Z non validata").

## Fase 6 — Benchmark

Obiettivo: un confronto equo e riproducibile eseguito sul Pi.

- [x] Tre configurazioni di pipeline: solo acquisizione, acquisizione + detection, acquisizione + enhancement + detection.
- [x] Vedi te i modelli che vuoi testare, secondo me ha senso OpenVino e il modello di Manuel ma non so se sono comparabili.
- [x] Latenza media, p50 e p95 con `perf_counter`, separata in pre-processing, inferenza e post-processing.
- [x] FPS, CPU%, RAM, temperatura e `vcgencmd get_throttled`.
- [x] mAP sul validation set per ogni variante, per quantificare quanta accuratezza costano.
- [x] Output CSV e grafici generati da qualche script.

## Fase 7 — Stress test termico

Obiettivo: testare se la detection può restare sul Pi a box chiusa.

- [ ] 1h a box chiusa in tre configurazioni: solo acquisizione, acquisizione + detection, acquisizione + enhancement + detection.
- [ ] Log ogni secondo di temperatura, frequenza CPU, FPS e flag di throttling.

## Fase 8 — Integrazione

- [ ] Portare i nodi nella repo Nautilus, con CycloneDDS configurato come il resto dello stack.
- [ ] Test Pi -> Jetson con sincronizzazione `chrony` verificata: senza RTC è indispensabile, altrimenti i timestamp delle detection non valgono nulla.

## Fase 9 — Documentazione

- [ ] Tesi e slide.
- [ ] Documentazione nella repo.
