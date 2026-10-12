# Guida al Lancio Globale della Pipeline Nautilus Vision

Questo documento descrive il funzionamento del sistema di lancio globale della pipeline ROS 2 per il progetto Nautilus, spiegando come configurare l'esecuzione dinamica dei nodi, gestire i parametri e avviare il sistema.

## 1. Architettura del Lancio Globale

Il cuore del sistema è il file `pipeline.launch.py` (situato in `ros2_ws/src/nautilus_perception/launch/`). Questo script non si limita ad avviare staticamente i nodi, ma utilizza le **Launch Conditions** e i **Launch Arguments** di ROS 2 per orchestrare la pipeline in base alle tue esigenze di test (es. Benchmark e Stress Test termico).

La pipeline è composta da tre blocchi principali:

1. **Acquisizione (`stereo_camera.launch.py`):** Sempre attivo. Avvia le fotocamere destra e sinistra.
2. **Enhancement (`enhancement.launch.py`):** Condizionale. Migliora le immagini raw tramite Sharpening + CLAHE.
3. **Detection (`detection.launch.py`):** Condizionale. Esegue l'inferenza YOLO e la stereovisione.

## 2. Configurazione Globale (`pipeline_config.env`)

Invece di modificare il codice ROS 2 per ogni test, il comportamento della pipeline è governato da un file di ambiente posizionato nella radice del progetto:

**Percorso:** `~/nautilus-vision-pipeline/pipeline_config.env`

```bash
# pipeline_config.env
# Imposta a 'true' o 'false' per configurare l'esecuzione della pipeline

ENABLE_ENHANCEMENT=true
ENABLE_DETECTION=true
```

Lo script di avvio principale (`start_pipeline.sh`) legge questo file e passa dinamicamente i valori a `pipeline.launch.py`.
Inoltre, il launch file **valuta in automatico il tipo di input** per la detection:

* Se `ENABLE_ENHANCEMENT=true`, la detection riceverà l'argomento `input_type_override='enhanced'`.
* Se `ENABLE_ENHANCEMENT=false`, riceverà `input_type_override='raw'`.

## 3. Parametri del Nodo di Detection (`detection_params.yaml`)

I parametri specifici dell'algoritmo di visione risiedono nel file YAML dedicato.

**Percorso:** `ros2_ws/src/nautilus_perception/config/detection_params.yaml`

```yaml
detection_node:
  ros__parameters:
    model_filename: 'yolov8n.pt' # o 'yolov8n_openvino_model'
    conf_threshold: 0.4          # Soglia di confidenza al 40%
    input_type: 'raw'            # Fallback (sovrascritto dinamicamente dal file .env)
    enable_debug: True           # Mostra la finestra OpenCV
    half_res: True               # False obbligatorio per OpenVINO
    num_threads: 2               # Core logici dedicati all'inferenza CPU/OpenVINO
```

### Note importanti sui parametri

* **`num_threads`**: È cruciale per i benchmark termici e prestazionali sul Raspberry Pi 5. Il nodo legge questo parametro e imposta le variabili di sistema `OMP_NUM_THREADS` e `MKL_NUM_THREADS` *prima* di caricare il modello, garantendo che le risorse CPU non vengano saturate in modo incontrollato.
* **Routing automatico dei Topic**: In base all'`input_type` ricevuto, il nodo Python si collegherà automaticamente ai namespace corretti (`/stereo/lx/camera/image_raw` per il raw, oppure `/stereo/lx/image_enhanced` per l'enhanced), prevenendo deadlock in cui il nodo attende topic inesistenti.

## 4. Come Compilare e Avviare

Ogni volta che modifichi i file Python o i `.launch.py`, devi ricompilare il workspace:

```bash
cd ~/nautilus-vision-pipeline/ros2_ws
colcon build --symlink-install
source install/setup.bash
```

*(Nota: L'uso di `--symlink-install` permette di modificare i file Python non compilati e i launch file e vedere le modifiche al prossimo avvio senza dover rifare la build, ma è sempre buona pratica ricompilare dopo modifiche strutturali).*

### Avvio tramite Script Bash

Per avviare la pipeline manualmente nel terminale (utile durante il debug):

```bash
cd ~/nautilus-vision-pipeline
./scripts/start_pipeline.sh
```

### Avvio tramite Servizio Systemd

Il Raspberry Pi è configurato per lanciare la pipeline in automatico all'avvio. Se modifichi il file `.env` e vuoi applicare subito le modifiche senza riavviare la scheda:

```bash
sudo systemctl restart nautilus-vision.service
```

Per controllare i log di ROS 2 e verificare quanti FPS stai raggiungendo, oppure controllare i log della detection:

```bash
journalctl -u nautilus-vision.service -f
```

## 5. Esempi di Configurazione per i Test (Fase 5 e 6)

1. **Test: Solo Acquisizione (Baseline hardware)**
   * Nel `.env`: `ENABLE_ENHANCEMENT=false`, `ENABLE_DETECTION=false`
2. **Test: Acquisizione + Detection (Nessun pre-processing)**
   * Nel `.env`: `ENABLE_ENHANCEMENT=false`, `ENABLE_DETECTION=true`
   * Nel `.yaml`: imposta `num_threads` desiderato.
3. **Test: Full Pipeline**
   * Nel `.env`: `ENABLE_ENHANCEMENT=true`, `ENABLE_DETECTION=true`
