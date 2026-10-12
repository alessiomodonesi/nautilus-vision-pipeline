# Nautilus — Detection Module (Debug & Status Notes)

> **Ultimo aggiornamento:** 12/10/2026 — Sessione di debug stereo Z = 0.00m
> **Stato:** Pipeline detection funzionante per benchmark; calibrazione stereo
> rimandata (Fase 9 in `docs/TODO.md`).

---

## 1. Architettura del modulo

Il nodo `detection_node` implementa un'architettura **Detect-Then-Range**:

1. **Inferenza IA** (YOLOv8 Nano / OpenVINO) sul frame **sinistro** rettificato
2. **Stima distanza** via `SparseBlockMatcher` (NCC epipolare localizzata)
3. **Pubblicazione** su `/stereo_down/targets` (`vision_msgs/Detection2DArray`)

Componenti principali:

| File | Ruolo |
| --- | --- |
| `detection_node.py` | Nodo ROS 2: sincronizzazione stereo, rectification, publishing |
| `core_detection.py` | Implementazione matcher (`SparseBlockMatcher`) e detector (`YoloDetector`) |
| `config.py` | Parametri hardware (`baseline`, `focal_length`) |
| `calibration/` | Tooling per ricalibrazione a 720p (non ancora eseguita) |
| `../../config/detection_params.yaml` | Parametri runtime del nodo |

---

## 2. Problemi noti e soluzioni applicate

### ✅ Risolto — Camera `AE/AWB` non bloccati

**Sintomo:** distanza Z oscillava tra `0.00 m` e valori casuali, con la GUI che
mostrava `Z: 0.00m` anche con oggetto textureato a distanza nota.

**Causa:** `camera_ros` **non applica i parametri AE/AWB passati dal launch file**
(bug noto del driver su Raspberry Pi 5). Le due camere restavano in auto-exposure
indipendenti, convergendo a valori fotometrici diversi. Il matcher NCC falliva
silenziosamente (`max_val < 0.5`) perché le due immagini non erano confrontabili.

**Soluzione:** lock dei parametri **a runtime** dopo l'avvio delle camere tramite
`lock_cameras.sh` (vedi Sezione 4). I valori di `AeEnable=False`,
`ExposureTime=20000`, `ColourGains=[1.5,1.5]` devono essere **identici** su
`lx` e `rx`.

**Nota su `AnalogueGain`:** `camera_ros` rifiuta `AnalogueGain` sul sensore
IMX708 quando impostato a un valore fuori dal range accettato — e rifiutando
il singolo parametro invalido, **rigetta l'intero batch**, lasciando tutti gli
altri parametri non applicati (compreso `AeEnable`). Questo è il motivo per
cui il launch file non funziona: `AnalogueGain: 1.0` fa fallire l'intero
caricamento. Il campo è stato **rimosso dal launch file e dallo script di lock**;
libcamera lo auto-converge allo stesso valore su entrambe le camere
(verificato: `1.1228` su `lx` e `rx`), quindi non serve forzarlo.

### ✅ Risolto — Campionamento a punto singolo instabile

**Sintomo:** match NCC intermittenti.

**Soluzione:** `detection_node.py` campiona **5 punti** (centro + 4 assi) per
ogni bounding box e prende la mediana, scartando gli outlier.

### ✅ Risolto — Autofocus non allineato

**Sintomo:** camera sinistra visibilmente più sfocata della destra con
`LensPosition=1.0` su entrambe.

**Causa:** tolleranza meccanica tra gli obiettivi dei due moduli IMX708.

**Soluzione:** valori `LensPosition` **diversi** per camera: `lx=3.0`, `rx=1.0`.
Non è un problema — le due lenti fisiche hanno offset diversi. Va però impostato
`AfMode=0` (manuale) per evitare che l'AF modifichi la focale tra cattura e
produzione.

### ⚠️ Non risolto — Mismatch risoluzione calibrazione/streaming

**Stato attuale:**

```text
stereo_calib.npz    →  mappe (480, 640),  image_size = [640, 480]
streaming camere    →  1280×720
```

