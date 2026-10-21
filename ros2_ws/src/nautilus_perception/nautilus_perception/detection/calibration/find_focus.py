#!/usr/bin/env python3
"""
find_focus.py
=============
Trova la LensPosition ottimale per ciascuna camera del rig stereo
Nautilus, alla distanza operativa di produzione.

Per ogni camera, cicla su una lista di LensPosition, cattura un frame
per ciascuna, salva l'immagine e calcola un indice di nitidezza
(varianza del Laplaciano). Stampa il valore migliore per camera.

Uso:
    python3 -m calibration.find_focus --distance 0.65 --outdir focus_test
"""

import argparse
import os
import sys
import time

import cv2
import numpy as np


def open_camera(camera_num, resolution):
    try:
        from picamera2 import Picamera2
    except ImportError as exc:
        raise RuntimeError(
            "picamera2 is required. Attiva il venv: source .venv/bin/activate"
        ) from exc

    picam2 = Picamera2(camera_num=camera_num)
    cfg = picam2.create_video_configuration(main={"size": resolution, "format": "RGB888"})
    picam2.configure(cfg)
    picam2.start()
    time.sleep(1.0)
    return picam2


def sharpness(gray):
    """Varianza del Laplaciano: più alto = più nitido."""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def sweep_camera(cam, cam_name, lp_values, outdir, settle_s=0.6):
    """Cicla sulle LensPosition, salva immagini, ritorna (best_lp, best_score)."""
    results = []
    for lp in lp_values:
        cam.set_controls({"AfMode": 0, "LensPosition": float(lp)})
        time.sleep(settle_s)
        frame = cam.capture_array()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        score = sharpness(gray)
        path = os.path.join(outdir, f"{cam_name}_lp{lp:.2f}_score{score:.0f}.jpg")
        cv2.imwrite(path, frame)
        results.append((lp, score))
        print(f"  {cam_name}  LP={lp:.2f}  sharpness={score:10.1f}  -> {os.path.basename(path)}")

    best_lp, best_score = max(results, key=lambda r: r[1])
    return best_lp, best_score, results


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--distance", type=float, default=0.65,
                    help="Distanza operativa target in metri (default: 0.65)")
    ap.add_argument("--left-cam", type=int, default=0)
    ap.add_argument("--right-cam", type=int, default=1)
    ap.add_argument("--resolution", default="1280x720")
    ap.add_argument("--outdir", default="focus_test")
    ap.add_argument("--sweep", type=float, default=0.4,
                    help="Ampiezza dello sweep intorno a 1/distance (default: ±0.4)")
    ap.add_argument("--steps", type=int, default=9,
                    help="Numero di valori di LensPosition da testare (default: 9)")
    args = ap.parse_args()

    w, h = (int(x) for x in args.resolution.lower().split("x"))
    resolution = (w, h)

    # LensPosition è in diottrie: 1/metri
    target_lp = 1.0 / args.distance
    lp_min = max(0.3, target_lp - args.sweep)
    lp_max = target_lp + args.sweep
    lp_values = np.linspace(lp_min, lp_max, args.steps).tolist()

    print(f"Distanza target : {args.distance:.3f} m")
    print(f"LensPosition ottimale teorica : {target_lp:.3f}")
    print(f"Sweep : da {lp_min:.2f} a {lp_max:.2f} ({args.steps} valori)")
    print()

    os.makedirs(args.outdir, exist_ok=True)

    print(f"Apro camera sinistra (num={args.left_cam}) a {resolution}...")
    cam_l = open_camera(args.left_cam, resolution)

    print(f"Apro camera destra (num={args.right_cam}) a {resolution}...")
    cam_r = open_camera(args.right_cam, resolution)

    print("\n--- Camera SINISTRA ---")
    best_lp_l, best_score_l, results_l = sweep_camera(
        cam_l, "left", lp_values, args.outdir
    )

    print("\n--- Camera DESTRA ---")
    best_lp_r, best_score_r, results_r = sweep_camera(
        cam_r, "right", lp_values, args.outdir
    )

    cam_l.stop(); cam_l.close()
    cam_r.stop(); cam_r.close()

    print("\n" + "=" * 60)
    print("RISULTATI")
    print("=" * 60)
    print(f"Camera SINISTRA: LensPosition = {best_lp_l:.3f}  (sharpness {best_score_l:.1f})")
    print(f"Camera DESTRA  : LensPosition = {best_lp_r:.3f}  (sharpness {best_score_r:.1f})")
    print()
    print("Controlla anche a occhio le immagini in", args.outdir)
    print("Se il picco di sharpness è ai bordi dello sweep, allarga --sweep")
    print()
    print("Passo successivo: aggiorna i valori in produzione:")
    print("  - deploy/lock_cameras.py")
    print("  - nautilus_camera/config/camera_params.yaml")
    print("  - nautilus_perception/.../detection/DEBUG.md")
    print(f"  - poi calibra con: --lens-left {best_lp_l:.2f} --lens-right {best_lp_r:.2f}")


if __name__ == "__main__":
    main()