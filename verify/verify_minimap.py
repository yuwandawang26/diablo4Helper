import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import numpy as np
import pyautogui
from config import MINIMAP_REGION, ASSETS_DIR, LOGS_DIR, MATCH_THRESHOLD

def verify_minimap_capture():
    print("Capturing in 2 seconds... PLEASE SWITCH TO GAME WINDOW!")
    import time
    time.sleep(2)
    print(f"Current MINIMAP_REGION: {MINIMAP_REGION}")
    x1, y1, x2, y2 = MINIMAP_REGION
    w, h = x2 - x1, y2 - y1
    
    # 1. Capture what the bot sees
    shot = pyautogui.screenshot(region=(x1, y1, w, h))
    minimap = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
    minimap_gray = cv2.cvtColor(minimap, cv2.COLOR_BGR2GRAY)
    
    # 2. Load bonehand template
    template_path = ASSETS_DIR / "minimap_bonehand.png"
    if not template_path.exists():
        print(f"Error: {template_path} not found!")
        return
    
    template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
    
    # 3. Match
    res = cv2.matchTemplate(minimap_gray, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    
    print(f"Best match score for bonehand: {max_val:.2f}")
    
    # 4. Draw result
    debug_img = minimap.copy()
    th, tw = template.shape[:2]
    color = (0, 255, 0) if max_val >= MATCH_THRESHOLD else (0, 0, 255)
    cv2.rectangle(debug_img, max_loc, (max_loc[0] + tw, max_loc[1] + th), color, 2)
    cv2.putText(debug_img, f"Score: {max_val:.2f}", (max_loc[0], max_loc[1]-10), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    
    # 5. Save
    out_path = LOGS_DIR / "verify_minimap_capture.png"
    cv2.imwrite(str(out_path), debug_img)
    print(f"Debug image saved to: {out_path}")
    
    if max_val < MATCH_THRESHOLD:
        print("!!! BONEHAND NOT DETECTED !!!")
        print(f"The score {max_val:.2f} is below threshold {MATCH_THRESHOLD}.")
    else:
        print("Bonehand detected successfully!")

if __name__ == "__main__":
    verify_minimap_capture()
