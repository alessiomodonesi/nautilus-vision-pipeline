# Nautilus Edge Perception & Vision Benchmark

Pipeline di computer vision edge basata su ROS 2 (Jazzy) e accelerata tramite OpenVINO. Sviluppata per il modulo di visione stereoscopica nell'ambito del progetto Nautilus (Università di Padova) — dedicato allo sviluppo di sistemi integrati innovativi per il monitoraggio e la valorizzazione dell'ambiente acquatico e all'esplorazione autonoma per il rilievo di flora e fauna —, include un'architettura modulare per l'acquisizione stereoscopica ad alto FPS, l'enhancement delle immagini e l'object detection in condizioni di stress termico e risorse hardware limitate (Prova Finale / Tesi). Questo repository contiene il codice sorgente, i modelli e gli script di validazione sviluppati a tale scopo.

## Obiettivi del Progetto

Il focus principale è l'ottimizzazione e l'integrazione di algoritmi di Object Detection in un ambiente con risorse computazionali limitate e in condizioni di stress termico (camera stagna).

Alla luce dei nuovi sviluppi, gli obiettivi specifici includono:

* **Transizione ad Acquisizione ROS 2:** Sostituzione del demone di acquisizione in background con un approccio ROS 2 nativo (es. basato su `camera_ros`), per abbattere il jitter e lo skew temporale tra le camere stereoscopiche.
* **Pipeline Modulare:** Sviluppo di nodi ROS 2 dedicati in pipeline per l'acquisizione, l'enhancement delle immagini e il salvataggio dei dati.
* **Object Detection Subacquea:** Implementazione di nodi di detection configurabili tramite YAML (es. modelli OpenVINO e YOLO) per la stereovisione, capaci di pubblicare i target identificati tramite `vision_msgs/Detection2DArray`.
* **Benchmarking Strutturato:** Valutazione di latenza (media, p50, p95 con `perf_counter`), FPS, CPU, RAM e calo di accuratezza (mAP) su tre diverse configurazioni della pipeline:
  1) Solo acquisizione
  2) Acquisizione + detection
  3) Acquisizione + enhancement + detection.
* **Stress Test Termico:** Esecuzione di test della durata di 1 ora a box chiusa per monitorare la temperatura, la frequenza della CPU e i flag di *thermal throttling* nelle varie configurazioni.

## Architettura dei Nodi ROS 2

L'elaborazione visiva è distribuita su nodi specializzati integrati nel repository Nautilus:

* **Acquisizione (`camera_ros`):** Nodo base per interfacciarsi ai sensori RPi.
* **Nodo di Enhancement (`nautilus_perception`):** Legge le immagini grezze e applica algoritmi di miglioramento dell'immagine prima dell'inferenza. *(Nota: il codice core dell'algoritmo di enhancement è di terze parti, qui integrato e incapsulato in un nodo ROS 2. Vedi sezione Riconoscimenti).*
* **Nodo di Salvataggio (`nautilus_camera`):** Si occupa del logging dei dati a scopo di analisi per i biologi marini, tramite `ROS 2 bag record` (formato mcap) oppure salvando immagini JPEG con numerazione incrementale.
* **Nodo di Detection (`nautilus_perception`):** Riceve in input immagini raw o enhanced, esegue l'inferenza tramite OpenVINO e pubblica le detection su `/stereo_down/targets`.
* **Messaggi Custom (`nautilus_msgs`):** Pacchetto dedicato per la definizione strutturata delle interfacce di comunicazione (es. comandi e target identificati) tra i vari nodi del sistema.

## Stack Tecnologico

* **Linguaggio:** Python 3, C++
* **Middleware:** ROS 2 (Domain DDS: CycloneDDS)
* **Computer Vision & AI:** OpenCV, Ultralytics (YOLOv8), Intel OpenVINO
* **Sincronizzazione:** `chrony` per l'allineamento dei timestamp tra Jetson e Pi in assenza di RTC hardware.
* **Hardware:** Raspberry Pi (Nodo Fotocamera Underwater)
* **Sviluppo e Deploy:** Docker e Docker Compose per la riproducibilità dell'ambiente (Ubuntu 24.04 / ROS 2 Jazzy) su hardware eterogeneo (Mac, Jetson, Raspberry).

## Struttura della Repository

* `/models/`: Modelli addestrati `.pt` e le relative versioni esportate e ottimizzate in formato OpenVINO (`.xml`, `.bin`) per inferenza su Edge.
* `/benchmarks/`: Script per la profilazione comparativa delle performance e generazione di CSV e grafici sulle metriche di stress.
* `/docker/`: Configurazioni `Dockerfile` e `docker-compose.yaml` per la validazione indipendente del workspace ROS 2.
* `/ROS 2_ws/`: Workspace ROS 2 contenente l'implementazione dei nodi di Acquisizione, Enhancement, Salvataggio e Detection, oltre ai messaggi custom.
* `/docs/`: Documentazione, roadmap operativa (`TODO.md`), tesi, slide e risultati degli stress test termici.

*(Nota storica: Il codice sorgente del vecchio daemon in C (`/sensing-rigs-daemon/`) e l'analisi del "cold-start" rimangono versionati a fini accademici e di documentazione, ma l'acquisizione operativa è ora demandata a ROS 2 nativo)*

## Riconoscimenti e Codice di Terze Parti

* **Sensing Rigs Daemon (`/sensing-rigs-daemon/`):** Incluso come sottomodulo Git. Ho contribuito personalmente allo sviluppo di questo componente (vedi README originale per i dettagli), che rimane versionato per scopi di benchmarking e documentazione storica.
* **Algoritmo di Image Enhancement (`ROS 2_ws/src/nautilus_perception/enhancement`):** Il codice sorgente dell'algoritmo di miglioramento delle immagini **non è stato sviluppato da me**. È stato prelevato dalla repository originale [underwater-image-enhancement](https://github.com/nautilus-unipd/underwater-image-enhancement) e modificato esclusivamente al fine di poterlo incapsulare ("wrappare") all'interno di un nodo ROS 2 compatibile con la pipeline del progetto. Tutti i crediti per la logica dell'algoritmo vanno ai rispettivi autori.
* **Marine Debris Computer Vision:** Il setup e i modelli per il riconoscimento dei detriti marini **non sono stati sviluppati da me**. Il materiale è stato prelevato dalla repository [marine_debris_CV](https://github.com/bazzy22/marine_debris_CV) di Manuel e adattato ai fini dell'integrazione e dell'inferenza Edge all'interno di questo progetto. Tutti i crediti per il lavoro e l'addestramento originale vanno al rispettivo autore.
* **Acquisizione ROS 2 (`camera_ros`):** Il codice per l'acquisizione diretta delle immagini è stato integrato utilizzando il pacchetto open-source [camera_ros](https://github.com/christianrauch/camera_ros), sviluppato da Christian Rauch.
