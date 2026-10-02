# ROS 2 Workspace - Nautilus Vision Pipeline

Questo workspace contiene l'implementazione dei nodi ROS 2 (Jazzy) per la pipeline di computer vision edge del progetto Nautilus. L'architettura modulare è progettata per gestire l'acquisizione stereoscopica, l'enhancement delle immagini e l'object detection subacquea in condizioni di risorse limitate (Raspberry Pi in camera stagna).

## Struttura dei Pacchetti

All'interno di questo workspace, il codice sorgente è organizzato nei seguenti pacchetti principali:

* **`nautilus_perception`**: Il pacchetto core dedicato all'elaborazione delle immagini. Contiene:
  * **nodo di enhancement**: Applica algoritmi di miglioramento (incapsulando codice di terze parti) alle immagini grezze per facilitare il riconoscimento.
  * **nodo di detection**: Esegue l'inferenza per la stereovisione utilizzando modelli ottimizzati tramite OpenVINO. Accetta in input immagini raw o enhanced e pubblica i target identificati sul topic `/stereo_down/targets` utilizzando il formato standard `vision_msgs/Detection2DArray`.

* **`nautilus_camera`**: Pacchetto focalizzato sulla gestione e memorizzazione dei dati visivi. Contiene il **nodo di salvataggio**, utile per registrare le immagini tramite `ros2 bag record` (in formato mcap) o salvarle su cartella in formato JPEG con numerazione incrementale per le successive analisi dei biologi marini.

* **`nautilus_msgs`**: Pacchetto contenente le definizioni dei messaggi custom, per garantire una comunicazione strutturata e coerente tra i vari nodi del sistema.

## Prerequisiti e Dipendenze

* **Sistema Base**: Ubuntu 24.04 con ROS 2 Jazzy
* **Middleware**: CycloneDDS
* **Librerie AI e Visione**: OpenCV, Ultralytics (YOLOv8), Intel OpenVINO
* **Acquisizione Hardware**: I nodi presuppongono l'uso del pacchetto `camera_ros` per il corretto interfacciamento con i sensori stereoscopici.

## Compilazione

Per compilare i nodi del sistema visivo, spostati nella root del workspace ed esegui `colcon`:

```bash
# Entra nel workspace
cd ros2_ws

# Compila tutti i pacchetti (oppure usa --packages-select per pacchetti specifici)
colcon build

# Rendi disponibili i binari e i package nel path corrente
source install/setup.bash
```

## Esecuzione e Configurazione

Tutto lo stack Nautilus è configurato per utilizzare CycloneDDS. Prima di avviare l'acquisizione o la pipeline, assicurati che la variabile d'ambiente corretta sia esportata:

```bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
```

### Configurazione tramite YAML

I parametri operativi del nodo di detection (come le soglie di confidenza, il percorso del modello OpenVINO e il device target per l'inferenza) sono configurabili tramite appositi file YAML da passare in fase di lancio.

### Avvio della Pipeline

Si consiglia di avviare il sistema completo tramite i file di launch, in modo da caricare automaticamente le configurazioni:

```bash
ros2 launch nautilus_perception <nome_launch_file>.launch.py
```
