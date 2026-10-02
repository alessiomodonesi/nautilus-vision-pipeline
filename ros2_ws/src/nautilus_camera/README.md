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

## Dipendenze Principali

* `camera_ros`
* `message_filters`
* `sensor_msgs`
* `cv_bridge`
