# Detection & Stereo Vision Core Library

Libreria Python di visione artificiale e stereovisione 3D integrata nel pacchetto [`nautilus_perception`](../README.md). Fornisce gli algoritmi matematici e i componenti di calcolo utilizzati dal nodo ROS 2 [`detection_node.py`](../detection_node.py) per la localizzazione tridimensionale dei target sottomarini.

---

## 1. Struttura del Modulo

```text
detection/
├── __init__.py
├── config.py                       # Dataclass StereoConfig con costanti geometriche calibrate
├── core_detection.py               # Algoritmi di matching epipolare e inferenza YOLO
├── DEBUG.md                        # Note dettagliate su calibrazione, offset lenti e troubleshooting
├── README.md                       # Questa documentazione
└── calibration/                    # Tooling completo di calibrazione e tuning ottico
    ├── charuco_common.py           # Definizioni condivise board ChArUco (8x11, 15/11 mm)
    ├── generate_charuco.py         # Generatore PDF/PNG del pattern di calibrazione
    ├── capture_calibration_pairs.py# Acquisizione coppie stereo con interfaccia grafica (GUI)
    ├── capture_calibration_pairs_web.py # Acquisizione headless via interfaccia web
    ├── stereo_calibrate.py         # Calcolo matrici intrinseche/estrinseche e mappe di rettifica
    └── find_focus.py               # Analisi nitidezza ottica (sweep LensPosition con Laplaciano)
```

---

## 2. Componenti Principali (`core_detection.py`)

### 2.1 `SparseBlockMatcher` (Algoritmo di Default per Distanza 3D)

Su dispositivi edge come il Raspberry Pi 5, il calcolo della mappa di disparità densa su tutti i pixel (StereoSGBM) richiede centinaia di millisecondi per frame, saturando la CPU.
La classe `SparseBlockMatcher` adotta invece un approccio **epipolare localizzato**:

1. **Ricerca Epipolare Monodimensionale**:
   Poiché le immagini stereo sono state preventivamente rettificate con le matrici di `stereo_calib_720p.npz`, i punti corrispondenti tra camera sinistra e destra giacciono sulla medesima riga orizzontale ($y_{sx} \approx y_{dx}$).
   La ricerca del patch di correlazione si riduce quindi a una scansione 1D lungo la coordinata $x$, con una tolleranza verticale ridotta a pochi pixel (`row_tolerance: 5`).
2. **Campionamento Multi-Punto Robusto (5 Punti)**:
   Invece di affidarsi a un singolo pixel centrale (soggetto a riflessi d'acqua, bolle o trasparenze dell'oggetto), il matcher estrae 5 patch distinti:
   - Centroide del bounding box $(u_c, v_c)$
   - Quattro campioni disposti sui semiassi a metà distanza dai bordi
3. **Calcolo della Disparità**:
   Per ciascun punto, viene eseguita una Normalized Cross-Correlation (NCC) su una patch quadrata di $31\times 31\text{ px}$ (`cv2.matchTemplate`). La disparità finale del target è la **mediana** delle disparità associate a match validi (punteggio NCC $> 0.6$).
4. **Triangolazione 3D**:
   Dalla disparità mediana $d$ vengono derivate le coordinate metriche tridimensionali nel sistema ottico della telecamera sinistra:
   $$Z = \frac{f_x \cdot B}{d}, \quad X = \frac{(u - c_x) \cdot Z}{f_x}, \quad Y = \frac{(v - c_y) \cdot Z}{f_y}$$
   dove $f_x = 1500.89\text{ px}$ e $B = 0.12017\text{ m}$.

### 2.2 `YoloDetector` (Motore di Rilevamento Oggetti)

Incapsula l'inferenza Ultralytics YOLOv8 con supporto trasparente per:

- Modelli standard PyTorch (`.pt`)
- Modelli OpenVINO esportati (`<name>_openvino_model/`) con runtime Intel OpenVINO

Il detector gestisce autonomamente il letterbox padding, la normalizzazione dei tensori, la soglia di confidenza (`conf_threshold`) e la Non-Maximum Suppression (NMS).

### 2.3 `DenseStereoMatcher` (Opzionale / Debug)

Implementa l'algoritmo di matching denso basato su `cv2.StereoSGBM` per la generazione di mappe di profondità full-frame, impiegato per la diagnostica visiva dell'allineamento geometrico delle telecamere.

---

## 3. Parametri Geometrici e Calibrazione (`config.py`)

La dataclass `StereoConfig` centralizza le costanti ottiche derivanti dalla calibrazione a 1280×720 eseguita sul banco ottico:

```python
@dataclass
class StereoConfig:
    # Geometria stereo calibrata (720p)
    baseline: float = 0.12017          # Distanza tra i centri ottici: 12.02 cm
    focal_length: float = 1500.89      # P1[0,0] rettificata (pixel)

    # Parametri Sparse Block Matching
    match_patch_size: int = 32         # Dimensione del template di confronto (pixel)
    match_search_range: int = 300      # Disparità massima cercata (pixel)
    match_row_tolerance: int = 6       # Tolleranza verticale epipolare (righe)
    match_min_confidence: float = 0.5  # Soglia minima punteggio NCC

    # Range operativo di disparità (SparseBlockMatcher)
    # Z_min ~0.40 m @ d=450 px, Z_max ~1.80 m @ d=100 px
    min_disparity: int = 100
    max_disparity: int = 450
```

---

## 4. Strumenti di Calibrazione (`calibration/`)

La sottocartella `calibration/` contiene la suite completa per la calibrazione stereo dei due sensori Raspberry Pi Camera Module 3:

### 1. Generazione Board ChArUco

```bash
python3 -m nautilus_perception.detection.calibration.generate_charuco
# Produce charuco_board.pdf (8x11 quadrati da 15 mm, marker 11 mm, DICT_4X4_50)
```

### 2. Cattura Coppie Stereo Sincronizzate

```bash
# Esecuzione server web headless su porta 8000
python3 -m nautilus_perception.detection.calibration.capture_calibration_pairs_web \
    --resolution 1280x720 \
    --lens-left 2.6 \
    --lens-right 1.5 \
    --outdir calib_pairs_720p
```

### 3. Calcolo Calibrazione Stereo

```bash
python3 -m nautilus_perception.detection.calibration.stereo_calibrate \
    --dir calib_pairs_720p \
    --out stereo_calib_720p.npz
```

La calibrazione in uso ha registrato un **RMS di reproiezione di 0.125 px** e una stima metrica Z con errore residuo inferiore a **1 cm** su distanze comprese tra 0.60 m e 0.90 m.

### 4. Verifica Fuoco e Offset Lenti (`find_focus.py`)

Esegue uno sweep automatico di `LensPosition` misurando la nitidezza ottica tramite varianza del Laplaciano:

- Telecamera Sinistra: fuoco ottimale a **2.6 diottrie**
- Telecamera Destra: fuoco ottimale a **1.5 diottrie**
- L'offset meccanico di +1.05 diottrie della lente sinistra è documentato in dettaglio in [`DEBUG.md`](DEBUG.md).
