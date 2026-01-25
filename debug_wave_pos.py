import cv2
import numpy as np
import pyautogui
from pathlib import Path
from config import LOGS_DIR

def capture_wave_area_grid():
    print("Capturing a large area around the wave info with a grid...")
    print("Capturing in 2 seconds... PLEASE SWITCH TO GAME WINDOW!")
    import time
    time.sleep(2)
    
    # Capture a large area on the right side
    # x: 1500 to 2560, y: 0 to 500
    x, y, w, h = 1500, 0, 1060, 500
    shot = pyautogui.screenshot(region=(x, y, w, h))
    img = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
    
    # Draw grid
    grid_size = 50
    for i in range(0, w, grid_size):
        cv2.line(img, (i, 0), (i, h), (200, 200, 200), 1)
        cv2.putText(img, str(x + i), (i, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
        
    for j in range(0, h, grid_size):
        cv2.line(img, (0, j), (w, j), (200, 200, 200), 1)
        cv2.putText(img, str(y + j), (5, j + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
        
    output_path = LOGS_DIR / "wave_region_calibration.png"
    cv2.imwrite(str(output_path), img)
    print(f"Calibration image saved to: {output_path}")
    print("Please open this image and find the exact (x1, y1, x2, y2) for the 'Wave: X/10' text.")

if __name__ == "__main__":
    capture_wave_area_grid()
