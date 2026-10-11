import cv2
import numpy as np
import openvino as ov

# Le 4 classi estratte dal tuo file data.yaml
CLASSES = ["Glass", "Metal", "Plastic", "Trash"]

def pre_process(image, input_shape):
    """Prepara l'immagine per il modello OpenVINO"""
    h, w = input_shape[2], input_shape[3] # 416x416
    
    # Ridimensionamento e cambio colore da BGR (OpenCV) a RGB (YOLO)
    resized_img = cv2.resize(image, (w, h))
    rgb_img = cv2.cvtColor(resized_img, cv2.COLOR_BGR2RGB)
    
    # Normalizzazione [0-1] e cambio layout da HWC a CHW
    input_tensor = rgb_img.astype(np.float32) / 255.0
    input_tensor = np.transpose(input_tensor, (2, 0, 1))
    
    # Aggiunta dimensione batch: da [3,416,416] a [1,3,416,416]
    input_tensor = np.expand_dims(input_tensor, 0)
    return input_tensor, image.shape

def post_process(output, orig_shape, input_shape, conf_threshold=0.5):
    """Estrae Box, Classe e Confidenza dall'output di YOLOv8"""
    # L'output di YOLOv8 è [1, 8, 3549]. Rimuoviamo il batch e trasponiamo in [3549, 8]
    predictions = np.squeeze(output).T
    
    boxes, scores, class_ids = [], [], []
    
    orig_h, orig_w = orig_shape[:2]
    input_h, input_w = input_shape[2], input_shape[3]
    
    # Fattori di scala per riportare i box alla dimensione originale (es. 720p)
    x_factor = orig_w / input_w
    y_factor = orig_h / input_h
    
    for row in predictions:
        class_scores = row[4:]
        class_id = np.argmax(class_scores)
        score = class_scores[class_id]
        
        if score > conf_threshold:
            # cx, cy, w, h
            cx, cy, w, h = row[0:4]
            
            # Conversione coordinate per cv2.dnn.NMSBoxes (x_min, y_min, w, h)
            left = int((cx - w / 2) * x_factor)
            top = int((cy - h / 2) * y_factor)
            width = int(w * x_factor)
            height = int(h * y_factor)
            
            boxes.append([left, top, width, height])
            scores.append(float(score))
            class_ids.append(class_id)
            
    # Non-Maximum Suppression (NMS) per rimuovere box sovrapposti
    indices = cv2.dnn.NMSBoxes(boxes, scores, conf_threshold, 0.4)
    
    results = []
    if len(indices) > 0:
        for i in indices.flatten():
            # Calcolo del centro del target (Posizione XY richiesta)
            x, y, w, h = boxes[i]
            center_x, center_y = x + (w // 2), y + (h // 2)
            
            results.append({
                "class": CLASSES[class_ids[i]],
                "confidence": scores[i],
                "box": boxes[i],
                "center": (center_x, center_y)
            })
            
    return results

def main():
    core = ov.Core()
    compiled_model = core.compile_model("best_openvino_model/best.xml", "CPU")
    input_layer = compiled_model.input(0)
    output_layer = compiled_model.output(0)
    input_shape = input_layer.shape

    print("Generazione frame fittizio 1280x720...")
    dummy_image = np.zeros((720, 1280, 3), dtype=np.uint8)
    
    print("Pre-processing...")
    input_tensor, orig_shape = pre_process(dummy_image, input_shape)
    
    print("Inferenza OpenVINO...")
    result = compiled_model([input_tensor])[output_layer]
    
    print("Post-processing...")
    detections = post_process(result, orig_shape, input_shape, conf_threshold=0.25)
    
    print("\n--- RISULTATI ---")
    if not detections:
        print("Nessun target rilevato.")
    else:
        for d in detections:
            print(f"[{d['class']}] Conf: {d['confidence']:.2f} | Centro: {d['center']} | Box: {d['box']}")

if __name__ == "__main__":
    main()