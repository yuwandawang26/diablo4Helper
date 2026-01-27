import cv2
import numpy as np
from pathlib import Path
from config import MINIMAP_REGION, PLAYER_POS, ASSETS_DIR

def analyze_offset():
    # 1. Load the reference image provided by the user
    # Use ABSOLUTE path
    ref_img_path = Path(r"C:\Users\59552\.cursor\projects\c-Users-59552-Desktop-project-diablo4compassfarm\assets\c__Users_59552_AppData_Roaming_Cursor_User_workspaceStorage_c15624d11c76da21f45b34a3943dc9ab_images_image-1bf48fb7-820a-4469-a67a-176526938e82.png")
    
    if not ref_img_path.exists():
        print(f"Error: Reference image not found at {ref_img_path}")
        return

    img = cv2.imread(str(ref_img_path))
    if img is None:
        print("Error: Could not read image")
        return

    print(f"Loaded image shape: {img.shape}")
    
    # Check if we need to resize
    target_w, target_h = 2560, 1440
    if img.shape[1] != target_w or img.shape[0] != target_h:
        print(f"Resizing image from {img.shape[:2]} to ({target_h}, {target_w})")
        img = cv2.resize(img, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

    # 2. Crop the minimap region
    x1, y1, x2, y2 = MINIMAP_REGION
    minimap_crop = img[y1:y2, x1:x2]
    
    # Save crop for debug
    cv2.imwrite("logs/debug_ref_minimap_crop.png", minimap_crop)
    print("Saved minimap crop to logs/debug_ref_minimap_crop.png")

    # 3. Load the health well template (chest_marker)
    template_path = ASSETS_DIR / "icon_health.png"
    template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
    
    # Crop template border as done in VisionSystem
    crop_pixels = 4
    if template.shape[0] > 20 and template.shape[1] > 20:
        template = template[crop_pixels:-crop_pixels, crop_pixels:-crop_pixels]

    # 4. Find the template
    haystack_gray = cv2.cvtColor(minimap_crop, cv2.COLOR_BGR2GRAY)
    res = cv2.matchTemplate(haystack_gray, template, cv2.TM_CCOEFF_NORMED)
    
    threshold = 0.4
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    
    print(f"Match result: Max Val = {max_val:.3f}")
    
    if max_val < threshold:
        print("Error: Could not find chest marker in the minimap crop.")
        return

    # 5. Calculate positions
    th, tw = template.shape[:2]
    # Center of the icon relative to the crop
    icon_rel_x = max_loc[0] + tw // 2
    icon_rel_y = max_loc[1] + th // 2
    
    # Global position of the icon center
    icon_global_x = x1 + icon_rel_x
    icon_global_y = y1 + icon_rel_y
    
    # 6. Calculate OFFSET
    # We want the offset FROM player TO icon.
    # dx = Icon_X - Player_X
    # dy = Icon_Y - Player_Y
    
    dx = icon_global_x - PLAYER_POS[0]
    dy = icon_global_y - PLAYER_POS[1]
    
    print(f"--- CALCULATION RESULTS ---")
    print(f"Minimap Region: {MINIMAP_REGION}")
    print(f"Player Position (Center): {PLAYER_POS}")
    print(f"Icon Found at (Global): ({icon_global_x}, {icon_global_y})")
    print(f"Relative on Minimap: ({icon_rel_x}, {icon_rel_y})")
    print(f"\n>>> TARGET OFFSETS: dx = {dx:.1f}, dy = {dy:.1f} <<<")
    print("-" * 30)

    # Visual Debug
    debug_img = minimap_crop.copy()
    # Draw rectangle around match
    cv2.rectangle(debug_img, max_loc, (max_loc[0] + tw, max_loc[1] + th), (0, 0, 255), 2)
    # Draw center point
    cv2.circle(debug_img, (icon_rel_x, icon_rel_y), 2, (0, 255, 0), -1)
    
    # Draw Player relative position on the crop for visualization
    # Player relative x = PLAYER_POS[0] - x1
    player_rel_x = PLAYER_POS[0] - x1
    player_rel_y = PLAYER_POS[1] - y1
    cv2.circle(debug_img, (player_rel_x, player_rel_y), 3, (255, 0, 0), -1) # Blue dot for player
    
    cv2.imwrite("logs/debug_ref_analysis.png", debug_img)
    print("Saved visual analysis to logs/debug_ref_analysis.png")

if __name__ == "__main__":
    analyze_offset()
