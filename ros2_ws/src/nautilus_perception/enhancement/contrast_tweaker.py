import cv2
import numpy as np
import os
from utils import list_images, save_image

def apply_CLAHE(image, clip_limit=2, tile_grid_size=(8, 8)):
    # Convert to LAB (luminance + color)
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)

    l_eq = clahe.apply(l)

    lab_eq = cv2.merge((l_eq, a, b))
    result = cv2.cvtColor(lab_eq, cv2.COLOR_LAB2BGR)
    return result

def process_contrast():
    input_folder = os.path.join(os.getcwd(), "data", "processed")
    output_folder = os.path.join(os.getcwd(), "data", "processed4")
    os.makedirs(output_folder, exist_ok=True)

    for path in list_images(input_folder):
        img = cv2.imread(path)
        enhanced = apply_CLAHE(img)
        filename = os.path.basename(path)
        save_image(os.path.join(output_folder, f"clahe_{filename}"), enhanced)

def laplacian_sharpen(image, alpha=0.1):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(gray, cv2.CV_64F, ksize=3)
    lap_norm = cv2.normalize(lap, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    lap_colored = cv2.cvtColor(lap_norm, cv2.COLOR_GRAY2BGR)

    sharpened = cv2.addWeighted(image, 1.0, lap_colored, -alpha, 0)
    return sharpened

if __name__ == "__main__":
    process_contrast()
