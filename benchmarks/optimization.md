# Guida all'Ottimizzazione HW/SW: ROS 2 e YOLOv8 Subacqueo su Raspberry Pi 5 (Case Stagno)

Questo documento sintetizza le strategie di ottimizzazione prestazionale, termica e architetturale per far girare una pipeline ROS 2 pesante (Acquisizione, Enhancement, Detection) all'interno di un case di plastica stagna per applicazioni AUV/ROV subacquee.

---

## 1. Configurazione Firmware & Overclock Controllato (`config.txt`)

Poiché il Raspberry Pi 5 si trova in un ambiente stagno a dissipazione limitata, un overclock spinto porterebbe al throttling termico in pochi minuti. Si consiglia una configurazione **conservativa e bilanciata**.

### Modifica al file `/boot/firmware/config.txt`

```ini
[pi5]
# Overclock bilanciato della CPU (Base: 2.4 GHz -> Target: 2.8 GHz)
arm_freq=2800

# Overclock della GPU/V3D per pre-processing OpenCV/OpenCL (Base: 800 MHz -> Target: 1.0 GHz)
gpu_freq=1000

# Incremento minimo di tensione (+0.05V = 50000 uV)
over_voltage_delta=50000
```

> **Nota RAM:** La memoria LPDDR4X opera già a 4267 MHz e non è overcloccabile da firmware in modo sicuro.

---

## 2. Quantizzazione Modello: PyTorch vs OpenVINO (INT8)

Per ridurre il carico computazionale, la conversione del modello da **FP32** (32-bit floating point) a **INT8** (8-bit integer) tramite OpenVINO è il fattore chiave.

### Confronto Prestazioni Stimate (Raspberry Pi 5 @ 2.8 GHz)

| Formato Modello | Risoluzione Input | FPS Stimati | Uso CPU | Note / Impatto Termico |
| :--- | :--- | :--- | :--- | :--- |
| **PyTorch (FP32)** | $640 \times 640$ | ~8 - 12 FPS | 100% (4 Core) | Elevato rischio throttling termico |
| **OpenVINO (FP16)** | $640 \times 640$ | ~18 - 25 FPS | ~70-80% | Buona fluidità, carico medio |
| **OpenVINO (INT8)** | $640 \times 640$ | ~30 - 42 FPS | ~45-60% | **Consigliato:** Ottimo compromesso FPS/T° |
| **OpenVINO (INT8)** | $416 \times 416$ | ~45 - 60 FPS | ~35-45% | **Massima reattività per braccio robotico** |

### Esportazione del modello con Ultralytics

```bash
yolo export model=yolov8n.pt format=openvino int8=True imgsz=640
```

---

## 3. Architettura della Pipeline ROS 2 e Downscaling

Per garantire sia **dati ad alta qualità per analisi biologiche post-missione**, sia **bassa latenza per il controllo in tempo reale del braccio robotico**, le due pipeline vanno separate subito dopo l'enhancement.

### Schema della Pipeline

```text
                       ┌───────────────────────────────┐
                       │    Nodo 1: Acquisizione       │
                       │       (Camera 720p)           │
                       └───────────────┬───────────────┘
                                       │ Frame 720p Originale
                                       ▼
                       ┌───────────────────────────────┐
                       │      Nodo 2: Enhancement      │
                       │   (Correzione Colore/Nitidezza)│
                       └───────┬───────────────┬───────┘
                               │               │
      Frame 720p Elaborato     │               │ Frame 720p Elaborato
                               ▼               ▼
           ┌───────────────────────┐       ┌───────────────────────┐
           │   Salvataggio Locale  │       │   Downscale OpenCV    │
           │   (SD / NVMe per      │       │ (416x416 o 640x640)   │
           │    Biologi)           │       └───────────┬───────────┘
           └───────────────────────┘                   │ Frame Ridotto
                                                       ▼
                                           ┌───────────────────────┐
                                           │    Nodo 3: Detection  │
                                           │   (YOLOv8n OpenVINO)  │
                                           └───────────┬───────────┘
                                                       │ Coordinates / Bounding Box
                                                       ▼
                                                Braccio Robotico
```

### Impatto della Risoluzione sul Modello di Detection

* **Da $480\text{p}$ ($640\times480$) a $720\text{p}$ ($1280\times720$):**
  * Incremento dei pixel: **+200%** (da ~0.30 Mpx a ~0.92 Mpx).
  * Impatto sui FLOPs: Il carico di calcolo della rete cresce di **2.5x - 3x**.
  * **Conclusione:** Passare il frame a $720\text{p}$ direttamente a YOLO abbassa il framerate a 10-12 FPS e surriscalda la scheda. Il downscale a $416\times416$ o $640\times640$ prima del nodo di detection risolve il problema senza compromettere la presa del braccio robotico.

---

## 4. Gestione Termica nel Case Stagno Subacqueo

In un contenitore plastico stagna, l'aria interna agisce come isolante termico. La ventola classica muove solo aria calda senza dissiparla verso l'esterno.

1. **Dissipazione Passiva a Contatto:**
   * Utilizzare pad termici ad alta conducibilità per trasferire il calore dal SoC BCM2712 a un elemento metallico / flangia di alluminio in contatto diretto con la parete o con l'esterno a contatto con l'acqua (l'acqua marina/dolce funge da dissipatore infinito).
2. **Monitoraggio dello Stato di Throttling via SSH:**
   * Controllo temperatura: `vcgencmd measure_temp`
   * Controllo Throttling: `vcgencmd get_throttled` (deve restituire `0x0`).

---

## 5. Sintesi delle Azioni Immediate

1. **Firmware:** Impostare `arm_freq=2800` e `over_voltage_delta=50000` nel `config.txt`.
2. **Export Modello:** Convertire YOLOv8n nel formato OpenVINO `INT8` con dimensione $640\times640$ o $416\times416$.
3. **Pipeline ROS 2:** Implementare il salvataggio dei frame a $720\text{p}$ dopo l'enhancement ed eseguire il downscaling prima di passare i dati al nodo OpenVINO per la detection.