Le mappe di rettifica sono state calibrate a **640×480**, ma le camere girano a
**1280×720**. Applicare le mappe a frame 720p produce una rettifica
geometricamente invalida:

- Le righe epipolari **NON sono allineate** → NCC cerca nella riga sbagliata
- La distanza Z ha **bias sistematico del ~30%** (tipicamente sottostimata:
  ~0.7 m invece di 1.0 m reale)
- Il campo visivo utile si riduce al quadrante in alto a sinistra

**Impatto sul benchmark:**

- ❌ Misurazione di **accuratezza metrica di Z**: non valida
- ✅ Misurazione di **timing** (FPS, latenza, CPU, RAM): non influenzata
- ✅ **mAP** della detection YOLO: non influenzata

**Soluzione pianificata:** ricalibrazione completa a 1280×720. Il tooling è
pronto (Fase 9 in `docs/TODO.md`), l'esecuzione è rimandata a dopo il benchmark.

---

## 3. Workflow operativo (post-fix)

### 3.1 Avvio delle camere

```bash
ros2 launch nautilus_camera stereo_camera.launch.py \
    enable_saving:=false enable_metrics:=true
```

Il launch file applica già i parametri AE/AWB, ma come documentato in Sezione 2
questi **non prendono** su `camera_ros`. Vanno riapplicati a runtime.

### 3.2 Lock fotometrico a runtime

```bash
# In un terminale separato, con le camere attive
./lock_cameras.sh
```

Lo script (in `scripts/lock_cameras.sh` o nella root del workspace):

```bash
#!/bin/bash
# lock_cameras.sh — imposta parametri di lock fotometrico su entrambe le camere
source /opt/ros/jazzy/setup.bash
source "$HOME/nautilus-vision-pipeline/ros2_ws/install/setup.bash"

sleep 3   # discovery

declare -A LENS_POS
LENS_POS[lx]=3.0
LENS_POS[rx]=1.0

for ns in lx rx; do
  node="/stereo/${ns}/camera"
  if ! ros2 node list 2>/dev/null | grep -q "^${node}$"; then
    echo "[ERROR] $node not found"
    exit 1
  fi
  ros2 param set "$node" AeEnable     false
  ros2 param set "$node" AwbEnable    false
  ros2 param set "$node" ExposureTime 20000
  ros2 param set "$node" ColourGains  "[1.5, 1.5]"
  ros2 param set "$node" AfMode       0
  ros2 param set "$node" LensPosition "${LENS_POS[$ns]}"
  echo "[OK] $node locked"
done
```

### 3.3 Verifica rapida

```bash
ros2 param get /stereo/lx/camera AeEnable        # atteso: False
ros2 param get /stereo/rx/camera AeEnable        # atteso: False
ros2 param get /stereo/lx/camera ExposureTime    # atteso: 20000
ros2 param get /stereo/rx/camera ExposureTime    # atteso: 20000
ros2 param get /stereo/lx/camera LensPosition    # atteso: 3.0
ros2 param get /stereo/rx/camera LensPosition    # atteso: 1.0
```

Confronto visivo con `rqt_image_view` sui due topic `image_raw`: le immagini
devono essere visivamente identiche per luminosità e colore.

### 3.4 Lancio detection

```bash
ros2 launch nautilus_perception detection.launch.py
```

Con GUI:

```bash
ros2 launch nautilus_perception detection.launch.py enable_debug:=true
```

---

## 4. Parametri di configurazione rilevanti

### `config.py`

```python
@dataclass
class StereoConfig:
    baseline: float = 0.12         # ⚠️ valore non calibrato
    focal_length: float = 1114.0   # ⚠️ valore non calibrato
    ...
```

**Nota:** questi valori sono **placeholder** che non corrispondono alla
calibrazione reale (che è a 640×480, con `baseline=0.1217` e `focal_length=1082.5`).
Vanno aggiornati dopo la ricalibrazione a 720p (Fase 9).

### `SparseBlockMatcher.__init__`

```python
self.min_disparity = 15
self.max_disparity = 500    # range per f=1114, B=0.12: Z in [0.27, 8.9] m
self.patch_size = 25
self.row_tolerance = 3
self.min_confidence = 0.5
```

