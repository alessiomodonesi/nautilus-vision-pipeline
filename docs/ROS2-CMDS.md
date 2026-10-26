# Cheat Sheet Comandi ROS 2 — Nautilus Vision Pipeline

Prontuario operativo dei comandi ROS 2 (Jazzy Jalisco) per la compilazione, l'esecuzione, il monitoraggio telemetrico e la gestione dei servizi del sistema di visione **Nautilus**.

---

## 1. Configurazione dell'Ambiente e Middleware

Prima di eseguire qualsiasi comando ROS 2, è indispensabile configurare l'ambiente e il middleware CycloneDDS:

```bash
# Sourcing della distribuzione ROS 2 e del workspace locale
source /opt/ros/jazzy/setup.bash
source ~/nautilus-vision-pipeline/ros2_ws/install/setup.bash

# Configurazione CycloneDDS (allineata a deploy/cyclonedds.xml e pipeline_config.env)
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID=42
export CYCLONEDDS_URI="file:///home/nautilus/nautilus-vision-pipeline/deploy/cyclonedds.xml"
```

---

## 2. Compilazione del Workspace (`colcon`)

Compilare sempre dalla directory radice del workspace (`ros2_ws`):

```bash
cd ~/nautilus-vision-pipeline/ros2_ws

# 1. Compilazione completa di tutti i pacchetti con symlink per Python/YAML
colcon build --symlink-install

# 2. Compilazione mirata per singolo pacchetto (più rapida)
colcon build --symlink-install --packages-select nautilus_perception
colcon build --symlink-install --packages-select nautilus_camera
colcon build --symlink-install --packages-select nautilus_common
colcon build --symlink-install --packages-select nautilus_msgs

# 3. Ricarica dell'ambiente post-compilazione
source install/setup.bash
```

---

## 3. Avvio dei Launch File

### 3.1 Acquisizione Telecamere Stereo (`nautilus_camera`)

```bash
# Avvio standard solo telecamere (5 FPS, senza debug/metriche)
ros2 launch nautilus_camera stereo_camera.launch.py

# Avvio telecamere con nodo di diagnostica attivo (stampa FPS, jitter, skew a log)
ros2 launch nautilus_camera stereo_camera.launch.py enable_metrics:=true

# Avvio con visualizzazione grafica affiancata OpenCV (richiede display)
ros2 launch nautilus_camera stereo_camera.launch.py metrics:=true display:=true
```

### 3.2 Detection e Stereovisione 3D (`nautilus_perception`)

```bash
# Avvio standard headless sopra le telecamere già attive
ros2 launch nautilus_perception detection.launch.py

# Avvio con finestra grafica OpenCV di debug (bounding box 2D e distanza Z)
ros2 launch nautilus_perception detection.launch.py enable_debug:=true

# Avvio con override del modello di inferenza e risoluzione
ros2 launch nautilus_perception detection.launch.py \
    model_filename_override:=best_416_fp32_openvino_model \
    imgsz_override:=416
```

### 3.3 Pipeline Integrata

```bash
# Avvio combinato di enhancement + detection (sopra le camere già accese)
ros2 launch nautilus_perception pipeline.launch.py \
    enable_enhancement:=true \
    enable_detection:=true

# Avvio completo da zero (inclusa l'acquisizione telecamere, utile a banco)
ros2 launch nautilus_perception pipeline.launch.py \
    include_stereo_camera:=true \
    enable_detection:=true \
    enable_enhancement:=false
```

---

## 4. Gestione dei Servizi di Produzione (`systemd`)

Sul Raspberry Pi di bordo, i flussi video sono regolati da servizi di sistema:

```bash
# Stato dei servizi di bordo
sudo systemctl status nautilus-vision.service
sudo systemctl status lock-cameras.service
sudo systemctl status nautilus-bag.service

# Riavvio dei servizi
sudo systemctl restart nautilus-vision.service

# Arresto per sessioni di benchmark o calibrazione
sudo systemctl stop nautilus-bag.service
sudo systemctl stop nautilus-vision.service
sudo systemctl stop lock-cameras.service

# Visualizzazione log telemetrici continui
journalctl -u nautilus-vision.service -f
journalctl -u lock-cameras.service -f
```

---

## 5. Ispezione dei Topic, Telemetria e QoS

```bash
# 1. Elenco dei nodi e dei topic attivi
ros2 node list
ros2 topic list

# 2. Visualizzazione in tempo reale dei target 3D rilevati (X, Y, Z in metri)
ros2 topic echo /stereo_down/targets

# 3. Visualizzazione scomposizione latenze per frame (pre, inferenza, post, totale ms)
ros2 topic echo /stereo_down/timings

# 4. Verifica throughput (frequenza effettiva FPS)
ros2 topic hz /stereo/lx/camera/image_raw
ros2 topic hz /stereo_down/targets

# 5. Verifica banda passante occupata (MB/s)
ros2 topic bw /stereo/lx/camera/image_raw

# 6. Verifica profili di comunicazione QoS effettivi sul topic
ros2 topic info /stereo/lx/camera/image_raw -v
ros2 topic info /stereo_down/targets -v

# 7. Ispezione della struttura dei messaggi
ros2 interface show vision_msgs/msg/Detection2DArray
ros2 interface show nautilus_msgs/msg/ArmCommand
```

---

## 6. Registrazione Dati ed Estrazione Frame

### 6.1 Registrazione Manuale Rosbag in Formato MCAP

```bash
# Registrazione dei flussi immagine compressi e dei target
ros2 bag record -s mcap \
    -o /home/nautilus/nautilus_bags/missione_01 \
    /stereo/lx/camera/image_raw/compressed \
    /stereo/rx/camera/image_raw/compressed \
    /stereo_down/targets
```

### 6.2 Estrazione Frame Post-Missione (`tools/extract_bag_frames.py`)

```bash
python3 tools/extract_bag_frames.py \
    --bag /home/nautilus/nautilus_bags/missione_01 \
    --out-dir /home/nautilus/immagini_estratte \
    --copy-calibration
```

---

## 7. Script di Benchmark e Stress Test (Fasi 6 e 7)

```bash
# Esecuzione benchmark prestazionale (singola run)
./benchmarks/run_benchmark.sh B2_ov_fp32 1

# Esecuzione stress test termico di 1 ora (3600 s) a box chiusa
./benchmarks/run_thermal_test.sh T_detection 1 3600

# Generazione grafici di benchmark Fase 6
python3 benchmarks/scripts/plot_results.py \
    --csv benchmarks/benchmark_results/csv_no_oc/ \
    --out benchmarks/benchmark_results/plots_no_oc/

# Generazione grafici stress test termico Fase 7
python3 benchmarks/scripts/plot_results_thermal.py \
    --csv benchmarks/thermal_results/csv/ \
    --out benchmarks/thermal_results/plots/
```
