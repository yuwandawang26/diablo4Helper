import cv2
import numpy as np
from pathlib import Path
from config import MINIMAP_REGION

# Load the reference image
ref_path = Path("assets/minimap_bossdoor.png")
if not ref_path.exists():
    print(f"❌ File not found: {ref_path}")
    exit(1)

img = cv2.imread(str(ref_path))
if img is None:
    print(f"❌ Failed to load image: {ref_path}")
    exit(1)

# Convert to HSV for better color detection
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

# Yellow color range in HSV
# Yellow is around H=20-30, S=100-255, V=100-255
lower_yellow = np.array([15, 100, 100])
upper_yellow = np.array([35, 255, 255])

# Create mask for yellow regions
mask = cv2.inRange(hsv, lower_yellow, upper_yellow)

# Find contours
contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

if not contours:
    print("⚠️ No yellow rectangle found. Trying different color ranges...")
    # Try a wider range
    lower_yellow = np.array([10, 50, 50])
    upper_yellow = np.array([40, 255, 255])
    mask = cv2.inRange(hsv, lower_yellow, upper_yellow)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

if contours:
    # Find the largest contour (should be the yellow rectangle)
    largest_contour = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(largest_contour)
    
    # Calculate center of the yellow rectangle
    center_x = x + w // 2
    center_y = y + h // 2
    
    print(f"✅ Found yellow rectangle:")
    print(f"   Bounding box: ({x}, {y}) to ({x+w}, {y+h})")
    print(f"   Center (relative to image): ({center_x}, {center_y})")
    
    # Convert to absolute screen coordinates
    # The image is the full minimap region
    x1, y1, x2, y2 = MINIMAP_REGION
    abs_center_x = x1 + center_x
    abs_center_y = y1 + center_y
    
    print(f"\n📍 Absolute screen coordinates:")
    print(f"   Boss Door Icon Center: ({abs_center_x}, {abs_center_y})")
    print(f"\n📝 Update config.py with:")
    print(f"   BOSS_DOOR_POS = ({abs_center_x}, {abs_center_y})")
    
    # Save debug visualization
    debug_img = img.copy()
    cv2.rectangle(debug_img, (x, y), (x+w, y+h), (0, 255, 0), 2)
    cv2.circle(debug_img, (center_x, center_y), 5, (0, 0, 255), -1)
    cv2.imwrite("logs/debug_bossdoor_position.png", debug_img)
    print(f"\n💾 Saved debug image to: logs/debug_bossdoor_position.png")
else:
    print("❌ No yellow rectangle found in the image.")
    print("   Please check if the yellow overlay is visible in the image.")
