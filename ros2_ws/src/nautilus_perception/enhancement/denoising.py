import cv2
import os
from utils import *

# higher kernel for higher noise (it must be 3 < kernel < 7)
def median_blur(kernel, image):

    if kernel > 7 or kernel < 3:
        raise ValueError("Value is invalid")   
    
    denoised = cv2.medianBlur(image, kernel)
    return denoised

def bilateral_filter(image):

    denoised = cv2.bilateralFilter(image, d=9, sigmaColor=75, sigmaSpace=75)
    return denoised

def non_local_means_denoising(image):

    denoised = cv2.fastNlMeansDenoisingColored(image, None, 10, 10, 7, 21)
    return denoised
