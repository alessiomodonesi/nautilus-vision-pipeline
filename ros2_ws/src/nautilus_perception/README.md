# nautilus_perception

## Guida all'Uso del Nodo di Enhancement

Il modulo di enhancement delle immagini sottomarine è progettato per essere **modulare**. Può eseguire una pipeline pesante (WaterNet + Sharpening + CLAHE), utile solo in fase di post-produzione per i biologi, oppure una pipeline ultraleggera (Sharpening + CLAHE) pensata per l'object detection in tempo reale sul Raspberry Pi.

Il sistema supporta tre modalità operative:

* **`force_off` (Default):** disabilita WaterNet, esegue solo CLAHE e Sharpening. È il default perché WaterNet è una rete neurale che **non serve alla navigazione né alla detection**: consumerebbe solo batteria e potenza di calcolo sulla barca (Pi 5 o Jetson). Su Raspberry Pi la latenza misurata è di **~70 secondi per frame**, incompatibile con qualunque uso real-time.
* **`auto`:** rileva l'hardware. Se trova CUDA o MPS attiva WaterNet, altrimenti usa la versione leggera. Utile **solo su workstation di sviluppo** con GPU dedicata, dove WaterNet gira in tempi ragionevoli.
* **`force_on`:** forza WaterNet anche in assenza di GPU dedicata. Serve per rigenerare immagini a posteriori o per misurare il carico computazionale su hardware specifico, non per l'uso operativo.

**Regola pratica**: sulla barca si usa sempre `force_off`. WaterNet si attiva solo in post-produzione, su workstation, per le immagini destinate ai biologi.

Di seguito le istruzioni per utilizzare il modulo sia per i benchmark locali che in produzione tramite ROS 2.

---

## 1. Test Locale e Benchmark (Tramite file di Launch)

Per testare la pipeline su una singola foto fissa simulando il comportamento completo del nodo in ROS 2, è disponibile un file di launch dedicato. Questo metodo pubblica ciclicamente l'immagine e ti permette di misurare esattamente il ritardo in millisecondi e gli FPS risultanti.

**Requisito:** assicurati di avere installato il pacchetto per la pubblicazione di immagini statiche.

```bash
sudo apt update
sudo apt install ros-jazzy-image-tools
```

**Come eseguire il test:**

1. Apri il file `launch/local_test_enhancement.launch.py` all'interno del tuo pacchetto.

2. All'inizio della funzione, imposta la modalità operativa e il percorso dell'immagine di test.

3. Avvia il test da terminale:

    ```bash
    ros2 launch nautilus_perception local_test_enhancement.launch.py
    ```

4. Il terminale stamperà il log dei tempi di elaborazione (`Delay entrata-uscita`). L'immagine elaborata verrà automaticamente salvata nella home dell'utente (`~/enhancement_output.jpg`) grazie al parametro `save_output=True`.

---

### Benchmark di Riferimento (Raspberry Pi 5)

Durante i test di profilazione eseguiti sul target hardware (CPU ARM, no GPU), sono stati rilevati i seguenti carichi computazionali medi:

* **Modalità `force_on` (Pipeline Completa con WaterNet su CPU):**
* Latenza media: **~70,658.15 ms (~70.6 secondi per frame)**
* Framerate effettivo: **0.0 FPS**

* *Conclusione:* inutilizzabile per applicazioni in tempo reale su dispositivi embedded. Da qui la scelta di `force_off` come default.

* *Output di esempio disponibili in `benchmarks/datasets/images/waternet_output.jpg`.*

* **Modalità `force_off` (Pipeline Leggera solo OpenCV * Sharpening + CLAHE):**
* Latenza media: **~65.3 - 67.1 ms per frame**
* Framerate effettivo: **~1.0 - 1.1 FPS** (con pubblicazione da file di test a 1Hz, salirebbe al limite della camera in streaming live)

* *Conclusione:* prestazioni compatibili con i vincoli di bordo per l'object detection.

* *Output di esempio disponibili in `benchmarks/datasets/images/enhancement_output.jpg`.*

---

## 2. Esecuzione in Produzione (Stereocamera)

Il nodo ROS 2 (`enhancement_node`) espone i parametri `waternet_mode` e `save_output`.

### Default

Il default di `waternet_mode` è **`force_off`** in tutte e tre le sedi:

* `enhancement_node.py` (default hardcoded nel nodo)
* `enhancement.launch.py` (default del `DeclareLaunchArgument`)
* `pipeline.launch.py` (default passato al launch di enhancement)

