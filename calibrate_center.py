import cv2
import numpy as np
import pyautogui
import time
from pathlib import Path
from config import MINIMAP_REGION, ASSETS_DIR, PLAYER_POS, MATCH_THRESHOLD

def calibrate_center_and_events():
    print("--- CALIBRATION MODE ---")
    print("Please stand at the EXACT center you want.")
    print("Capturing in 2 seconds...")
    time.sleep(2)
    
    # 1. Capture Minimap
    x1, y1, x2, y2 = MINIMAP_REGION
    w, h = x2 - x1, y2 - y1
    shot = pyautogui.screenshot(region=(x1, y1, w, h))
    minimap = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
    minimap_gray = cv2.cvtColor(minimap, cv2.COLOR_BGR2GRAY)
    
    # 2. Find Bonehand
    template_path = ASSETS_DIR / "minimap_bonehand.png"
    template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
    res = cv2.matchTemplate(minimap_gray, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    
    th, tw = template.shape[:2]
    icon_center_rel = (max_loc[0] + tw // 2, max_loc[1] + th // 2)
    abs_icon_pos = (x1 + icon_center_rel[0], y1 + icon_center_rel[1])
    
    # 3. Calculate current DX, DY relative to CURRENT PLAYER_POS
    dx = abs_icon_pos[0] - PLAYER_POS[0]
    dy = abs_icon_pos[1] - PLAYER_POS[1]
    
    print(f"\n[RESULTS]")
    print(f"Bonehand Score: {max_val:.2f}")
    print(f"Current Icon Abs Pos: {abs_icon_pos}")
    print(f"Current PLAYER_POS in config: {PLAYER_POS}")
    print(f"Current Offset: dx={dx:.1f}, dy={dy:.1f}")
    
    # 4. Suggest new PLAYER_POS
    # To make dx=0, dy=0 at this spot, PLAYER_POS should be equal to abs_icon_pos
    print(f"\n[ACTION]")
    print(f"To calibrate this spot as (0,0), update config.py with:")
    print(f"PLAYER_POS = {abs_icon_pos}")
    
    # 5. Scan for Events (OCR)
    print("\n[EVENT SCAN TEST]")
    from core.vision import VisionSystem
    vision = VisionSystem()
    screen = vision.capture_screen()
    # Default event selection ROI (center area)
    h_scr, w_scr = screen.shape[:2]
    roi_x1, roi_y1, roi_x2, roi_y2 = 400, 300, w_scr - 400, h_scr - 400
    
    text_items = vision.scan_screen_for_text_events(screen)
    if text_items:
        print(f"Detected {len(text_items)} text items in central area:")
        for item in text_items:
            print(f"  - '{item['text']}' at {item['center']} (conf: {item['confidence']:.2f})")
    else:
        print("No text events detected in central area.")

if __name__ == "__main__":
    calibrate_center_and_events()
