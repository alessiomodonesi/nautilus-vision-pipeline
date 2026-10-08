# TO DO

## Fase 1 — Acquisizione con ROS2

- [x] Passa a ROS invece che usare il demon (mi pare si usi camera\_ros <https://github.com/christianrauch/camera_ros> e poi lo imposti a quello che serve).
- [x] Misurare FPS reali, jitter e skew temporale tra camera sinistra e destra.

## Fase 2 — Nodo di enhancement

Obiettivo: un nodo in `nautilus_perception` che legge le immagini e ci applica l'enhancement.

- [x] Realizza il nodo che prende le immagini e le migliora (applica l'algoritmo in pratica).
- [x] Misurare FPS reali e delay entrata-uscita da questo nodo.

## Fase 3 — Nodo di salvataggio (probably one to skip)

Obiettivo: un nodo in `nautilus_camera` che legge le immagini (enhanced o no, a seconda della configurazione) e le salva in una cartella per uso futuro.

- [ ] Realizza il nodo che prende le immagini e le salva.
- [ ] Misurare FPS reali e delay entrata-uscita da questo nodo.
- [ ] Valutare prima `ros2 bag record` (mcap, immagini compresse). Il nodo serve se i biologi vogliono JPEG in cartelle; in quel caso numerazione incrementale dei file, perché manca l'RTC.

## Fase 4 — Nodo di detection

Obiettivo: un nodo in `nautilus_perception` che legge le immagini e pubblica i target.

- [x] Realizza il nodo che fa la stereovision e trova i target.
- [x] Pubblicazione su `/stereo_down/targets` con `vision_msgs/Detection2DArray`.
- [x] Parametri (soglie, modello, device) in YAML e launch file funzionante.
- [x] Input configurabile: immagini raw o enhanced.

## Fase 5 — Benchmark

Obiettivo: un confronto equo e riproducibile eseguito sul Pi.

- [ ] Tre configurazioni di pipeline: solo acquisizione, acquisizione + detection, acquisizione + enhancement + detection.
- [ ] Vedi te i modelli che vuoi testare, secondo me ha senso OpenVino e il modello di Manuel ma non so se sono comparabili.
- [ ] Latenza media, p50 e p95 con `perf_counter`, separata in pre-processing, inferenza e post-processing.
- [ ] FPS, CPU%, RAM, temperatura e `vcgencmd get_throttled`.
- [ ] mAP sul validation set per ogni variante, per quantificare quanta accuratezza costano.
- [ ] Output CSV e grafici generati da qualche script.

## Fase 6 — Stress test termico

Obiettivo: testare se la detection può restare sul Pi a box chiusa.

- [ ] 1h a box chiusa in tre configurazioni: solo acquisizione, acquisizione + detection, acquisizione + enhancement + detection.
- [ ] Log ogni secondo di temperatura, frequenza CPU, FPS e flag di throttling.

## Fase 7 — Integrazione

- [ ] Portare i nodi nella repo Nautilus, con CycloneDDS configurato come il resto dello stack.
- [ ] Test Pi -> Jetson con sincronizzazione `chrony` verificata: senza RTC è indispensabile, altrimenti i timestamp delle detection non valgono nulla.

## Fase 8 — Documentazione

- [ ] Tesi e slide.
- [ ] Documentazione nella repo.
