#!/usr/bin/env python3

import cv2
import numpy as np
import os
import torch

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
    Classe wrapper per integrare l'algoritmo di enhancement WaterNet in ROS 2.
    Incapsula il caricamento dei pesi, l'inizializzazione del dispositivo hardware
    e la pipeline di elaborazione frame by frame.
    """
    def __init__(self, weights_path=None):
        """
        Inizializza il modello caricando i pesi e allocandolo sul device disponibile
        (CUDA, MPS per i Mac Apple Silicon, o CPU).
        """
        if weights_path is None:
            # di default cerca weights.pt nella stessa cartella di questo script
            script_dir = os.path.dirname(os.path.abspath(__file__))
            weights_path = os.path.join(script_dir, "weights.pt")

        if not os.path.exists(weights_path):
            raise FileNotFoundError(f"Weights not found at path: {weights_path}")

        # selezione automatica del dispositivo di accelerazione hardware
        if torch.cuda.is_available():
            self.device = torch.device("cuda")
        elif torch.backends.mps.is_available():
            self.device = torch.device("mps")
        else:
            self.device = torch.device("cpu")
        
        print(f"[Enhancer] WaterNet initialized on device: {self.device}")
        
        # inizializzazione della rete e caricamento dei pesi salvati
        self.model = WaterNet()
        ckpt = torch.load(weights_path, map_location=self.device)
        self.model.load_state_dict(ckpt)
        self.model = self.model.to(self.device)
        # modalità valutazione (disabilita dropout/batchnorm per l'inferenza)
        self.model.eval()

    def enhance_image(self, image_bgr):
        """
        Applica l'intera pipeline di enhancement (WaterNet -> Laplacian -> CLAHE)
        a un singolo frame/immagine in formato BGR (formato standard OpenCV fornito dal cv_bridge ROS 2).
        
        Ritorna l'immagine finale migliorata come array NumPy BGR.
        """
        # peparazione dell'immagine (conversione BGR -> RGB e calcolo tensori wb, he, gc)
        rgb_im = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        rgb_ten, wb_ten, he_ten, gc_ten = preprocess(rgb_im)

        # spostamento dei tensori nella memoria del device (GPU o CPU)
        rgb_ten = rgb_ten.to(self.device)
        wb_ten  = wb_ten.to(self.device)
        he_ten  = he_ten.to(self.device)
        gc_ten  = gc_ten.to(self.device)

        # inferenza WaterNet
        with torch.no_grad():
            out_ten = self.model(rgb_ten, wb_ten, he_ten, gc_ten)

        # post-processamento WaterNet e riconversione a BGR OpenCV
        out_im = postprocess(out_ten).squeeze(0)  # da tensore (1,H,W,3) a (H,W,3)
        result_bgr = cv2.cvtColor(out_im, cv2.COLOR_RGB2BGR)

        # passaggi successivi di correzione contrasto e sharpening
        sharpened = laplacian_sharpen(result_bgr)
        final_img = apply_CLAHE(sharpened)

        return final_img
