# ROS 2 Workspace — Nautilus Vision Pipeline

Questo workspace contiene l'implementazione dei nodi e dei pacchetti ROS 2 (Jazzy Jalisco) per la pipeline di computer vision edge del veicolo sottomarino **Nautilus**. L'architettura è ottimizzata per eseguire l'acquisizione stereoscopica, la diagnostica telemetrica, l'enhancement visivo e l'object detection 3D su hardware vincolato: **Raspberry Pi 5 (8 GB RAM, box stagna in alluminio, raffreddamento passivo)**.

---

## 1. Struttura dei Pacchetti

Il workspace è organizzato nei seguenti pacchetti ROS 2:

* **[`nautilus_camera`](src/nautilus_camera/README.md)**:
  Gestisce l'acquisizione stereoscopica interfacciandosi con il driver [`camera_ros`](src/camera_ros/README.md) per i due sensori Sony IMX708 (Pi Camera Module 3 via bus CSI).
  * **Acquisizione**: configurata a 1280×720 @ 5 FPS nominali tramite `config/camera_params.yaml`.
  * **Benchmark e Diagnostica**: include [`metrics_node`](src/nautilus_camera/nautilus_camera/metrics_node.py) per il calcolo in tempo reale di FPS effettivi, jitter inter-frame e skew temporale stereo.
  * **Registrazione Dati**: la persistenza delle missioni avviene tramite `ros2 bag record` (formato MCAP, controllato dal servizio `nautilus-bag.service`), con estrazione post-missione delegata a `tools/extract_bag_frames.py` per non appesantire la CPU durante la navigazione.

* **[`nautilus_perception`](src/nautilus_perception/README.md)**:
  Pacchetto core di Computer Vision e Machine Learning per l'elaborazione dei flussi video stereo.
  * **Enhancement ([`enhancement_node`](src/nautilus_perception/nautilus_perception/enhancement_node.py))**: applica algoritmi classici di miglioramento dell'immagine (Laplacian Sharpening + CLAHE). La rete neurale WaterNet è disabilitata di default (`waternet_mode:=force_off`) poiché richiederebbe ~70 secondi per frame su CPU ARM, risultando incompatibile con l'uso real-time.
  * **Detection & Stima Distanza ([`detection_node`](src/nautilus_perception/nautilus_perception/detection_node.py))**: architettura **"Detect-Then-Range"**. Esegue YOLOv8n (default OpenVINO FP32) sul frame sinistro rettificato e calcola la distanza metrica tridimensionale $(X, Y, Z)$ tramite matcher stereo localizzato ([`SparseBlockMatcher`](src/nautilus_perception/nautilus_perception/detection/core_detection.py)), pubblicando i target su `/stereo_down/targets` in formato standard `vision_msgs/Detection2DArray`.

* **[`nautilus_common`](src/nautilus_common/README.md)**:
  Pacchetto di utility condivise. Centralizza i profili di comunicazione QoS (Quality of Service) in un unico file YAML (`config/qos_overrides.yaml`) come **Single Source of Truth (SSOT)**. I nodi Python li importano via [`qos_profiles.py`](src/nautilus_common/nautilus_common/qos_profiles.py), mentre i nodi C++ (come `camera_ros`) li caricano nativamente tramite `--params-file`.

* **[`nautilus_msgs`](src/nautilus_msgs/README.md)**:
  Definizione delle interfacce custom (messaggi ROS 2) che attraversano i confini dei pacchetti, come [`ArmCommand.msg`](src/nautilus_msgs/msg/ArmCommand.msg) sul topic `/arm/command`.

---

## 2. Servizi di Produzione e Avvio al Boot

Sul target Raspberry Pi, i servizi systemd regolano il ciclo di vita della pipeline:

1. **`nautilus-vision.service`**: avvia automaticamente al boot l'acquisizione stereo base ([`nautilus_camera/launch/stereo_camera.launch.py`](src/nautilus_camera/launch/stereo_camera.launch.py)).
2. **`lock-cameras.service`**: associato a `nautilus-vision.service` via `PartOf`, esegue `deploy/lock_cameras.py` dopo l'avvio delle camere per imporre il lock fotometrico a runtime (`AeEnable:=false`, `AwbEnable:=false`, fuoco manuale `LensPosition: 2.6 / 1.5`), aggirando le limitazioni note del driver `camera_ros`.
3. **`nautilus-bag.service`**: (opzionale, gestito da `ENABLE_BAG` in `pipeline_config.env`) registra i flussi stereo in un file MCAP compresso per la documentazione scientifica.

