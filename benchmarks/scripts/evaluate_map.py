#!/usr/bin/env python3
"""Calcola mAP@0.5 e mAP@0.5:0.95 sul validation set per ogni variante di modello.

Supporta sia modelli Ultralytics .pt (PyTorch) sia modelli esportati
in formato OpenVINO (directory contenente .xml/.bin/metadata.yaml).
"""
import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

try:
    from ultralytics import YOLO
except ImportError:
    print("ERROR: ultralytics non installato. pip install ultralytics",
          file=sys.stderr)
    sys.exit(1)


def resolve_weights(path_str: str) -> str:
    """Accetta .pt, .xml, oppure una directory con .xml o .pt dentro."""
    p = Path(path_str).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"Percorso pesi inesistente: {p}")
    if p.is_file():
        if p.suffix in (".pt", ".xml"):
            return str(p)
        raise ValueError(f"Estensione non supportata: {p.suffix}")
    xmls = sorted(p.glob("*.xml"))
    pts = sorted(p.glob("*.pt"))
    if xmls:
        # per OpenVINO Ultralytics richiede il percorso della cartella del modello
        return str(p)
    if pts:
        return str(pts[0])
    raise FileNotFoundError(f"Nessun .xml/.pt trovato in {p}")


def evaluate(weights, data_yaml, imgsz, split, conf, iou, device, batch):
    model = YOLO(weights, task="detect")
    metrics = model.val(
        data=str(Path(data_yaml).expanduser().resolve()),
        split=split,
        imgsz=imgsz,
        conf=conf,
        iou=iou,
        device=device,
        batch=batch,
        plots=True,
        verbose=True,
    )
    box = metrics.box
    per_class = {}
    for i, c in enumerate(box.ap_class_index):
        per_class[model.names[int(c)]] = {
            "map50": float(box.ap50[i]),
            "map50_95": float(box.ap[i]),
        }
    return {
        "map50": float(box.map50),
        "map50_95": float(box.map),
        "mp": float(box.mp),
        "mr": float(box.mr),
        "per_class": per_class,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True,
                    help="Path a .pt, .xml o directory OpenVINO")
    ap.add_argument("--data", required=True, help="Path al data.yaml")
    ap.add_argument("--out", required=True, help="CSV di output")
    ap.add_argument("--imgsz", type=int, default=416,
                    help="Deve combaciare con il training/export del modello")
    ap.add_argument("--split", default="val",
                    choices=["val", "test", "train"])
    ap.add_argument("--conf", type=float, default=0.001,
                    help="Soglia bassa per mAP corretta (default 0.001)")
    ap.add_argument("--iou", type=float, default=0.6)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--tag", default=None,
                    help="Etichetta variante (es. yolov8n_pt, best_ov)")
    args = ap.parse_args()

    weights = resolve_weights(args.weights)
    tag = args.tag or Path(weights).stem

    print("== evaluate_map ==")
    print(f"  weights: {weights}")
    print(f"  data:    {args.data}")
    print(f"  tag:     {tag}")
    print(f"  imgsz:   {args.imgsz}")
    print(f"  split:   {args.split}")

    res = evaluate(weights, args.data, args.imgsz, args.split,
                   args.conf, args.iou, args.device, args.batch)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tag", "weights", "data", "split", "imgsz",
                    "map50", "map50_95", "mp", "mr", "timestamp"])
        w.writerow([tag, weights, args.data, args.split, args.imgsz,
                    f"{res['map50']:.5f}", f"{res['map50_95']:.5f}",
                    f"{res['mp']:.5f}", f"{res['mr']:.5f}",
                    datetime.now().isoformat(timespec="seconds")])

    print(f"\nmAP@0.5      = {res['map50']:.4f}")
    print(f"mAP@0.5:0.95 = {res['map50_95']:.4f}")
    print(f"mP           = {res['mp']:.4f}")
    print(f"mR           = {res['mr']:.4f}")
    print("per-class mAP@0.5:")
    for name, v in res["per_class"].items():
        print(f"  {name:>12s}: {v['map50']:.4f}  "
              f"(0.5:0.95 = {v['map50_95']:.4f})")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
    