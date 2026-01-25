import cv2
import time
import numpy as np
from core.vision import VisionSystem
from core.navigation import NavigationSystem
from config import MINIMAP_REGION, PLAYER_POS, ASSETS_DIR, MATCH_THRESHOLD

def verify_chest_position():
    print("=== 宝箱随机位置移动测试脚本 ===")
    print("请切换到游戏窗口。")
    print("1. 请确保人物在宝箱所在的走廊区域。")
    print("2. 请将人物移动到一个【随机位置】（只要能看到血井图标即可）。")
    print("3. 脚本将在 5 秒后开始，尝试将人物引导至黄金开箱坐标 (13.0, 109.0)...")
    time.sleep(5)

    vision = VisionSystem()
    vision.load_template("chest_marker", ASSETS_DIR / "icon_health.png")
    nav = NavigationSystem()
    
    # 目标位置：我们之前校准好的黄金坐标
    target_dx, target_dy = 13.0, 109.0
    x1, y1, _, _ = MINIMAP_REGION

    print("\n开始导航...")
    for i in range(30): # 增加到 30 步以确保能走远一点回来
        minimap = vision.capture_minimap()
        res = vision.find_template(minimap, "chest_marker", threshold=0.5)
        
        if res:
            curr_x, curr_y, score = res
            abs_curr_x = x1 + curr_x
            abs_curr_y = y1 + curr_y
            
            # 计算当前偏移
            raw_dx = abs_curr_x - PLAYER_POS[0]
            raw_dy = abs_curr_y - PLAYER_POS[1]
            
            # 计算与目标的误差
            error_x = raw_dx - target_dx
            error_y = raw_dy - target_dy
            
            print(f"步数 {i+1}/30 | 误差: {error_x:.1f}, {error_y:.1f} | 匹配度: {score:.2f}")
            
            if abs(error_x) <= 1 and abs(error_y) <= 1:
                print("✅ 已到达理想位置！")
                break
            
            if abs(error_x) > 1:
                nav.move("right" if error_x > 0 else "left", nav.calculate_duration(abs(error_x)))
            if abs(error_y) > 1:
                nav.move("down" if error_y > 0 else "up", nav.calculate_duration(abs(error_y)))
            
            time.sleep(0.1)
        else:
            print(f"步数 {i+1}/30 | ❌ 丢失参考目标 (icon_health.png)")
            time.sleep(0.5)

    print("\n测试结束。")

if __name__ == "__main__":
    verify_chest_position()
