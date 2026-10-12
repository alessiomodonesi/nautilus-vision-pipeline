import cv2
import os
import shutil

def variance_of_laplacian(image_path):
    """Calcola un punteggio di messa a fuoco/dettaglio per un'immagine."""
    image = cv2.imread(image_path)
    if image is None:
        return 0.0
    # normalizzazione per Pi Cam 3 (riduce il rumore ISO)
    height = 480
    dim = (int(height * (image.shape[1] / image.shape[0])), height)
    resized = cv2.resize(image, dim, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    return cv2.Laplacian(blurred, cv2.CV_64F).var()

def calibrate_threshold(dataset_lx_dir):
    """Calcola i punteggi e li ordina per aiutarti a scegliere la soglia."""
    images = [f for f in os.listdir(dataset_lx_dir) if f.lower().endswith(('.jpg', '.png'))]
    print(f"Analyzing {len(images)} images for calibration...")    
    scores = []
    for filename in images:
        file_path = os.path.join(dataset_lx_dir, filename)
        score = variance_of_laplacian(file_path)
        scores.append((filename, score))
        
    # ordina i risultati dal peggiore al migliore
    scores.sort(key=lambda x: x[1])
    
    print("\nCALIBRATION RESULTS (From most blurred to sharpest)")
    for filename, score in scores:
        # calcola il percorso assoluto del file
        file_path = os.path.abspath(os.path.join(dataset_lx_dir, filename))
        
        # crea il link cliccabile usando la sintassi ANSI OSC 8
        # formato: \033]8;;URL\033\TESTO_VISIBILE\033]8;;\033\
        clickable_link = f"\033]8;;file://{file_path}\033\\{filename}\033]8;;\033\\"
        
        print(f"Score: {score:06.2f} | File: {clickable_link}")

def clean_stereo_dataset(dir_lx, dir_rx, keep_left, keep_right, discard_left, discard_right, threshold):
    """
    Pulisce il dataset COPIANDO LE COPPIE BUONE nelle cartelle di output da tenere,
    e COPIANDO LE COPPIE SCARSE nelle cartelle di scarto.
    I file originali non vengono MAI modificati o cancellati.
    """
    # crea le cartelle di output per le immagini da tenere e da scartare
    os.makedirs(keep_left, exist_ok=True)
    os.makedirs(keep_right, exist_ok=True)
    os.makedirs(discard_left, exist_ok=True)
    os.makedirs(discard_right, exist_ok=True)
    
    images_lx = [f for f in os.listdir(dir_lx) if f.lower().endswith(('.jpg', '.png'))]
    kept, discarded = 0, 0
    
    for filename in images_lx:
        path_lx = os.path.join(dir_lx, filename)
        path_rx = os.path.join(dir_rx, filename)
        
        # basiamo la decisione sull'immagine sinistra
        score = variance_of_laplacian(path_lx)
        
        if score >= threshold:
            # immagine BUONA: copia nelle nuove cartelle "left" e "right" DA TENERE
            print(f"Held Pair: {filename} (Score: {score:.2f})")
            shutil.copy2(path_lx, os.path.join(keep_left, filename))
            
            # copia anche la destra se esiste, mantenendo la coppia
            if os.path.exists(path_rx):
                shutil.copy2(path_rx, os.path.join(keep_right, filename))
            kept += 1
        else:
            # immagine SCARSA: copia nelle nuove cartelle "left" e "right" DI SCARTO
            print(f"Discarded pair: {filename} (Score: {score:.2f})")
            shutil.copy2(path_lx, os.path.join(discard_left, filename))
            
            # copia anche la destra se esiste negli scarti
            if os.path.exists(path_rx):
                shutil.copy2(path_rx, os.path.join(discard_right, filename))
            discarded += 1
            
    print(f"\nStereo cleaning complete! Pairs Kept: {kept} | Pairs Discarded: {discarded}")


if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    benchmark_root = os.path.abspath(os.path.join(current_dir, '..', '..'))

    # percorsi sorgente (raw dataset)
    dataset_raw_base = os.path.join(benchmark_root, "datasets", "raw", "underwater-image")
    lx_dir = os.path.join(dataset_raw_base, "2", "serie-1", "lx")
    rx_dir = os.path.join(dataset_raw_base, "2", "serie-1", "rx")

    # percorsi destinazione (clean output sotto datasets/processed/)
    clean_out_base = os.path.join(
        benchmark_root, "datasets", "processed", "clean_output", "2", "serie-1"
    )
    keep_left = os.path.join(clean_out_base, "keep_lx")
    keep_right = os.path.join(clean_out_base, "keep_rx")
    discard_left = os.path.join(clean_out_base, "discard_lx")
    discard_right = os.path.join(clean_out_base, "discard_rx")

    # PASSO 1: calibrare la soglia
    # calibrate_threshold(lx_dir)

    # PASSO 2: selezione e copia
    clean_stereo_dataset(
        lx_dir, rx_dir,
        keep_left, keep_right,
        discard_left, discard_right,
        threshold=1.99,
    )
    