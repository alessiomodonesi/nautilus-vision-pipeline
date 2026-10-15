#!/usr/bin/env python3
"""Confronto PyTorch (.pt) vs OpenVINO per lo stesso modello YOLO.

Usa Ultralytics per entrambi i backend, così pre-processing, letterbox,
NMS e post-processing sono identici: l'unica variabile è il backend.
Ogni coppia usa la propria imgsz nativa (yolov8n=640, best=416).
"""
import argparse
import csv
import statistics
import time
from pathlib import Path

import numpy as np
from ultralytics import YOLO


WEIGHTS = (Path(__file__).resolve().parents[2] /
           "ros2_ws/src/nautilus_perception/nautilus_perception/data/weights")


def bench(label, model_path, imgsz, n_frames, warmup, dummy):
    print(f"\n== {label} ==")
    print(f"  path:  {model_path}")
    print(f"  imgsz: {imgsz}")
    model = YOLO(str(model_path))

    # warm-up (compila grafi, alloca cache)
    for _ in range(warmup):
        model.predict(source=dummy, imgsz=imgsz, verbose=False, device="cpu")

    lat = []
    for _ in range(n_frames):
        t0 = time.perf_counter()
        model.predict(source=dummy, imgsz=imgsz, verbose=False, device="cpu")
        lat.append((time.perf_counter() - t0) * 1000.0)

    lat_sorted = sorted(lat)
    n = len(lat_sorted)
    return {
        "label": label,
        "model": str(model_path),
        "imgsz": imgsz,
        "n": n,
        "mean_ms": statistics.mean(lat),
        "p50_ms": statistics.median(lat),
        "p95_ms": lat_sorted[min(int(0.95 * n), n - 1)],
        "min_ms": min(lat),
        "max_ms": max(lat),
        "fps": 1000.0 / statistics.mean(lat),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=100)
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--out", default=None, help="CSV di output (opzionale)")
    args = ap.parse_args()

    dummy = np.zeros((720, 1280, 3), dtype=np.uint8)

    pairs = [
        ("yolov8n_pt",        WEIGHTS / "yolov8n.pt",                    640),
        ("yolov8n_fp32_640",  WEIGHTS / "yolov8n_openvino_640_fp32",     640),
        ("yolov8n_int8_640",  WEIGHTS / "yolov8n_openvino_640_int8",     640),
        ("yolov8n_int8_416",  WEIGHTS / "yolov8n_openvino_416_int8",     416),
        ("best_pt",           WEIGHTS / "best.pt",                       416),
        ("best_fp32_416",     WEIGHTS / "best_openvino_416_fp32",        416),
    ]

    results = []
    for label, path, imgsz in pairs:
        if not Path(path).exists():
            print(f"[SKIP] {label}: {path} non esiste")
            continue
        results.append(bench(label, path, imgsz,
                             args.frames, args.warmup, dummy))

    if not results:
        print("Nessun modello trovato. Verifica i path in WEIGHTS.")
        return

    print("\n\n== Riepilogo ==")
    print(f"{'label':<14}{'imgsz':>7}{'mean':>9}{'p50':>9}{'p95':>9}{'fps':>8}")
    for r in results:
        print(f"{r['label']:<14}{r['imgsz']:>7}"
              f"{r['mean_ms']:>8.1f}m{r['p50_ms']:>8.1f}m"
              f"{r['p95_ms']:>8.1f}m{r['fps']:>7.2f}")

    # boost OpenVINO per ogni coppia .pt/.ov
    by_label = {r["label"]: r for r in results}
    for pt, ov in [("yolov8n_pt", "yolov8n_fp32_640"),
                   ("yolov8n_pt", "yolov8n_int8_640"),
                   ("yolov8n_pt", "yolov8n_int8_416"),
                   ("best_pt",    "best_fp32_416")]:
        if pt in by_label and ov in by_label:
            b = ((by_label[ov]["fps"] - by_label[pt]["fps"]) /
                 by_label[pt]["fps"]) * 100
            print(f"\n{ov} vs {pt}: {b:+.1f}% FPS "
                  f"({by_label[pt]['fps']:.2f} -> {by_label[ov]['fps']:.2f})")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
            w.writeheader()
            w.writerows(results)
        print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
    