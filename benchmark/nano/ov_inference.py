import cv2
import numpy as np
import openvino as ov
from ultralytics import YOLO

def pre_process(image, input_shape):
    h, w = input_shape[2], input_shape[3]
    resized_img = cv2.resize(image, (w, h))
    rgb_img = cv2.cvtColor(resized_img, cv2.COLOR_BGR2RGB)
    input_tensor = rgb_img.astype(np.float32) / 255.0
    input_tensor = np.transpose(input_tensor, (2, 0, 1))
    input_tensor = np.expand_dims(input_tensor, 0)
    return input_tensor, image.shape

def post_process(output, orig_shape, input_shape, classes, conf_threshold=0.5):
    predictions = np.squeeze(output).T
    boxes, scores, class_ids = [], [], []
    orig_h, orig_w = orig_shape[:2]
    input_h, input_w = input_shape[2], input_shape[3]
    x_factor = orig_w / input_w
    y_factor = orig_h / input_h
    
    for row in predictions:
        class_scores = row[4:]
        class_id = np.argmax(class_scores)
        score = class_scores[class_id]
        if score > conf_threshold:
            cx, cy, w, h = row[0:4]
            left = int((cx - w / 2) * x_factor)
            top = int((cy - h / 2) * y_factor)
            width = int(w * x_factor)
            height = int(h * y_factor)
            boxes.append([left, top, width, height])
            scores.append(float(score))
            class_ids.append(class_id)
            
    indices = cv2.dnn.NMSBoxes(boxes, scores, conf_threshold, 0.4)
    results = []
    if len(indices) > 0:
        for i in indices.flatten():
            x, y, w, h = boxes[i]
            center_x, center_y = x + (w // 2), y + (h // 2)
            results.append({
                "class": classes[class_ids[i]],
                "confidence": scores[i],
                "box": boxes[i],
                "center": (center_x, center_y)
            })
    return results

def init_ov(model_xml="yolov8n_openvino_model/yolov8n.xml"):
    """Inizializza OpenVINO e recupera le classi."""
    core = ov.Core()
    compiled_model = core.compile_model(model_xml, "CPU")
    model = YOLO('yolov8n.pt') 
    return compiled_model, model.names

def run_ov(compiled_model, image, classes, conf_threshold=0.25):
    """Esegue l'intera pipeline OpenVINO su un singolo frame."""
    input_layer = compiled_model.input(0)
    output_layer = compiled_model.output(0)
    input_shape = input_layer.shape
    
    input_tensor, orig_shape = pre_process(image, input_shape)
    result = compiled_model([input_tensor])[output_layer]
    return post_process(result, orig_shape, input_shape, classes, conf_threshold)

def main():
    print("Preparazione e caricamento modello OpenVINO...")
    compiled_model, classes = init_ov()
    
    print("Generazione frame fittizio 1280x720...")
    dummy_image = np.zeros((720, 1280, 3), dtype=np.uint8)
    
    print("Inferenza OpenVINO in corso...")
    detections = run_ov(compiled_model, dummy_image, classes)
    
    print("\nRisultati OpenVINO:")
    if not detections:
        print("Nessun target rilevato")
    else:
        for d in detections:
            print(f"[{d['class']}] Conf: {d['confidence']:.2f} | Centro: {d['center']} | Box: {d['box']}")

if __name__ == "__main__":
    main()