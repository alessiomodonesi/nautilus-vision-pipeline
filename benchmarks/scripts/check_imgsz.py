#!/usr/bin/env python3
"""Stampa la shape di input effettiva di .pt (a runtime) e OpenVINO (.xml)."""
import sys
from pathlib import Path

import openvino as ov
from ultralytics import YOLO

WEIGHTS = (Path(__file__).resolve().parents[2] /
           "ros2_ws/src/nautilus_perception/nautilus_perception/data/weights")


def inspect_pt(path, runtime_imgsz=416):
    print(f"\n== {path.name} ==")
    m = YOLO(str(path))
    print(f"  task:        {m.task}")
    print(f"  names:       {list(m.names.values()) if isinstance(m.names, dict) else m.names}")
    try:
        y = m.model.yaml
        print(f"  yaml imgsz:  {y.get('imgsz')}")
        print(f"  yaml nc:     {y.get('nc')}")
    except Exception as e:
        print(f"  yaml imgsz:  n/a ({e})")
    print(f"  overrides imgsz: {m.overrides.get('imgsz', 'default 640')}")
    # inferenza reale per vedere la shape effettiva del tensore input
    import numpy as np
    dummy = np.zeros((720, 1280, 3), dtype=np.uint8)
    r = m.predict(source=dummy, imgsz=runtime_imgsz, verbose=False)
    print(f"  runtime imgsz: {runtime_imgsz}")
    print(f"  orig_shape frame:    {r[0].orig_shape}")
    print(f"  speed (ms):          {r[0].speed}")


def inspect_ov(xml_path):
    print(f"\n== {xml_path.name} ==")
    core = ov.Core()
    model = core.read_model(str(xml_path))
    for i, inp in enumerate(model.inputs):
        name = inp.get_any_name() if inp.get_names() else f"input_{i}"
        print(f"  input[{i}]  name={name}  "
              f"shape={inp.shape}  type={inp.element_type}")
    for i, out in enumerate(model.outputs):
        name = out.get_any_name() if out.get_names() else f"output_{i}"
        print(f"  output[{i}] name={name}  "
              f"shape={out.shape}  type={out.element_type}")
    meta = xml_path.parent / "metadata.yaml"
    if meta.exists():
        import yaml
        with open(meta) as f:
            md = yaml.safe_load(f)
        print(f"  metadata.yaml: names={md.get('names')}  "
              f"imgsz={md.get('imgsz', 'n/d')}  task={md.get('task', 'n/d')}")


def main():
    core = ov.Core()
    # scansiona TUTTI i modelli OpenVINO presenti
    for d in sorted(WEIGHTS.glob("*openvino*")):
        if not d.is_dir():
            continue
        xmls = sorted(d.glob("*.xml"))
        if not xmls:
            continue
        print(f"\n== {d.name} ==")
        inspect_ov(xmls[0])

    # i .pt per confronto
    for pt_name in ["yolov8n.pt", "best.pt"]:
        pt = WEIGHTS / pt_name
        if pt.exists():
            inspect_pt(pt, runtime_imgsz=416 if "best" in pt_name else 640)


if __name__ == "__main__":
    main()
    