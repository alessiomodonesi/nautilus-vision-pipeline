import numpy as np
from ultralytics import YOLO

def init_yolo(model_path='yolov8n.pt'):
    """Inizializza il modello YOLO nativo."""
    return YOLO(model_path)

def run_yolo(model, image, imgsz=416, conf=0.25):
    """Esegue l'inferenza nativa. verbose=False sopprime i log per frame."""
    return model.predict(source=image, imgsz=imgsz, conf=conf, verbose=False)

def main():
    print("Caricamento modello YOLOv8 Nano...")
    model = init_yolo()
    
    print("Generazione frame fittizio 1280x720...")
    dummy_image = np.zeros((720, 1280, 3), dtype=np.uint8)
    
    print("Inferenza YOLOv8 Nano in corso...")
    results = run_yolo(model, dummy_image)
    
    print("\nRisultati YOLOv8 Nano:")
    detections = results[0].boxes
    if len(detections) == 0:
        print("Nessun target rilevato")
    else:
        for box in detections:
            class_id = int(box.cls[0])
            class_name = model.names[class_id]
            confidence = float(box.conf[0])
            cx, cy, w, h = box.xywh[0].tolist()
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            print(f"[{class_name}] Conf: {confidence:.2f} | Centro: ({int(cx)}, {int(cy)}) | Box: [{int(x1)}, {int(y1)}, {int(x2)}, {int(y2)}]")

if __name__ == "__main__":
    main()