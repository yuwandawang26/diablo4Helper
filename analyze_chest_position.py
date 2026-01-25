import cv2
import numpy as np
from pathlib import Path
from config import MINIMAP_REGION, ASSETS_DIR, LOGS_DIR

def find_template(haystack, template, threshold=0.6):
    haystack_gray = cv2.cvtColor(haystack, cv2.COLOR_BGR2GRAY)
    template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    
    # Pre-process template (crop edges like in vision.py)
    h, w = template_gray.shape
    crop = 4
    if h > 20 and w > 20:
        template_gray = template_gray[crop:-crop, crop:-crop]
    
    res = cv2.matchTemplate(haystack_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    
    if max_val < threshold:
        return None
        
    th, tw = template_gray.shape[:2]
    center_x = max_loc[0] + tw // 2
    center_y = max_loc[1] + th // 2
    return (center_x, center_y, max_val)

def main():
    # Load images
    readyloop_path = ASSETS_DIR / "minimap_readyloop.png"
    health_icon_path = ASSETS_DIR / "icon_health.png"
    
    if not readyloop_path.exists() or not health_icon_path.exists():
        print("Missing required assets")
        return

    readyloop_img = cv2.imread(str(readyloop_path))
    health_icon = cv2.imread(str(health_icon_path))
    
    # Extract minimap from readyloop
    x1, y1, x2, y2 = MINIMAP_REGION
    # Note: minimap_readyloop.png is a full screenshot (2560x1440)
    minimap_crop = readyloop_img[y1:y2, x1:x2]
    
    # Find health icon in minimap
    pos = find_template(minimap_crop, health_icon, threshold=0.5)
    
    debug_img = readyloop_img.copy()
    
    if pos:
        cx, cy, val = pos
        # Convert to global coordinates
        global_cx = x1 + cx
        global_cy = y1 + cy
        print(f"Found Health Icon at Minimap Local: ({cx}, {cy}), Global: ({global_cx}, {global_cy}), Confidence: {val:.2f}")
        
        # Draw on debug image
        cv2.circle(debug_img, (global_cx, global_cy), 10, (0, 0, 255), -1)
        cv2.rectangle(debug_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(debug_img, f"Chest Marker: ({global_cx}, {global_cy})", (global_cx + 15, global_cy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    else:
        print("Health icon not found on minimap")
        # Let's try finding it on the whole screen just in case
        pos_screen = find_template(readyloop_img, health_icon, threshold=0.5)
        if pos_screen:
            cx, cy, val = pos_screen
            print(f"Found Health Icon on FULL SCREEN at: ({cx}, {cy}), Confidence: {val:.2f}")
            cv2.circle(debug_img, (cx, cy), 15, (255, 255, 0), 3)
        else:
            print("Health icon not found on full screen either")

    output_path = LOGS_DIR / "debug_chest_marker.png"
    cv2.imwrite(str(output_path), debug_img)
    print(f"Debug image saved to: {output_path}")

if __name__ == "__main__":
    main()
