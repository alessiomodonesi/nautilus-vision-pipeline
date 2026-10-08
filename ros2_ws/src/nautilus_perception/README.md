# nautilus_perception

## Guida all'Uso del Nodo di Enhancement

Il modulo di enhancement delle immagini sottomarine è progettato per essere **modulare e adattivo**. Può eseguire una pipeline pesante (WaterNet + Sharpening + CLAHE) su macchine dotate di GPU, oppure una pipeline ultraleggera (Sharpening + CLAHE) su dispositivi embedded come il Raspberry Pi.

Il sistema supporta tre modalità operative:

* **`auto` (Default):** Rileva automaticamente l'hardware. Se trova CUDA o MPS attiva WaterNet, altrimenti usa la versione leggera per CPU.
* **`force_off`:** Disabilita forzatamente WaterNet, eseguendo solo CLAHE e Sharpening (massimi FPS, ideale per Object Detection su Raspberry).
* **`force_on`:** Forza l'esecuzione di WaterNet anche in assenza di GPU dedicata (utile per testare il carico computazionale e la latenza).

Di seguito le istruzioni per utilizzare il modulo sia per i benchmark locali che in produzione tramite ROS 2.

---

## 1. Test Locale e Benchmark (Tramite file di Launch)

Per testare la pipeline su una singola foto fissa simulando il comportamento completo del nodo in ROS 2, è disponibile un file di launch dedicato. Questo metodo pubblica ciclicamente l'immagine e ti permette di misurare esattamente il ritardo in millisecondi e gli FPS risultanti.

**Requisito:** Assicurati di avere installato il pacchetto per la pubblicazione di immagini statiche.

```bash
sudo apt update
sudo apt install ros-jazzy-image-tools
```

**Come eseguire il test:**

1. Apri il file `launch/local_test.launch.py` all'interno del tuo pacchetto.

2. All'inizio della funzione, imposta la modalità operativa e il percorso dell'immagine di test.

3. Avvia il test da terminale:

    ```bash
    ros2 launch nautilus_perception local_test.launch.py
    ```

4. Il terminale stamperà il log dei tempi di elaborazione (`Delay entrata-uscita`). L'immagine elaborata verrà automaticamente salvata nella home dell'utente (`~/enhancement_output.jpg`) grazie al parametro `save_output=True`.

---

### Benchmark di Riferimento (Raspberry Pi 5)

Durante i test di profilazione eseguiti sul target hardware (CPU ARM, no GPU), sono stati rilevati i seguenti carichi computazionali medi:

* **Modalità `force_on` (Pipeline Completa con WaterNet su CPU):**
* Latenza media: **~70,658.15 ms (~70.6 secondi per frame)**
* Framerate effettivo: **0.0 FPS**

* *Conclusione:* Inutilizzabile per applicazioni in tempo reale su dispositivi embedded.

* *Output di esempio:* `waternet_output.jpg`

* **Modalità `force_off` (Pipeline Leggera solo OpenCV - Sharpening + CLAHE):**
* Latenza media: **~65.3 - 67.1 ms per frame**
* Framerate effettivo: **~1.0 - 1.1 FPS** (con pubblicazione da file di test a 1Hz, salirebbe al limite della camera in streaming live)

* *Conclusione:* Prestazioni eccellenti e perfettamente compatibili con i vincoli di bordo per l'Object Detection.

* *Output di esempio:* `enhancement_output.jpg`

---

## 2. Risultati Visivi del Test Locale

Di seguito il confronto tra i file di output generati sulla home del Raspberry Pi nelle due modalità di test:

| Modalità WaterNet `force_off` (OpenCV) | Modalità WaterNet `force_on` (Rete Neurale) |
| :---: | :---: |
| ![Enhancement Off](nautilus_perception/data/test/enhancement_output.jpg) | ![WaterNet On](nautilus_perception/data/test/waternet_output.jpg) |
| *(File: `enhancement_output.jpg`)* | *(File: `waternet_output.jpg`)* |

---

## 3. Esecuzione in Produzione (Stereocamera)

Il nodo ROS 2 (`enhancement_node`) espone i parametri `waternet_mode` e `save_output` per configurare la pipeline in modo flessibile.

### Avvio tramite file Launch (Metodo Consigliato)

Per l'utilizzo reale in acqua, la configurazione ottimale si imposta direttamente nel file `launch/enhancement.launch.py`. Modificando la variabile `WATERNET_MODE` in cima al file su `'force_off'`, configurerai simultaneamente sia la telecamera destra che quella sinistra:

```bash
ros2 launch nautilus_perception enhancement.launch.py
```

---

## Guida al Nodo di Detection e Stereovisione

Il modulo di detection (`detection_node`) implementa un'architettura **"Detect-Then-Range"** ottimizzata per dispositivi edge (Raspberry Pi 5):

1. **Inferenza IA (Camera Sinistra):** Esegue il modello YOLOv8 Nano esclusivamente sul flusso sinistro rettificato per individuare i target ed estrarre i bounding box.
2. **Stima della Distanza (Stereo):** Sfrutta la geometria epipolare e un `SparseBlockMatcher` normalizzato per calcolare la disparità e stimare la distanza metrica tridimensionale ($Z$) sfruttando la calibrazione stereo (`stereo_calib.npz`).

### Configurazione (`detection_params.yaml`)

Il nodo legge i parametri di configurazione dal file `config/detection_params.yaml`:

* `input_type`: Seleziona il tipo di flusso in ingresso (`'raw'` per le immagini grezze o `'enhanced'` se si usa la pipeline di miglioramento).
* `conf_threshold`: Soglia di confidenza di YOLO (es. `0.2` o `0.3`).
* `model_path`: Gestito automaticamente in modo dinamico dal codice (supporta sia file `.pt` standard che modelli ottimizzati OpenVINO `.xml`).

---

## 1. Debug Visivo OpenCV

Per verificare in tempo reale l'efficacia del rilevamento e la correttezza della calibrazione stereo (evitando che riflessi o materiali trasparenti falsino la stima della distanza), è integrata una finestra grafica OpenCV di debug.

* **Cosa mostra:** L'immagine rettificata della camera sinistra con i bounding box arancioni di YOLO, il punto di campionamento verde e l'etichetta con la confidenza e la distanza metrica in metri ($Z$).
* **Come attivarla:** Tramite l'argomento di lancio `enable_debug:=true` nel file di lancio della detection.

---

## 2. Comandi di Test e Verifica della Pipeline

Di seguito trovi l'elenco completo dei comandi ROS 2 per compilare, avviare e testare l'intera catena di detection e stereovisione sul campo:

### Compilazione del Workspace

```bash
cd ~/nautilus-vision-pipeline/ros2_ws
colcon build --packages-select nautilus_perception
source install/setup.bash
```

### Avvio dell'Acquisizione Stereo

Avvia i driver delle due telecamere CSI (IMX708) con namespace e sincronizzazione dedicati:

```bash
ros2 launch nautilus_perception stereo_camera.launch.py
```

### Avvio del Nodo di Detection

Puoi avviare la detection in due modalità differenti:

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

### Monitoraggio dei Target Pubblicati

Per visualizzare in tempo reale i messaggi strutturati (`vision_msgs/Detection2DArray`) pubblicati sul topic dei target:

```bash
ros2 topic echo /stereo_down/targets
```
