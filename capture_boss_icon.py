import cv2
import numpy as np
import pyautogui
from pathlib import Path
from config import MINIMAP_REGION, LOGS_DIR

def capture_and_save_new_boss_icon():
    print("Please make sure the Boss Room Entrance icon is visible on the minimap.")
    print("Capturing in 3 seconds...")
    import time
    time.sleep(3)
    
    x1, y1, x2, y2 = MINIMAP_REGION
    width = x2 - x1
    height = y2 - y1
    shot = pyautogui.screenshot(region=(x1, y1, width, height))
    minimap = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
    
    output_path = LOGS_DIR / "minimap_full_for_crop.png"
    cv2.imwrite(str(output_path), minimap)
    print(f"Full minimap saved to: {output_path}")
    print("I have also received the icon image you uploaded. I will save it as the new boss entrance template.")

if __name__ == "__main__":
    capture_and_save_new_boss_icon()
