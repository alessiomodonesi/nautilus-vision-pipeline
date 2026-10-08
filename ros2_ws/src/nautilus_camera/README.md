# nautilus_camera

Pacchetto ROS 2 dedicato all'acquisizione, al salvataggio e alla diagnostica del modulo di visione stereoscopica per il veicolo Nautilus (host Raspberry Pi).

## Funzionalità (Fase 1 - Acquisizione e Diagnostica)

Questo pacchetto si appoggia a `camera_ros` per interfacciarsi direttamente con l'hardware video e include strumenti per validare le prestazioni di acquisizione nativa in ROS 2.

### Launch Files

* **`stereo_camera.launch.py`**: Avvia simultaneamente due istanze del driver `camera_ros` (camera sinistra e camera destra). Configura i namespace separati (es. `/stereo/left`, `/stereo/right`), assegna i device ID corretti e applica i parametri hardware (risoluzione, formato pixel).

### Nodi

* **`metrics_node`**: Nodo diagnostico che si sottoscrive ai flussi d'immagine di entrambe le fotocamere per calcolare e stampare a terminale le metriche chiave:
  * **FPS reali:** Frequenza effettiva di arrivo dei fotogrammi.
  * **Jitter:** Varianza temporale tra l'arrivo di frame consecutivi della stessa camera.
  * **Skew temporale:** Disallineamento (delta assoluto) tra i timestamp dei messaggi accoppiati (sinistro/destro).
  
  **Parametri:**
  * `display` (bool, default: `false`): Se attivato (`true`), apre una finestra OpenCV per mostrare lo stream stereo affiancato con i dati in sovrimpressione. Se disattivato, il nodo esegue solo i calcoli matematici e stampa a terminale, annullando l'overhead grafico (consigliato per i benchmark).
  
  **Esempi di utilizzo:**
  * Esecuzione headless (tramite SSH / benchmark):

    ```bash
    ros2 run nautilus_camera metrics_node
    ```

  * Esecuzione con GUI video (richiede monitor fisico o sessione VNC attiva):
  
    ```bash
    ros2 run nautilus_camera metrics_node --ros-args -p display:=true
    ```

## Esecuzione dei Test e Risultati

Per avviare la pipeline hardware a nodo singolo e testare le metriche prestazionali (acquisizione nuda e cruda), eseguire in terminali separati:

1. **Avvio del driver di acquisizione stereoscopica:**

```bash
ros2 launch nautilus_camera stereo_camera.launch.py
```

2. **Verifica della frequenza effettiva sul topic:**

```bash
ros2 topic hz /stereo/lx/camera/image_raw
```

3. **Avvio del nodo di logging metriche (benchmark headless):**

```bash
ros2 run nautilus_camera metrics_node
```

**Risultati del test sul Raspberry Pi:**

* **FPS:** Stabili a **5.0 FPS** (in perfetto allineamento con i limiti hardware di 200000 µs configurati nel file di launch).
* **Jitter (sx):** Costante a **0.00 ms** (flusso video pulito, assenza di ritardi sul bus hardware).
* **Skew (sx-dx):** Compreso tra **1.00 ms e 1.50 ms** (sincronizzazione dei timestamp eccellente per la pipeline di visione).

> **Nota di Sistema (Calibrazione):** Durante l'avvio, il nodo `camera_ros` emette dei warning di errore relativi all'apertura del file `camera_info` (`.yaml`). Attualmente il sistema non dispone della calibrazione geometrica delle fotocamere (intrinseca ed estrinseca). La mancanza dei parametri di calibrazione non influisce sull'acquisizione dei flussi grezzi (`image_raw`) né sui benchmark di latenza sopra riportati.

## Dipendenze Principali

* `camera_ros`
* `message_filters`
* `sensor_msgs`
* `cv_bridge`
