#!/usr/bin/env python3

import cv2
import numpy as np
import os
import torch
import time

from nautilus_perception.enhancement.contrast_tweaker import apply_CLAHE, laplacian_sharpen
from nautilus_perception.enhancement.denoising import *
from nautilus_perception.enhancement.waternet.net import WaterNet
from nautilus_perception.enhancement.waternet.data import transform


def arr2ten(arr):
    """
    Converte un array NumPy (OpenCV) in un tensore PyTorch normalizzato [0, 1].
    Permuta le dimensioni per adattarsi al formato atteso da PyTorch (C, H, W).
    """
    ten = torch.from_numpy(arr) / 255
    if len(ten.shape) == 3:
        # se è una singola immagine (H, W, C) -> (1, C, H, W)
        ten = torch.permute(ten, (2, 0, 1))
        ten = torch.unsqueeze(ten, dim=0)
    elif len(ten.shape) == 4:
        # se è già un batch di immagini (B, H, W, C) -> (B, C, H, W)
        ten = torch.permute(ten, (0, 3, 1, 2))
    return ten

def ten2arr(ten):
    """
    Converte un tensore PyTorch in output dal modello in un array NumPy (OpenCV) (H, W, C).
    Effettua il clipping tra 0 e 1, scala a [0, 255] e converte in uint8.
    """
    arr = ten.cpu().detach().numpy()
    arr = np.clip(arr, 0, 1)
    arr = (arr * 255).astype(np.uint8)
    arr = np.transpose(arr, (0, 2, 3, 1))
    return arr

def preprocess(rgb_arr):
    """
    Esegue i pre-processamenti richiesti da WaterNet sulle immagini d'ingresso:
    White Balancing (wb), Gamma Correction (gc) e Histogram Equalization (he).
    Converte infine tutti gli array risultanti in tensori.
    """
    wb, gc, he = transform(rgb_arr)
    rgb_ten = arr2ten(rgb_arr)
    wb_ten  = arr2ten(wb)
    gc_ten  = arr2ten(gc)
    he_ten  = arr2ten(he)
    return rgb_ten, wb_ten, he_ten, gc_ten

def postprocess(model_out):
    """
    Alias per semplificare la pipeline di post-processing dal tensore del modello all'array.
    """
    return ten2arr(model_out)


class WaternetEnhancer:
    """
    Classe wrapper per l'enhancement. 'mode' supporta: 
    - 'auto': Applica WaterNet se è presente un acceleratore hardware (CUDA/MPS), altrimenti CPU.
    - 'force_on': Attiva sempre WaterNet (anche su CPU pura).
    - 'force_off': Disattiva sempre WaterNet, usa solo OpenCV.
    """
    def __init__(self, weights_path=None, mode='auto'):
        if weights_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            weights_path = os.path.join(script_dir, "weights.pt")

        if not os.path.exists(weights_path):
            print(f"[Warning] Weights not found at path: {weights_path}")

        # rilevamento hardware e impostazione flag basati sulla modalità modulare
        if mode == 'force_off':
            self.device = torch.device("cpu")
            self.use_waternet = False
            print("[Enhancer] Mode FORCED OFF: WaterNet completely disabled.")
        elif mode == 'force_on':
            # cerca comunque l'hardware migliore, ma lo forza anche su CPU se necessario
            self.device = torch.device("cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu"))
            self.use_waternet = True
            print(f"[Enhancer] Mode FORCED ON: WaterNet forcibly activated on {self.device}.")
        else: # 'auto' (comportamento di default)
            if torch.cuda.is_available():
                self.device = torch.device("cuda")
                self.use_waternet = True
            elif torch.backends.mps.is_available():
                self.device = torch.device("mps")
                self.use_waternet = True
            else:
                self.device = torch.device("cpu")
                # disabilita WaterNet su CPU di base
                self.use_waternet = False
            print(f"[Enhancer] Mode AUTO: Hardware detected {self.device}, WaterNet {'Enabled' if self.use_waternet else 'Disabled'}.")

        # inizializzazione rete solo se necessario
        if self.use_waternet:
            print("[Enhancer] Initializing WaterNet...")
            self.model = WaterNet()
            ckpt = torch.load(weights_path, map_location=self.device)
            self.model.load_state_dict(ckpt)
            self.model = self.model.to(self.device)
            self.model.eval()
        else:
            print("[Enhancer] WaterNet DISABLED. Light mode (OpenCV only: Sharpening + CLAHE).")

    def enhance_image(self, image_bgr):
        # esecuzione condizionale
        if self.use_waternet:
            # pipeline completa
            rgb_im = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
            rgb_ten, wb_ten, he_ten, gc_ten = preprocess(rgb_im)

            rgb_ten = rgb_ten.to(self.device)
            wb_ten  = wb_ten.to(self.device)
            he_ten  = he_ten.to(self.device)
            gc_ten  = gc_ten.to(self.device)

            with torch.no_grad():
                out_ten = self.model(rgb_ten, wb_ten, he_ten, gc_ten)

            out_im = postprocess(out_ten).squeeze(0)  
            base_image = cv2.cvtColor(out_im, cv2.COLOR_RGB2BGR)
        else:
            # pipeline leggera
            # salta completamente PyTorch e WaterNet, usa l'immagine originale
            base_image = image_bgr.copy()

        # applicati in entrambi i casi per favorire la detection
        sharpened = laplacian_sharpen(base_image)
        final_img = apply_CLAHE(sharpened)

        return final_img


# eseguibile da terminale senza ROS per verificare visivamente l'output 
# e misurare il tempo di esecuzione su hardware specifico
if __name__ == "__main__":
    # setting della modalità in 'auto', 'force_on' o 'force_off' per testare l'immagine locale
    MODE = 'force_on' 
    
    # nome dell'immagine da usare per il test
    IMG_NAME = "test.jpg"
    OUTPUT_NAME = "test_output.jpg"
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    img_path = os.path.join(script_dir, IMG_NAME)
    out_path = os.path.join(script_dir, OUTPUT_NAME)

    if not os.path.exists(img_path):
        print(f"[Error] Test image '{IMG_NAME}' not found in the directory.")
        print(f"Searched path: {img_path}")
    else:
        # carica immagine
        img = cv2.imread(img_path)
        print(f"Image loaded successfully (Resolution: {img.shape[1]}x{img.shape[0]}).")

        # inizializza classe passando il parametro modulare
        enhancer = WaternetEnhancer(mode=MODE)

        # esecuzione misurata
        print("\nProcessing image...")
        t0 = time.time()
        
        result_img = enhancer.enhance_image(img)
        
        t1 = time.time()
        elapsed = t1 - t0
        
        # stampa risultati
        print(f"Completed! Time taken: {elapsed:.4f} seconds (approx. {1/elapsed:.2f} FPS).")
        
        # salva risultato
        cv2.imwrite(out_path, result_img)
        print(f"Enhanced image saved to: {out_path}")
        