import pyautogui
import cv2
import numpy as np
from pathlib import Path

def main():
    print("Capturing in 3 seconds... Switch to the game window!")
    import time
    time.sleep(3)
    
    # 截取右上角一个巨大的范围 (从 X=1500, Y=0 开始，截取 1060x400)
    x, y, w, h = 1500, 0, 1060, 400
    shot = pyautogui.screenshot(region=(x, y, w, h))
    img = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
    
    # 画坐标网格（每 50 像素一根线）
    for i in range(0, w, 50):
        cv2.line(img, (i, 0), (i, h), (200, 200, 200), 1)
        cv2.putText(img, str(x + i), (i, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
        
    for j in range(0, h, 50):
        cv2.line(img, (0, j), (w, j), (200, 200, 200), 1)
        cv2.putText(img, str(y + j), (5, j + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

    output_path = Path("logs/find_wave_pos.png")
    output_path.parent.mkdir(exist_ok=True)
    cv2.imwrite(str(output_path), img)
    print(f"探测截图已保存至: {output_path}")
    print("请查看该图，找到'波次'文字所在的精确坐标范围。")

if __name__ == "__main__":
    main()
