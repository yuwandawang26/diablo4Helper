import cv2
import time
import numpy as np
import pyautogui
from pathlib import Path
from config import EVENT_SCAN_ROI, WAVE_REGION, ETHER_REGION, LOGS_DIR

def draw_ruler(img):
    h, w = img.shape[:2]
    # Draw horizontal ruler
    for x in range(0, w, 200):
        cv2.line(img, (x, 0), (x, h), (100, 100, 100), 1)
        cv2.putText(img, str(x), (x + 5, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1)
    
    # Draw vertical ruler
    for y in range(0, h, 200):
        cv2.line(img, (0, y), (w, y), (100, 100, 100), 1)
        cv2.putText(img, str(y), (5, y + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1)

def verify_regions():
    print("=== 识别区域校验工具 (EVENT / WAVE / ETHER) ===")
    print("说明：该脚本将截取屏幕并框出三个关键识别区域，并带有坐标标尺。")
    print("1. 绿色框：事件选择区域 (EVENT_SCAN_ROI)")
    print("2. 蓝色框：波次识别区域 (WAVE_REGION)")
    print("3. 红色框：以太识别区域 (ETHER_REGION)")
    
    print("\n请立即切换到游戏窗口...")
    for i in range(3, 0, -1):
        print(f"{i}...")
        time.sleep(1)

    # 1. 截取全屏
    print("正在截取屏幕...")
    screenshot = pyautogui.screenshot()
    img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    debug_img = img.copy()

    # 2. 绘制标尺
    draw_ruler(debug_img)

    # 3. 绘制 ROI 区域
    # EVENT_SCAN_ROI (绿色)
    ex1, ey1, ex2, ey2 = EVENT_SCAN_ROI
    cv2.rectangle(debug_img, (ex1, ey1), (ex2, ey2), (0, 255, 0), 3)
    cv2.putText(debug_img, f"EVENT ROI: {EVENT_SCAN_ROI}", (ex1, ey1 - 10), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

    # WAVE_REGION (蓝色)
    wx1, wy1, wx2, wy2 = WAVE_REGION
    cv2.rectangle(debug_img, (wx1, wy1), (wx2, wy2), (255, 0, 0), 2)
    cv2.putText(debug_img, f"WAVE: {WAVE_REGION}", (wx1, wy1 - 10), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 1)

    # ETHER_REGION (红色)
    rx1, ry1, rx2, ry2 = ETHER_REGION
    cv2.rectangle(debug_img, (rx1, ry1), (rx2, ry2), (0, 0, 255), 2)
    cv2.putText(debug_img, f"ETHER: {ETHER_REGION}", (rx1, ry1 - 10), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)

    # 4. 保存结果
    save_path = LOGS_DIR / "verify_regions.png"
    cv2.imwrite(str(save_path), debug_img)
    
    print("\n" + "="*50)
    print(f"✅ 校验图像已保存至: {save_path}")
    print("请查看该图像，确认红、绿、蓝三个框是否准确覆盖了游戏中的对应文字。")
    print("="*50)

if __name__ == "__main__":
    verify_regions()