Non ci sono valori divergenti: la scelta "sulla barca WaterNet non gira" è coerenza di configurazione, non solo di intenti.

### Avvio tramite file Launch

Per avviare l'enhancement sulla stereocamera:

```bash
# default: force_off (CLAHE + sharpening, adatto alla barca)
ros2 launch nautilus_perception enhancement.launch.py

# per uso su workstation con GPU, se vuoi sperimentare WaterNet
ros2 launch nautilus_perception enhancement.launch.py waternet_mode:=auto
```

Oppure, all'interno della pipeline completa (con detection a valle):

```bash
ros2 launch nautilus_perception pipeline.launch.py \
    enable_enhancement:=true \
    enable_detection:=true \
    waternet_mode:=force_off
```

---

## Sistema di QoS (Quality of Service)

I nodi di questo pacchetto (`enhancement_node` e `detection_node`) utilizzano i profili QoS centralizzati definiti nel pacchetto [`nautilus_common`](../nautilus_common/README.md) per garantire l'allineamento con il resto della pipeline.

* **Immagini (`IMAGE_QOS`)**: Iscrizioni e pubblicazioni dei flussi video usano `BEST_EFFORT` (depth 5). Questo previene colli di bottiglia di rete e garantisce che l'enhancement e la detection non siano bloccati da logiche di ritrasmissione dei frame persi.
* **Target (`DETECTION_QOS`)**: Il topic `/stereo_down/targets` usa `RELIABLE` (depth 10). Poiché rappresenta l'output finale per la logica di bordo, un target rilevato non deve mai andare perso.
* **Telemetria (`DEBUG_QOS`)**: Il topic `/stereo_down/timings` usa `BEST_EFFORT`. I dati sulle prestazioni (pre/inferenza/post) sono diagnostici e la loro eventuale perdita non deve impattare la pipeline.

---

## Guida al Nodo di Detection e Stereovisione

Il modulo di detection (`detection_node`) implementa un'architettura **"Detect-Then-Range"** ottimizzata per dispositivi edge (Raspberry Pi 5):

1. **Inferenza IA (Camera Sinistra):** esegue il modello YOLOv8 Nano esclusivamente sul flusso sinistro rettificato per individuare i target ed estrarre i bounding box.
2. **Stima della Distanza (Stereo):** sfrutta la geometria epipolare e un `SparseBlockMatcher` normalizzato per calcolare la disparità e stimare la distanza metrica tridimensionale (Z) sfruttando la calibrazione stereo (`stereo_calib_720p.npz`).

### Configurazione (`detection_params.yaml`)

Il nodo legge i parametri di configurazione dal file `config/detection_params.yaml`:

* `model_filename`: file `.pt` o directory OpenVINO in `data/weights/`. Gestito dinamicamente dal nodo.
* `input_type`: seleziona il tipo di flusso in ingresso (`'raw'` per le immagini grezze o `'enhanced'` se si usa la pipeline di miglioramento). Sovrascritto dinamicamente da `pipeline.launch.py` in base a `enable_enhancement`.
* `conf_threshold`: soglia di confidenza di YOLO.
* `enable_debug`: apre finestra OpenCV di debug. Default `false`; sovrascrivibile con `enable_debug:=true` al lancio.
* `half_res`: dimezza il frame prima di YOLO. Deve essere `false` per OpenVINO.
* `imgsz`: risoluzione di inferenza, deve combaciare con l'export del modello.

**Nota sui default**: il launch file `detection.launch.py` sovrascrive **sempre** `input_type`, `enable_debug`, `model_filename`, `half_res`, `imgsz` con i propri `DeclareLaunchArgument`. Per modificare questi valori, o si aggiornano i default in `detection.launch.py`, o si passano come argomenti al lancio. Gli altri parametri (`conf_threshold`, `num_threads`, `sync_slop_sec`) restano invece quelli del YAML.

---

## 1. Debug Visivo OpenCV

Per verificare in tempo reale l'efficacia del rilevamento e la correttezza della calibrazione stereo (evitando che riflessi o materiali trasparenti falsino la stima della distanza), è integrata una finestra grafica OpenCV di debug.

* **Cosa mostra:** l'immagine rettificata della camera sinistra con i bounding box arancioni di YOLO, il punto di campionamento verde e l'etichetta con la confidenza e la distanza metrica in metri (Z).
* **Come attivarla:** tramite l'argomento di lancio `enable_debug:=true` nel file di lancio della detection.

