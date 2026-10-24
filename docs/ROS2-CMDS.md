# Cheat Sheet Comandi ROS 2

## Compilazione e Setup

* **Compilazione dell'intero workspace**: Esegui `colcon build` all'interno della cartella `ros2_ws` che contiene l'implementazione del sistema.
* **Compilazione mirata**: Compila unicamente i pacchetti dedicati all'elaborazione visiva usando:
  `colcon build --packages-select nautilus_perception nautilus_camera nautilus_msgs`
* **Inclusione dell'ambiente**: Esegui `source install/setup.bash` nella root del workspace per rendere visibili a ROS 2 i nuovi binari compilati.

## Esecuzione dei Nodi

* **Impostazione del Middleware**: Dato che lo stack di Nautilus è configurato per utilizzare CycloneDDS, esporta la variabile prima di avviare qualsiasi nodo:
  `export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp`
* **Avvio manuale di un singolo nodo**: Lancia individualmente un nodo usando:
  `ros2 run nautilus_perception <nome_nodo>`
* **Avvio tramite Launch File**: Usa i file launch per avviare il sistema caricando contemporaneamente i file YAML (parametri di soglia, modello, device):
  `ros2 launch nautilus_perception <file_launch>.launch.py`

## Debug e Analisi dei Topic

* **Lettura dei target in output**: Visualizza i risultati della object detection:
  `ros2 topic echo /stereo_down/targets`
* **Misurazione FPS reali e latenza**: Verifica la frequenza operativa, il jitter e lo skew temporale dei nodi:
  `ros2 topic hz /stereo_down/targets` (o il topic delle immagini)
* **Struttura dei messaggi**: Controlla i campi disponibili per le coordinate dei target:
  `ros2 interface show vision_msgs/msg/Detection2DArray`
* **Topologia di rete**: Esamina i nodi e i topic in esecuzione:
  `ros2 topic list` e `ros2 node list`

## Registrazione Dati

* **Salvataggio delle sessioni in mcap**: Registra le immagini (grezze o processate) per l'uso futuro:
  `ros2 bag record -s mcap -o <nome_salvataggio> <nome_topic>`
