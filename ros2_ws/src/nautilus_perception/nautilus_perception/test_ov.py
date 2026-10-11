from ultralytics import YOLO
import numpy as np

# percorso al modello OpenVINO
model_path = "data/weights/yolov8n_openvino_model"

print(f"Loading model from: {model_path}")
model = YOLO(model_path)

# crea un'immagine fittizia nera 640x480 (uint8)
dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)

print("Running test inference...")
results = model.predict(dummy_frame, verbose=True)
print("Inference completed successfully! The OpenVINO model is working.")
