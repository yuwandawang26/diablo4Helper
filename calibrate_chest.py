import cv2
import numpy as np
import pyautogui
import time
from pathlib import Path
from config import MINIMAP_REGION, ASSETS_DIR, PLAYER_POS, MATCH_THRESHOLD

def calibrate_chest_marker():
    print("--- CHEST MARKER CALIBRATION (v2) ---")
    print("Please stand so the LEFTMOST chest icon is at the center of your minimap.")
    print("Capturing in 2 seconds...")
    time.sleep(2)
    
    # 1. Capture Minimap
    x1, y1, x2, y2 = MINIMAP_REGION
    w, h = x2 - x1, y2 - y1
    shot = pyautogui.screenshot(region=(x1, y1, w, h))
    minimap = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
    minimap_gray = cv2.cvtColor(minimap, cv2.COLOR_BGR2GRAY)
    
    # 2. Find Chest Marker (leftmost)
    template_path = ASSETS_DIR / "icon_chest.png" 
    if not template_path.exists():
        print(f"Error: {template_path} not found!")
        return
        
    template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
    res = cv2.matchTemplate(minimap_gray, template, cv2.TM_CCOEFF_NORMED)
    loc = np.where(res >= MATCH_THRESHOLD)
    points = list(zip(*loc[::-1]))
    
    if not points:
        print(f"Error: Chest Marker (icon_chest.png) NOT detected (Max Score: {np.max(res):.2f}).")
        return

    # Find the leftmost point
    leftmost_pt = min(points, key=lambda p: p[0])
    th, tw = template.shape[:2]
    icon_center_rel = (leftmost_pt[0] + tw // 2, leftmost_pt[1] + th // 2)
    abs_icon_pos = (x1 + icon_center_rel[0], y1 + icon_center_rel[1])
    
    # 3. Calculate current Raw DX, DY
    raw_dx = abs_icon_pos[0] - PLAYER_POS[0]
    raw_dy = abs_icon_pos[1] - PLAYER_POS[1]
    
    print(f"\n[RESULTS]")
    print(f"Chest Marker detected! Best Score: {np.max(res):.2f}")
    print(f"Leftmost Icon Abs Pos: {abs_icon_pos}")
    print(f"Current PLAYER_POS: {PLAYER_POS}")
    print(f"Current Error (Distance from center): dx={raw_dx:.1f}, dy={raw_dy:.1f}")
    
    print(f"\n[GOAL]")
    print(f"The bot will now move until dx=0.0 and dy=0.0 for the leftmost chest icon.")

if __name__ == "__main__":
    calibrate_chest_marker()
