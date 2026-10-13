# Nautilus — Detection Module (Debug & Status Notes)

> **Ultimo aggiornamento:** 13/10/2026 — Test focus + prep calibrazione 720p
> **Stato:** LensPosition di produzione fissate (lx=2.6, rx=1.5). Calibrazione
> stereo 720p in corso (Fase 9).

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
lo script `deploy/lock_cameras.py`, invocato automaticamente dal servizio
systemd `lock-cameras.service` (vedi Sezione 3.2). I valori di `AeEnable=False`,
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

> **Nota (13/10/2026):** questi valori (`lx=3.0, rx=1.0`) sono stati **superati**
> dal test `find_focus.py`. Vedi Sezione 3.2 per i valori attuali (`lx=2.6,
> rx=1.5`), che mettono a fuoco entrambe le camere a ~0.65 m e riflettono
> l'offset reale della lente sinistra.

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

Valori attuali (aggiornati 13/10/2026 dopo test `find_focus.py`):

| Camera | LensPosition | Fuoco effettivo |
| --- | --- | --- |
| lx | 2.6 | ~0.65 m |
| rx | 1.5 | ~0.65 m |

**Nota (13/10/2026):** la camera sinistra mostra un offset di **+1.05 diottrie**
rispetto al valore teorico `1/d` (verificato su 3 distanze: 0.40, 0.65, 0.90 m
con `calibration/find_focus.py`). La destra è nominale (picco ≈ teorico).
La pulizia della lente con alcol isopropilico ha migliorato la nitidezza di
entrambe (+20-27%) ma non ha corretto l'offset, che è di natura meccanica.

**Impatto:** la sinistra ha sharpness ~50% della destra fuori dal picco
(0.40 m e 0.90 m), quindi il range utile di calibrazione è **0.50–0.85 m**,
più stretto del range di lavoro teorico del braccio (0.40–1.10 m).

**Da valutare:** sostituzione del modulo IMX708 sinistro (~30€) se la
differenza di nitidezza off-peak causa problemi in produzione.

**Script di verifica:** `calibration/find_focus.py` (sweep di LensPosition
con metrica di sharpness = varianza del Laplaciano). Esempi di run:

```bash
python3 -m calibration.find_focus --distance 0.65 --sweep 1.6 --steps 12
```

### 3.3 Lancio detection

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

**Aggiornamento (13/10/2026):** la calibrazione a 720p è in corso. Quando
completata, sostituire i due valori con quelli estratti da `stereo_calib.npz`
(campo `baseline_m` e `P1[0,0]`). Vedi Sezione 5.3.

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

## 5. Tooling di calibrazione (pronto, in esecuzione)

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
python3 -m calibration.capture_calibration_pairs_web \
    --resolution 1280x720 --lens-left 2.6 --lens-right 1.5 \
    --outdir calib_pairs_720p
```

Aprire `http://<ip-del-pi>:8000` da browser.

**Range di cattura:** 0.50 – 0.85 m (limitato dall'offset della lente sinistra,
vedi Sezione 3.2). Distribuzione consigliata su 36 coppie:

| Fascia | Distanza | Coppie |
| --- | --- | --- |
| Vicino | 0.50 – 0.60 m | 8 |
| Target | 0.60 – 0.75 m | 16 |
| Lontano | 0.75 – 0.85 m | 12 |

### 5.3 Ricalibrazione

```bash
python3 -m calibration.stereo_calibrate --dir calib_pairs_720p --out stereo_calib_720p.npz
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
| LensPosition di produzione (lx=2.6, rx=1.5) | ✅ |
| Offset lente sinistra documentato (+1.05 diottrie) | ✅ |
| Modulo IMX708 sinistro candidato a sostituzione | ⏳ |
| Mappe rettifica a risoluzione corretta | ❌ (640×480 vs 1280×720) |
| Calibrazione 720p eseguita (RMS < 1.0 px) | ⏳ (in corso) |
| Validazione Z metrica su 3 distanze (0.5, 1.0, 2.0 m) | ❌ (dopo calibrazione) |
| Benchmark FPS/latenza/CPU (Fase 5) | ⏳ |

---

## 7. Riferimenti

- `docs/TODO.md` — Roadmap completa (Fase 9 per calibrazione)
- `detection_params.yaml` — Parametri runtime del nodo
- `deploy/lock_cameras.py` — Lock fotometrico post-launch (systemd)
- `deploy/lock-cameras.service` — Unit systemd che lo invoca
- `deploy/nautilus-vision.service` — Unit systemd della pipeline (a cui `lock-cameras` è agganciata via `PartOf`)
- `calibration/README.md` — Dettagli sulla calibrazione (se presente)