Dopo la ricalibrazione a 720p (focale raddoppiata a ~2165 px), aggiornare:

```python
self.min_disparity = 20
self.max_disparity = 400    # Z in [0.66, 13] m a f=2165, B=0.122
self.patch_size = 41        # patch più grande = NCC più stabile
self.row_tolerance = 5      # tollera imperfezioni di rettifica
self.min_confidence = 0.65  # scarta match deboli
```

---

## 5. Tooling di calibrazione (pronto, non eseguito)

Tutti gli script sono in `calibration/`:

| Script | Ruolo |
| --- | --- |
| `generate_charuco.py` | Genera board ChArUco 8×11, 15/11 mm, `DICT_4X4_50` |
| `capture_calibration_pairs.py` | Cattura coppie L/R (GUI, richiede display) |
| `capture_calibration_pairs_web.py` | Cattura coppie L/R (headless, browser) |
| `stereo_calibrate.py` | Genera `stereo_calib.npz` dalle coppie |
| `charuco_common.py` | Utility condivise (board + detector) |

### 5.1 Board ChArUco

Parametri coerenti con `charuco_common.py`:

- Griglia: **8×11** quadrati
- Dimensione quadrato: **15 mm**
- Dimensione marker: **11 mm**
- Dizionario: **`DICT_4X4_50`**
- `legacy_pattern=True`
- Dimensioni fisiche: **120 × 165 mm**

Generazione:

```bash
python3 generate_charuco.py
# Output: charuco_board.pdf + charuco_board.png
```

Stampare a **scala 100%** su carta opaca, verificare con righello che un
quadrato misuri **15 mm**, incollare su supporto rigido.

### 5.2 Cattura coppie

Fermare prima le camere (`Ctrl+C` su `stereo_camera.launch.py`), poi:

```bash
cd ros2_ws/src/nautilus_perception/nautilus_perception/detection
python3 -m calibration.capture_calibration_pairs_web \
    --resolution 1280x720 --lens-left 3.0 --lens-right 1.0
```

Aprire `http://<ip-del-pi>:8000` da browser. Catturare **30–40 coppie** con
**varietà di tilt** (angolare la board, non solo traslarla). L'overlay deve
essere **verde (READY)** prima di ogni scatto.

### 5.3 Ricalibrazione

```bash
python3 -m calibration.stereo_calibrate --dir calib_pairs --out stereo_calib_720p.npz
```

Verificare nell'output:

- Per-camera RMS < 1.0 px
- Stereo RMS < 1.0 px

Estrarre i valori:

```bash
python3 -c "
import numpy as np
c = np.load('stereo_calib_720p.npz')
print('image_size:', c['image_size'])          # atteso [1280, 720]
print('map shape:', c['map1x'].shape)          # atteso (720, 1280)
print('baseline_m:', float(c['baseline_m']))
print('P1[0,0] (rectified focal):', float(c['P1'][0,0]))
"
```

Sostituire in `config.py`:

```python
baseline: float = <baseline_m>
focal_length: float = <P1[0,0]>
```

---

## 6. Checklist di stato

| Item | Stato |
| --- | --- |
| Detection YOLO funzionante | ✅ |
| Pubblicazione `/stereo_down/targets` | ✅ |
| Input raw/enhanced configurabile | ✅ |
| Lock AE/AWB a runtime (workaround) | ✅ |
| Multi-point sampling (5 punti + mediana) | ✅ |
| LensPosition allineato (lx=3.0, rx=1.0) | ✅ |
| Mappe rettifica a risoluzione corretta | ❌ (640×480 vs 1280×720) |
| Accuratezza Z validata | ❌ (dipende dalla ricalibrazione) |
| Benchmark FPS/latenza/CPU (Fase 5) | ⏳ |

---

## 7. Riferimenti

- `docs/TODO.md` — Roadmap completa (Fase 9 per calibrazione)
- `detection_params.yaml` — Parametri runtime del nodo
- `scripts/lock_cameras.sh` — Lock fotometrico post-launch
- `calibration/README.md` — Dettagli sulla calibrazione (se presente)
