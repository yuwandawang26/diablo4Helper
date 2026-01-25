import cv2
import time
import numpy as np
from core.vision import VisionSystem
from core.navigation import NavigationSystem
from config import EVENT_SCAN_ROI, ASSETS_DIR

def verify_scan_area():
    print("=== Scan Area Verification Script ===")
    print("Please switch to the game window. The script will try to navigate to center.")
    print("Starting in 5 seconds...")
    time.sleep(5)

    vision = VisionSystem()
    nav = NavigationSystem()

    # 1. Try to navigate to center
    print("Navigating to center (using extrahand or bonehand)...")
    from core.agent import CompassBot
    bot = CompassBot()
    bot.log_status = lambda msg: print(f"[NAV] {msg}")
    
    success = bot.execute_return_to_center(template_name="bonehand")
    
    if success:
        print("[OK] Arrived at center.")
    else:
        print("[WARN] Could not fully arrive at center, proceeding to capture.")

    # 2. Capture screen
    print("Capturing screen...")
    screen = vision.capture_screen()

    # 3. Draw ROI box
    x1, y1, x2, y2 = EVENT_SCAN_ROI
    debug_screen = screen.copy()
    cv2.rectangle(debug_screen, (x1, y1), (x2, y2), (0, 255, 0), 3)
    cv2.putText(debug_screen, "EVENT_SCAN_ROI", (x1, y1 - 10), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

    # 4. Perform OCR
    print(f"Scanning ROI: {EVENT_SCAN_ROI}...")
    text_items = vision.scan_screen_for_text_events(screen, roi=EVENT_SCAN_ROI)

    # 5. Print and mark results
    if not text_items:
        print("[ERROR] No text detected in ROI!")
    else:
        print(f"[OK] Detected {len(text_items)} items:")
        for item in text_items:
            text = item['text']
            center = item['center']
            conf = item['confidence']
            # We skip printing the text itself to the console to avoid encoding errors
            print(f"  - [Text detected] Conf: {conf:.2f} Pos: {center}")
            
            # Mark on image
            cv2.circle(debug_screen, center, 5, (0, 0, 255), -1)
            # Drawing text on image is fine as it's handled by OpenCV (though it might show as ? if font doesn't support it)
            # We'll just draw a generic label
            cv2.putText(debug_screen, "ITEM", (center[0] + 10, center[1]), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    # 6. Save result
    save_path = "logs/verify_scan_event_area.png"
    vision.save_debug_image(debug_screen, "verify_scan_event_area.png")
    print(f"\n=== Finished ===")
    print(f"Debug image saved to: {save_path}")

if __name__ == "__main__":
    verify_scan_area()
