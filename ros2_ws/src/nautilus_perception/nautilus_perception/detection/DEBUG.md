# Nautilus — Detection Module (Debug & Status Notes)

> **Ultimo aggiornamento:** 13/10/2026 — Calibrazione 720p completata e validata
> **Stato:** Fase 5 chiusa. Stereo calibrated at 1280×720 (RMS 0.125 px),
> Z validata su 4 distanze (60–90 cm) con errore < 1 cm. Pronti per Fase 6
> (benchmark).

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
| `calibration/` | Tooling di calibrazione (720p eseguita il 13/10/2026) |
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

### ✅ Risolto — Mismatch risoluzione calibrazione/streaming

**Sintomo (storico):** le mappe di rettifica erano calibrate a 640×480 ma le
camere giravano a 1280×720. Applicare le mappe produceva rettifica
geometricamente invalida: righe epipolari non allineate, bias sistematico
sulla Z (~30% sottostimata), campo visivo ridotto.

**Soluzione (13/10/2026):** ricalibrazione completa a 1280×720 eseguita con
`calibration/stereo_calibrate.py` su 36 coppie ChArUco catturate nel range
0.50–0.85 m. Risultati:

| Metrica | Valore |
| --- | --- |
| Coppie usate | 36/36 (0 scartate) |
| Per-camera RMS (lx) | 0.116 px |
| Per-camera RMS (rx) | 0.116 px |
| Stereo RMS | 0.125 px |
| Baseline | 0.12017 m (12.02 cm) |
| Focal length (raw) | 1423.27 px |
| P1[0,0] (rectified) | 1500.89 px |

**File prodotti:**

- `stereo_calib_720p.npz` — calibrazione attiva (installata nel pacchetto)
- `stereo_calib_480p.npz` — calibrazione legacy, tenuta per riferimento

**Validazione Z metrica:** oggetto textureato a distanze misurate con metro,
Z stimato dalla pipeline. Risultati (mediana di 5-10 letture per distanza):

| Z reale | Z stimato | Errore |
| --- | --- | --- |
| 0.60 m | ~0.60 m | < 1 cm |
| 0.70 m | ~0.70 m | < 1 cm |
| 0.80 m | ~0.80 m | < 1 cm |
| 0.90 m | ~0.90 m | < 1 cm |

Errore su tutta la banda operativa < 1 cm. **Accuratezza Z validata.**

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
    baseline: float = 0.12017      # Calibrated 2026-10-13, 720p (12.02 cm)
    focal_length: float = 1500.89  # P1[0,0] rectified, 720p
    ...
```

**Nota:** valori estratti da `stereo_calib_720p.npz`. La focale è
`P1[0,0]` rettificata (1500.89 px), non la focale raw (1423.27 px), perché
il matcher NCC lavora su frame già rimappati. La baseline (12.02 cm) coincide
con la specifica del rig (12 cm).

### `SparseBlockMatcher.__init__`

```python
# Tuned for calibrated 720p (f=1500.89, B=0.12017, f*B=180.35)
# Z_min ~0.40 m @ d=450, Z_max ~1.80 m @ d=100
self.min_disparity = 100
self.max_disparity = 450
self.patch_size = 31
self.row_tolerance = 5
self.min_confidence = 0.6
```

**Nota (13/10/2026):** i valori precedenti (f=1114, range Z 0.27–8.9 m) erano
basati su una calibrazione placeholder. I valori attuali derivano dalla
calibrazione 720p reale e restringono il range a 0.40–1.80 m, che copre
con margine la fascia operativa del braccio (0.40–1.10 m). Il valore
"suggerito" originariamente (f~2165, `max_disparity=400`) era basato su una
scala lineare errata — la focale reale è 1500.89 px, non 2165.

---

## 5. Tooling di calibrazione (eseguito)

Tutti gli script sono in `calibration/`:

| Script | Ruolo |
| --- | --- |
| `generate_charuco.py` | Genera board ChArUco 8×11, 15/11 mm, `DICT_4X4_50` |
| `capture_calibration_pairs.py` | Cattura coppie L/R (GUI, richiede display) |
| `capture_calibration_pairs_web.py` | Cattura coppie L/R (headless, browser) |
| `stereo_calibrate.py` | Genera `stereo_calib_720p.npz` dalle coppie |
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

**Stato (13/10/2026):** eseguito con successo. `config.py` aggiornato,
pacchetto `nautilus_perception` rebuildato, calibrazione installata e
validata (vedi Sezione 2).

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
| Modulo IMX708 sinistro candidato a sostituzione | ⏳ (valutazione post-benchmark) |
| Calibrazione 720p eseguita (RMS 0.125 px) | ✅ |
| File `stereo_calib_720p.npz` installato nel pacchetto | ✅ |
| `config.py` aggiornato (baseline 0.12017, focal 1500.89) | ✅ |
| `SparseBlockMatcher` ritarato (disparity 100-450) | ✅ |
| Validazione Z su 4 distanze (0.6–0.9 m) | ✅ (errore < 1 cm) |
| Benchmark FPS/latenza/CPU (Fase 6) | ⏳ |

---

## 7. Riferimenti

- `docs/TODO.md` — Roadmap completa (Fase 5 = calibrazione 720p, chiusa)
- `detection_params.yaml` — Parametri runtime del nodo
- `deploy/lock_cameras.py` — Lock fotometrico post-launch (systemd)
- `deploy/lock-cameras.service` — Unit systemd che lo invoca
- `deploy/nautilus-vision.service` — Unit systemd della pipeline (a cui `lock-cameras` è agganciata via `PartOf`)
- `calibration/README.md` — Dettagli sulla calibrazione (se presente)
- `calibration/find_focus.py` — Test LensPosition con metrica di sharpness
- `calibration/stereo_calibrate.py` — Genera `stereo_calib_720p.npz`
- `stereo_calib_720p.npz` — Calibrazione attiva (1280×720)
- `stereo_calib_480p.npz` — Calibrazione legacy (640×480), non usata
