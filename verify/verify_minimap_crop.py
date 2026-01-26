import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import numpy as np
import pyautogui
import time
from config import MINIMAP_REGION, LOGS_DIR

def verify_minimap_crop():
    print("--- MINIMAP REGION VERIFICATION ---")
    print("Please ensure the game is visible.")
    print("Capturing in 2 seconds...")
    time.sleep(2)
    
    # 1. Capture full screen
    full_shot = pyautogui.screenshot()
    full_img = cv2.cvtColor(np.array(full_shot), cv2.COLOR_RGB2BGR)
    
    # 2. Crop based on MINIMAP_REGION (x1, y1, x2, y2)
    x1, y1, x2, y2 = MINIMAP_REGION
    cropped_minimap = full_img[y1:y2, x1:x2]
    
    # 3. Save the crop
    output_path = LOGS_DIR / "verify_minimap_crop.png"
    cv2.imwrite(str(output_path), cropped_minimap)
    
    print(f"\n[RESULTS]")
    print(f"MINIMAP_REGION used: {MINIMAP_REGION}")
    print(f"Cropped image saved to: {output_path}")
    print("Please open this image. If it perfectly contains ONLY the minimap, the region is correct.")
    print("If it's offset or contains other UI elements, we need to adjust the coordinates.")

if __name__ == "__main__":
    verify_minimap_crop()
