import cv2
import numpy as np
from pathlib import Path

def analyze_reference_from_image():
    # The user provided a screenshot where they are at the chest
    # We need to find where the health well (icon_health.png) is on the minimap in that state
    img_path = "assets/minimap_readyloop.png" # Assuming this is the uploaded image saved or similar
    # Wait, the user didn't give a filename for the uploaded image. 
    # I will search for the latest screenshot in assets or logs.
    
    # Let's try to match icon_health.png on the full screen image provided.
    # Since I don't have the file path of the uploaded image directly, 
    # I'll use the one they just uploaded which I can see in the context.
    
    # I'll write a script that captures the CURRENT screen (assuming the user stays there)
    # or analyzes the provided assets/minimap_info.png if it has the reference.
    
    print("--- REFERENCE CALIBRATION ---")
    print("Finding icon_health.png on your minimap...")
    
    import pyautogui
    from config import MINIMAP_REGION, PLAYER_POS, ASSETS_DIR
    
    x1, y1, x2, y2 = MINIMAP_REGION
    w, h = x2 - x1, y2 - y1
    shot = pyautogui.screenshot(region=(x1, y1, w, h))
    minimap = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
    minimap_gray = cv2.cvtColor(minimap, cv2.COLOR_BGR2GRAY)
    
    template_path = ASSETS_DIR / "icon_health.png"
    template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
    
    res = cv2.matchTemplate(minimap_gray, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    
    if max_val < 0.5:
        print(f"Error: Reference icon NOT found (Score: {max_val:.2f})")
        return

    th, tw = template.shape[:2]
    icon_center_rel = (max_loc[0] + tw // 2, max_loc[1] + th // 2)
    abs_icon_pos = (x1 + icon_center_rel[0], y1 + icon_center_rel[1])
    
    raw_dx = abs_icon_pos[0] - PLAYER_POS[0]
    raw_dy = abs_icon_pos[1] - PLAYER_POS[1]
    
    print(f"\n[RESULTS]")
    print(f"Reference Found! Score: {max_val:.2f}")
    print(f"Icon Abs Pos: {abs_icon_pos}")
    print(f"Player Center: {PLAYER_POS}")
    print(f"Target Offset for Chest: dx={raw_dx:.1f}, dy={raw_dy:.1f}")
    print("\nCopy these dx/dy values and send them to me!")

if __name__ == "__main__":
    analyze_reference_from_image()
