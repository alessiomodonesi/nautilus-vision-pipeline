import cv2
import numpy as np
from PIL import Image

# --- Parametri coerenti con charuco_common.py / capture / calibrate ---
SQUARES_X = 8
SQUARES_Y = 11
SQUARE_LENGTH = 0.015   # 15 mm
MARKER_LENGTH = 0.011   # 11 mm
ARUCO_DICT = cv2.aruco.DICT_4X4_50

# --- Generazione board ---
aruco_dict = cv2.aruco.getPredefinedDictionary(ARUCO_DICT)
board = cv2.aruco.CharucoBoard(
    (SQUARES_X, SQUARES_Y), SQUARE_LENGTH, MARKER_LENGTH, aruco_dict
)

# IMPORTANTE: allinea la numerazione dei corner a quella attesa dagli script
# di calibrazione (legacy_pattern=True di default in CharucoSetup).
try:
    board.setLegacyPattern(True)
except AttributeError:
    print("WARN: setLegacyPattern non disponibile in questa OpenCV "
          "(versione < 4.6). Gli script funzioneranno lo stesso.")

# --- Render ad alta risoluzione ---
DPI = 600
PIXELS_PER_METER = DPI / 0.0254
img_w = int(SQUARES_X * SQUARE_LENGTH * PIXELS_PER_METER)
img_h = int(SQUARES_Y * SQUARE_LENGTH * PIXELS_PER_METER)

board_image = board.generateImage((img_w, img_h), marginSize=0, borderBits=1)

# Margine bianco per la stampa (2 cm)
margin_px = int(0.02 * PIXELS_PER_METER)
padded = cv2.copyMakeBorder(
    board_image, margin_px, margin_px, margin_px, margin_px,
    cv2.BORDER_CONSTANT, value=255
)

# --- Salva PNG e PDF ---
cv2.imwrite("charuco_board.png", padded)
Image.fromarray(padded).save("charuco_board.pdf", "PDF", resolution=DPI)

# --- Info ---
print(f"Board: {SQUARES_X}x{SQUARES_Y} squares")
print(f"Square: {SQUARE_LENGTH*1000:.1f} mm")
print(f"Marker: {MARKER_LENGTH*1000:.1f} mm")
print(f"Dizionario: DICT_4X4_50, legacy_pattern=True")
print(f"Dimensioni fisiche: "
      f"{SQUARES_X*SQUARE_LENGTH*1000:.0f} x {SQUARES_Y*SQUARE_LENGTH*1000:.0f} mm")
print("Salvati: charuco_board.pdf + charuco_board.png")
