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
2. All'inizio della funzione, imposta la modalità operativa e il percorso assoluto della tua foto:

    ```python
    WATERNET_MODE = 'force_on'  # Opzioni: 'auto', 'force_on', 'force_off'
    IMG_PATH = '/home/nautilus/nautilus-vision-pipeline/ros2_ws/src/nautilus_perception/nautilus_perception/enhancement/test.jpg'
    ```

3. Avvia il test da terminale:

    ```bash
    ros2 launch nautilus_perception local_test.launch.py
    ```

4. Il terminale stamperà il log dei tempi di elaborazione (Delay entrata-uscita). L'immagine elaborata verrà automaticamente salvata nella directory di esecuzione con il nome `output.jpg` (grazie al parametro `save_output=True` configurato nel launch file). Puoi anche visualizzare lo stream continuo aprendo un nuovo terminale e avviando `ros2 run rqt_image_view rqt_image_view` (selezionando il topic `/image_enhanced`).

*(Nota: È ancora possibile testare lo script Python puro senza l'infrastruttura ROS eseguendo `python3 main.py` all'interno della cartella `enhancement`, previa configurazione della variabile `MODE` a fine file)*.

---

### Benchmark di Riferimento (Raspberry Pi 5)

Durante i test di profilazione eseguiti sul target hardware (CPU ARM, no GPU), sono stati rilevati i seguenti carichi computazionali medi:

* **Modalità `force_on` (Pipeline Completa con WaterNet su CPU):**
* Latenza media: **~79.89 secondi per frame**

* Framerate effettivo: **0.0 FPS**

* *Conclusione:* Inutilizzabile per applicazioni in tempo reale su dispositivi embedded.

* **Modalità `force_off` (Pipeline Leggera solo OpenCV - Sharpening + CLAHE):**
* Latenza media: **~75.8 millisecondi per frame**

* Framerate effettivo: **Garantisce fluidità sufficiente per l'Object Detection** (il limite diventa la frequenza di scatto della telecamera).

---

## 2. Esecuzione in Produzione (Stereocamera)

Il nodo ROS 2 (`enhancement_node`) espone i seguenti parametri per configurare la pipeline in modo flessibile:

* `waternet_mode` (`auto`, `force_on`, `force_off`)
* `save_output` (bool, default: `False`): Se abilitato, salva continuamente l'ultimo fotogramma come `output.jpg` nella directory di lavoro (sconsigliato in produzione per non usurare la SD card).

### Avvio tramite file Launch (Metodo Consigliato)

Per l'utilizzo reale in acqua, la configurazione ottimale si imposta direttamente nel file `launch/enhancement.launch.py`. Modificando la variabile `WATERNET_MODE` in cima al file, configurerai simultaneamente sia la telecamera destra che quella sinistra:

```python
def generate_launch_description():
    # Imposta qui la modalità desiderata per entrambe le telecamere
    WATERNET_MODE = 'force_off' 

    lx_enhancement = Node(
        package='nautilus_perception',
        executable='enhancement_node',
        name='enhancement_node',
        namespace='stereo/lx',
        parameters=[{
            'waternet_mode': WATERNET_MODE,
            'save_output': False
        }],
        remappings=[('image_raw', 'camera/image_raw')],
        output='screen'
    )
```

Avvia quindi l'intera pipeline stereoscopica con:

```bash
ros2 launch nautilus_perception enhancement.launch.py
```

### Avvio manuale del singolo nodo (Debug da Terminale)

Se hai necessità di avviare un singolo nodo di elaborazione manualmente, puoi sovrascrivere il parametro passandolo come argomento ROS:

```bash
# Modalità Automatica
ros2 run nautilus_perception enhancement_node

# Forzatura modalità Leggera (No WaterNet)
ros2 run nautilus_perception enhancement_node --ros-args -p waternet_mode:="force_off"

# Forzatura WaterNet e salvataggio su disco
ros2 run nautilus_perception enhancement_node --ros-args -p waternet_mode:="force_on" -p save_output:=true
```
