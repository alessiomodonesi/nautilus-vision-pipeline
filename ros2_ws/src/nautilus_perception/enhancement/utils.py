import ensurepip
import os
import cv2

def list_images(folder: str):
    return [os.path.join(folder, f) for f in os.listdir(folder)]

def save_image(path: str, image):
    cv2.imwrite(path, image)