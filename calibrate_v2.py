import cv2
import numpy as np
from pathlib import Path

def calibrate_from_image():
    # Load the reference image
    img_path = "assets/minimap_info.png"
    img = cv2.imread(img_path)
    if img is None:
        print(f"Error: Could not load {img_path}")
        return

    print(f"Image Resolution: {img.shape[1]}x{img.shape[0]}")

    # Define colors to search for based on user's previous covers
    # Minimap was covered with #5cad53 (RGB: 92, 173, 83 -> BGR: 83, 173, 92)
    # Wave info was covered with #7991bc (RGB: 121, 145, 188 -> BGR: 188, 145, 121)
    
    # Let's also look for the yellow covers in the latest screenshot if applicable, 
    # but the user specifically asked to use assets/minimap_info.png
    
    colors = {
        "Minimap (#5cad53)": ([70, 160, 80], [100, 185, 110]),
        "Wave Info (#7991bc)": ([170, 130, 110], [200, 160, 135])
    }

    results = {}

    for name, (lower, upper) in colors.items():
        mask = cv2.inRange(img, np.array(lower), np.array(upper))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if contours:
            # Find the largest area for each color
            c = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(c)
            results[name] = (x, y, x + w, y + h)
            print(f"Detected {name}: x1={x}, y1={y}, x2={x+w}, y2={y+h} (Size: {w}x{h})")
        else:
            print(f"Could not find color for {name}")

    # Based on the latest screenshot provided by user (with yellow boxes):
    # Yellow is roughly (0, 255, 255) in BGR
    yellow_lower = np.array([0, 200, 200])
    yellow_upper = np.array([50, 255, 255])
    yellow_mask = cv2.inRange(img, yellow_lower, yellow_upper)
    y_contours, _ = cv2.findContours(yellow_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    for i, c in enumerate(y_contours):
        if cv2.contourArea(c) > 1000:
            x, y, w, h = cv2.boundingRect(c)
            print(f"Detected Yellow Box {i+1}: x1={x}, y1={y}, x2={x+w}, y2={y+h} (Size: {w}x{h})")

if __name__ == "__main__":
    calibrate_from_image()
