# nautilus_perception

## Guida all'Uso del Nodo di Enhancement

Il modulo di enhancement delle immagini sottomarine è progettato per essere **modulare e adattivo**. Può eseguire una pipeline pesante (WaterNet + Sharpening + CLAHE) su macchine dotate di GPU, oppure una pipeline ultraleggera (Sharpening + CLAHE) su dispositivi embedded come il Raspberry Pi.

Il sistema supporta tre modalità operative:

* **`auto` (Default):** Rileva automaticamente l'hardware. Se trova CUDA o MPS attiva WaterNet, altrimenti usa la versione leggera per CPU.
* **`force_off`:** Disabilita forzatamente WaterNet, eseguendo solo CLAHE e Sharpening (massimi FPS, ideale per Object Detection su Raspberry).
* **`force_on`:** Forza l'esecuzione di WaterNet anche in assenza di GPU dedicata (utile per testare il carico computazionale e la latenza).

Di seguito le istruzioni per utilizzare il modulo sia in ambiente locale (standalone) che tramite ROS 2.

---

## 1. Test Locale (Senza ROS 2)

Puoi testare la pipeline di enhancement su una singola immagine locale per valutare la qualità visiva e misurare i tempi di esecuzione esatti sull'hardware corrente, senza dover avviare l'infrastruttura ROS.

1. Inserisci un'immagine sottomarina rinominata `test.jpg` nella stessa cartella dello script `main.py` (`nautilus_perception/enhancement/`).

2. Apri il file `main.py` e, alla fine del file nel blocco `if __name__ == "__main__":`, imposta la variabile `MODE`:

    ```python
    MODE = 'force_on'  # Opzioni: 'auto', 'force_on', 'force_off'
    ```

3. Esegui lo script da terminale:

    ```bash
    python3 main.py
    ```

4. Lo script stamperà nel terminale il tempo esatto impiegato per l'elaborazione e salverà il risultato nel file `test_output.jpg` nella stessa cartella.

---

## 2. Esecuzione tramite ROS 2

Il nodo ROS 2 (`enhancement_node`) espone il parametro `waternet_mode`, che permette di cambiare il comportamento della pipeline direttamente da riga di comando o dai file di launch, rendendo l'infrastruttura estremamente flessibile.

### Avvio in modalità Automatica (Consigliata)

Usa l'hardware migliore a disposizione.

```bash
ros2 run nautilus_perception enhancement_node
```

### Avvio forzando la modalità Leggera (No WaterNet)

Costringe il nodo a saltare la rete neurale, anche se la macchina dispone di una GPU. Questa è la configurazione suggerita per massimizzare il framerate prima di un nodo YOLO.

```bash
ros2 run nautilus_perception enhancement_node --ros-args -p waternet_mode:="force_off"
```

### Avvio forzando WaterNet su CPU

Obbliga il calcolo della rete neurale anche su dispositivi privi di accelerazione hardware (come il Raspberry Pi). Genera latenza elevata, ma è utile per scopi di debug o benchmark.

```bash
ros2 run nautilus_perception enhancement_node --ros-args -p waternet_mode:="force_on"
```

### Integrazione nel file Launch

Se desideri fissare una specifica modalità nel tuo file `enhancement.launch.py`, puoi passare il parametro direttamente nella definizione del nodo:

```python
Node(
    package='nautilus_perception',
    executable='enhancement_node',
    name='enhancement_node',
    namespace='stereo/lx',
    remappings=[('image_raw', 'camera/image_raw')],
    parameters=[{'waternet_mode': 'force_off'}], # <-- Parametro inserito qui
    output='screen'
)
```
