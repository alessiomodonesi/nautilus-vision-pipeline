import time
import numpy as np

# Importiamo moduli di init e inferenza dagli script esistenti
from yolo_inference import init_yolo, run_yolo
from ov_inference import init_ov, run_ov

def run_benchmark(name, init_func, infer_func, num_frames=100):
    print(f"\nInizializzazione {name}...")
    
    # Init specifico in base al framework
    if name == "OpenVINO":
        model, classes = init_func()
    else:
        model = init_func()
        classes = None
        
    dummy_image = np.zeros((720, 1280, 3), dtype=np.uint8)
    
    # Warm-up per caricare tensori e allocare memoria cache
    print(f"Warm-up {name}...")
    if name == "OpenVINO":
        infer_func(model, dummy_image, classes)
    else:
        infer_func(model, dummy_image)
        
    print(f"Avvio misurazione {name} su {num_frames} frames...")
    latencies = []
    start_time = time.time()
    
    for _ in range(num_frames):
        t0 = time.time()
        if name == "OpenVINO":
            infer_func(model, dummy_image, classes)
        else:
            infer_func(model, dummy_image)
        latencies.append((time.time() - t0) * 1000)
        
    total_time = time.time() - start_time
    fps = num_frames / total_time
    avg_latency = np.mean(latencies)
    
    return avg_latency, fps

def main():
    print("Benchmark: YOLOv8 Nano vs OpenVINO")
    
    # 100 frame corrispondono a 20 secondi di video a 5 FPS (il target del daemon)
    yolo_lat, yolo_fps = run_benchmark("YOLOv8 Nano", init_yolo, run_yolo, num_frames=100)
    ov_lat, ov_fps = run_benchmark("OpenVINO", init_ov, run_ov, num_frames=100)
    
    print(f"\nYOLOv8 Nano: Latenza media = {yolo_lat:.2f} ms | Throughput = {yolo_fps:.2f} FPS")
    print(f"\nOpenVINO: Latenza media = {ov_lat:.2f} ms | Throughput = {ov_fps:.2f} FPS")
    
    if yolo_fps > 0:
        boost = ((ov_fps - yolo_fps) / yolo_fps) * 100
        print(f"\nIncremento prestazionale FPS: +{boost:.1f}%")

if __name__ == "__main__":
    main()