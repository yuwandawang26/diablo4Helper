import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import numpy as np
import pyautogui
from config import MINIMAP_REGION, ASSETS_DIR, LOGS_DIR, MATCH_THRESHOLD

def verify_bossdoor():
    print("Capturing minimap and searching for bossdoor icons...")
    
    # 1. Capture minimap
    x1, y1, x2, y2 = MINIMAP_REGION
    width = x2 - x1
    height = y2 - y1
    shot = pyautogui.screenshot(region=(x1, y1, width, height))
    minimap = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
    minimap_gray = cv2.cvtColor(minimap, cv2.COLOR_BGR2GRAY)
    
    # 2. Load templates
    templates = {
        "bosshand": ASSETS_DIR / "minimap_bosshand.png",
        "bossdoor": ASSETS_DIR / "icon_bossdoor.png",
        "bossdoor_merge": ASSETS_DIR / "icon_bossdoor_merge.png"
    }
    
    debug_img = minimap.copy()
    
    for name, path in templates.items():
        if not path.exists():
            print(f"Template {name} NOT FOUND at {path}")
            continue
            
        template = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if template is None:
            print(f"Failed to load {name}")
            continue
            
        # Match
        res = cv2.matchTemplate(minimap_gray, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        
        print(f"Template {name}: Best score = {max_val:.2f}")
        
        if max_val >= MATCH_THRESHOLD:
            th, tw = template.shape[:2]
            color = (0, 255, 0) if name == "bosshand" else (0, 0, 255)
            cv2.rectangle(debug_img, max_loc, (max_loc[0] + tw, max_loc[1] + th), color, 2)
            cv2.putText(debug_img, f"{name} ({max_val:.2f})", (max_loc[0], max_loc[1]-5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        else:
            print(f"  - {name} not found (below threshold {MATCH_THRESHOLD})")

    # 3. Save result
    output_path = LOGS_DIR / "verify_bossdoor.png"
    cv2.imwrite(str(output_path), debug_img)
    print(f"Debug image saved to: {output_path}")

if __name__ == "__main__":
    verify_bossdoor()