> [!NOTE]
> I nodi di elaborazione (`enhancement_node`, `detection_node`) e di benchmark (`metrics_node`) **non partono mai automaticamente al boot**, per non saturare la CPU e il budget termico durante la navigazione di crociera. Vanno avviati esplicitamente da operatore o tramite mission manager.

---

## 3. Prerequisiti e Configurazione Middleware

* **Sistema Operativo**: Ubuntu 24.04 LTS a 64-bit
* **Distribuzione ROS 2**: Jazzy Jalisco
* **Middleware DDS**: Eclipse CycloneDDS (`rmw_cyclonedds_cpp`)
* **Librerie Principali**: Intel OpenVINO 2024.x, Ultralytics YOLOv8, OpenCV 4.x, PyYAML, psutil

### Configurazione CycloneDDS

Per garantire la corretta interoperabilità tra Raspberry Pi e il computer di missione Jetson, impostare le variabili d'ambiente:

```bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///home/nautilus/nautilus-vision-pipeline/deploy/cyclonedds.xml
export ROS_DOMAIN_ID=42
```

Questi parametri sono allineati a `pipeline_config.env` e ai file unit systemd. Se i nodi non condividono lo stesso `ROS_DOMAIN_ID` o la stessa configurazione di trasporto, non potranno comunicare.

---

## 4. Compilazione del Workspace

Dalla cartella principale del workspace, compilare con `colcon` utilizzando sempre `--symlink-install`:

```bash
cd ~/nautilus-vision-pipeline/ros2_ws

# Compilazione di tutti i pacchetti
colcon build --symlink-install

# In alternativa, compilazione selettiva di un singolo pacchetto
colcon build --symlink-install --packages-select nautilus_perception

# Sourcing dell'ambiente generato
source install/setup.bash
```

L'uso di `--symlink-install` fa sì che le modifiche ai file di launch, agli script Python e ai file YAML in `src/` abbiano effetto immediato senza richiedere una ricompilazione a ogni modifica.

---

## 5. File di Configurazione YAML e Priorità dei Parametri

I parametri sono centralizzati in due file di configurazione principali:

* [`src/nautilus_camera/config/camera_params.yaml`](src/nautilus_camera/config/camera_params.yaml): parametri hardware delle telecamere `camera_ros` (risoluzione, frametime, controlli fotometrici, diottrie) e configurazione di `metrics_node`.
* [`src/nautilus_perception/config/detection_params.yaml`](src/nautilus_perception/config/detection_params.yaml): modello YOLOv8, risoluzione (`imgsz`), soglia di confidenza, threading e tolleranza di sincronizzazione stereo.

### Regola di Priorità dei Parametri

1. **Avvio standard senza argomenti**: il file YAML ha priorità assoluta. Tutte le chiavi vengono lette e applicate fedelmente dal nodo.
2. **Override da CLI al launch**: passando argomenti espliciti da riga di comando (es. `model_filename:=best_416_fp32_openvino_model`, `enable_debug:=true`, `enable_metrics:=true`), tali valori sovrascrivono il parametro corrispondente per quella specifica sessione.

---

## 6. Comandi Rapidi di Avvio

```bash
# 1. Avvio della sola acquisizione stereoscopica (con driver camera_ros)
ros2 launch nautilus_camera stereo_camera.launch.py

# 2. Avvio acquisizione con diagnostica FPS / Jitter / Skew attiva
ros2 launch nautilus_camera stereo_camera.launch.py enable_metrics:=true

# 3. Avvio della sola detection (con camere già avviate in background da systemd)
ros2 launch nautilus_perception detection.launch.py

# 4. Avvio della sola detection con finestra grafica OpenCV di debug (richiede display)
ros2 launch nautilus_perception detection.launch.py enable_debug:=true

# 5. Avvio della pipeline integrata (enhancement + detection sopra le camere già attive)
ros2 launch nautilus_perception pipeline.launch.py \
    enable_enhancement:=true \
    enable_detection:=true

# 6. Avvio completo standalone da zero (inclusa acquisizione telecamere)
ros2 launch nautilus_perception pipeline.launch.py \
    include_stereo_camera:=true \
    enable_detection:=true \
    enable_enhancement:=false
```
