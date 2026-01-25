import cv2
import numpy as np
import pyautogui
import time
from pathlib import Path
from config import MINIMAP_REGION, PLAYER_POS, ASSETS_DIR

def analyze_health_reference():
    print("--- HEALTH WELL REFERENCE CALIBRATION ---")
    print("Please stand at the EXACT spot where you want the character to be at the chest.")
    print("Capturing in 2 seconds...")
    time.sleep(2)
    
    x1, y1, x2, y2 = MINIMAP_REGION
    w, h = x2 - x1, y2 - y1
    shot = pyautogui.screenshot(region=(x1, y1, w, h))
    minimap = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
    minimap_gray = cv2.cvtColor(minimap, cv2.COLOR_BGR2GRAY)
    
    # Load the NEW icon_health.png provided by user
    template_path = ASSETS_DIR / "icon_health.png"
    if not template_path.exists():
        print(f"Error: {template_path} not found!")
        return
        
    template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
    res = cv2.matchTemplate(minimap_gray, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    
    if max_val < 0.5:
        print(f"Error: Health icon NOT found (Max Score: {max_val:.2f})")
        return

    th, tw = template.shape[:2]
    icon_center_rel = (max_loc[0] + tw // 2, max_loc[1] + th // 2)
    abs_icon_pos = (x1 + icon_center_rel[0], y1 + icon_center_rel[1])
    
    raw_dx = abs_icon_pos[0] - PLAYER_POS[0]
    raw_dy = abs_icon_pos[1] - PLAYER_POS[1]
    
    print(f"\n[RESULTS]")
    print(f"Health Icon detected! Score: {max_val:.2f}")
    print(f"Icon Abs Pos: {abs_icon_pos}")
    print(f"Current PLAYER_POS: {PLAYER_POS}")
    print(f"Current Raw Offset: dx={raw_dx:.1f}, dy={raw_dy:.1f}")
    
    print(f"\n[ACTION]")
    print(f"Send me these dx/dy values. I will use them as the TARGET for chest navigation.")

if __name__ == "__main__":
    analyze_health_reference()