---

## 2. Comandi di Test e Verifica della Pipeline

Di seguito trovi l'elenco completo dei comandi ROS 2 per compilare, avviare e testare l'intera catena di detection e stereovisione sul campo.

### Compilazione del Workspace

```bash
cd ~/nautilus-vision-pipeline/ros2_ws
colcon build --packages-select nautilus_perception
source install/setup.bash
```

### Avvio dell'Acquisizione Stereo

Avvia i driver delle due telecamere CSI (IMX708) con namespace e sincronizzazione dedicati:

```bash
ros2 launch nautilus_camera stereo_camera.launch.py
```

**Nota**: se le camere sono già attive dal boot (caso normale sulla barca, gestito da `nautilus-vision.service`), **non** rilanciare questo comando: va in errore per nodo duplicato. Salta direttamente alla sezione "Avvio del Nodo di Detection".

### Avvio del Nodo di Detection

Puoi avviare la detection in due modalità differenti.

* **Modalità Standard (Headless / Performance Piene):**

Ideale per benchmark di stress termico o esecuzione su barchino senza monitor collegato:

```bash
ros2 launch nautilus_perception detection.launch.py
```

* **Modalità con Debug Visivo OpenCV (GUI attiva):**

Ideale per la calibrazione e la verifica visiva sul campo (richiede schermo locale o X11 forwarding):

```bash
ros2 launch nautilus_perception detection.launch.py enable_debug:=true
```

Se invece vuoi lanciare detection + enhancement in un colpo solo, sopra le camere già attive:

```bash
ros2 launch nautilus_perception pipeline.launch.py \
    enable_detection:=true \
    enable_enhancement:=true
```

### Monitoraggio dei Target Pubblicati

Per visualizzare in tempo reale i messaggi strutturati (`vision_msgs/Detection2DArray`) pubblicati sul topic dei target:

```bash
ros2 topic echo /stereo_down/targets
```

---

## Riepilogo delle correzioni

**`global_launch.md`:**

* Sezione 1: chiarito che solo acquisizione (+ salvataggio opzionale) parte al boot.
* Sezione 2: rimosso il riferimento a `ENABLE_ENHANCEMENT` / `ENABLE_DETECTION` / `ENABLE_METRICS`. Ora c'è solo `ENABLE_SAVING`. Aggiunto blocco che mostra cosa fa `start_pipeline.sh`.
* Sezione 3: aggiornato il YAML con i parametri fotometrici mancanti. Aggiornato `save_directory`.
* Sezione 4: aggiunta nota sul doppio livello di override (YAML + launch sempre attivo sui 5 parametri).
* Sezione 5: aggiunti esempi per `pipeline.launch.py` con `include_stereo_camera`, con spiegazione del perché di default è `false`.
* Sezione 6: riscritta per includere `lock-cameras.service` e spiegare come `lock_cameras.py` legge il YAML.
* Sezione 7: aggiornati gli esempi di test (niente più riferimenti a env var inesistenti).
* Sezione 9: aggiunte due righe di troubleshooting ("node already exists", lens position non applicata).

**`ros2_ws/README.md`:**

* Aggiunta sezione "Cosa parte automaticamente al boot".
* Aggiunto PyYAML tra le dipendenze.
* Chiarito che WaterNet è disabilitata di default e perché.
* Corretto l'esempio di avvio.

**`nautilus_camera/README.md`:**

* Corretto `enable_metrics` default: `false` (non `true`).
* Corretto `save_directory` default: `/home/nautilus/nautilus_data` (non `/home/pi/...`).
* Aggiunti i parametri fotometrici nel YAML di esempio.
* Aggiunta sezione "Perché i parametri fotometrici sono nel YAML" con riferimento a `lock_cameras.py`.
* Aggiunta riga di troubleshooting per lens position.

**`nautilus_perception/README.md`:**

* Cambiato il default di WaterNet da `auto` a `force_off` con spiegazione.
* Rimossa la menzione a `WATERNET_MODE` (variabile inesistente in `enhancement.launch.py`): il launch arg è `waternet_mode`.
* Aggiunta sezione "Default" per chiarire che il valore è coerente in tre file.
* Aggiunta nota sul doppio livello di override in detection.
* Aggiunto warning di non rilanciare `stereo_camera.launch.py` se le camere sono già attive dal boot.
