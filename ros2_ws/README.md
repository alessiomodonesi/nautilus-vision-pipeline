# ROS 2 Workspace - Nautilus Vision Pipeline

Questo workspace contiene l'implementazione dei nodi ROS 2 (Jazzy) per la pipeline di computer vision edge del progetto Nautilus. L'architettura modulare è progettata per gestire l'acquisizione stereoscopica, l'enhancement delle immagini e l'object detection subacquea in condizioni di risorse limitate (Raspberry Pi in camera stagna).

## Struttura dei Pacchetti

All'interno di questo workspace, il codice sorgente è organizzato nei seguenti pacchetti principali:

* **`nautilus_camera`**: pacchetto focalizzato sull'acquisizione e sulla memorizzazione dei dati visivi. Contiene il **nodo di salvataggio** (JPEG/PNG su cartella, con numerazione incrementale) e il **nodo di benchmark** (FPS, jitter, skew stereo). Le camere sono configurate tramite un unico YAML letto anche dal `lock_cameras.py` che riapplica i parametri fotometrici al boot.

* **`nautilus_perception`**: il pacchetto core dedicato all'elaborazione delle immagini. Contiene:
  * **nodo di enhancement**: applica algoritmi di miglioramento (incapsulando codice di terze parti) alle immagini grezze. La rete neurale WaterNet è **disabilitata di default** perché pensata solo per post-produzione, non per navigazione: sulla barca la pipeline gira solo in modalità `force_off` (CLAHE + sharpening).
  * **nodo di detection**: esegue l'inferenza per la stereovisione utilizzando modelli ottimizzati tramite OpenVINO. Accetta in input immagini raw o enhanced e pubblica i target identificati sul topic `/stereo_down/targets` utilizzando il formato standard `vision_msgs/Detection2DArray`.

* **`nautilus_common`**: pacchetto di utility condivise. Centralizza i profili QoS in un singolo YAML (`config/qos_overrides.yaml`) come **SSOT**, letto dai nodi Python via `qos_profiles.py` (loader) e dai nodi C++ via `--params-file`. Nessuna duplicazione di valori QoS tra nodo e nodo: una modifica al YAML si propaga a tutta la pipeline senza toccare il codice. Vedi [`README.md`](src/nautilus_common/README.md) per l'architettura completa.

* **`nautilus_msgs`**: pacchetto contenente le definizioni dei messaggi custom, per garantire una comunicazione strutturata e coerente tra i vari nodi del sistema.

## Cosa parte automaticamente al boot

Solo il blocco di acquisizione (`nautilus_camera/stereo_camera.launch.py`) parte in automatico tramite `nautilus-vision.service`. Il salvataggio è opzionale, controllato da `ENABLE_SAVING` in `pipeline_config.env`. Enhancement, detection e metriche **non partono mai da soli**: vanno lanciati a mano. Dettagli operativi in `docs/global_launch.md`.

## Prerequisiti e Dipendenze

* **Sistema Base**: Ubuntu 24.04 con ROS 2 Jazzy
* **Middleware**: CycloneDDS
* **Librerie AI e Visione**: OpenCV, Ultralytics (YOLOv8), Intel OpenVINO
* **Python**: PyYAML (per `lock_cameras.py`)
* **Acquisizione Hardware**: i nodi presuppongono l'uso del pacchetto `camera_ros` per il corretto interfacciamento con i sensori stereoscopici.

## Compilazione

Per compilare i nodi del sistema visivo, spostati nella root del workspace ed esegui `colcon`:

```bash
# entra nel workspace
cd ros2_ws

# compila tutti i pacchetti (oppure usa --packages-select per pacchetti specifici)
colcon build

# rendi disponibili i binari e i package nel path corrente
source install/setup.bash
```

## Esecuzione e Configurazione

Tutto lo stack Nautilus è configurato per utilizzare CycloneDDS. Prima di avviare l'acquisizione o la pipeline, assicurati che la variabile d'ambiente corretta sia esportata:

```bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///home/nautilus/nautilus-vision-pipeline/deploy/cyclonedds.xml
export ROS_DOMAIN_ID=42
```

Questi tre valori sono coerenti con `deploy/cyclonedds.xml`, con i `.service`
systemd e con `pipeline_config.env`. In caso di divergenza, i nodi su domini
DDS diversi non si vedono. Vedi `deploy/cyclonedds.xml` per la configurazione
del trasporto (peer statici, MTU ridotto per WiFi, fragment size).

### Configurazione tramite YAML

I parametri operativi sono distribuiti su due file YAML, uno per pacchetto:

* `nautilus_camera/config/nautilus_camera.yaml` — parametri camera_ros, metrics_node, saving_node.
* `nautilus_perception/config/detection_params.yaml` — parametri detection (modello, soglia, threads, sync).

I parametri passati come launch argument sovrascrivono i valori YAML per la singola run, senza modificare il file.

### Avvio della Pipeline

Si consiglia di avviare i nodi tramite i file di launch, in modo da caricare automaticamente le configurazioni:

```bash
# acquisizione (sempre)
ros2 launch nautilus_camera stereo_camera.launch.py

# aggiungi detection/enhancement sopra l'acquisizione già attiva
ros2 launch nautilus_perception pipeline.launch.py \
    enable_detection:=true enable_enhancement:=false
```
