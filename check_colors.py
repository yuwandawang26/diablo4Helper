import cv2
import numpy as np
from pathlib import Path

def analyze_colors(image):
    # Get unique colors and their counts
    pixels = image.reshape(-1, 3)
    unique_colors, counts = np.unique(pixels, axis=0, return_counts=True)
    
    # Sort by count descending
    sorted_indices = np.argsort(-counts)
    print("Top 20 colors (BGR):")
    for i in range(min(20, len(sorted_indices))):
        idx = sorted_indices[i]
        color = unique_colors[idx]
        count = counts[idx]
        hex_val = '#{:02x}{:02x}{:02x}'.format(color[2], color[1], color[0])
        print(f"Color: {color} (Hex: {hex_val}), Count: {count}")

def main():
    img_path = Path("assets/minimap_info.png")
    img = cv2.imread(str(img_path))
    if img is None:
        print("Error: Could not read image")
        return
    
    analyze_colors(img)

if __name__ == "__main__":
    main()
