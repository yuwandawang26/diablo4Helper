import cv2
import time
import numpy as np
import pyautogui
import keyboard as kb
from core.vision import VisionSystem
from core.navigation import NavigationSystem
from config import MINIMAP_REGION, PLAYER_POS, ASSETS_DIR, MATCH_THRESHOLD

def verify_open_chest():
    print("=== 开启宝箱与拾取测试脚本 (最终修正版) ===")
    print("请切换到游戏窗口。")
    print("脚本将在 5 秒后开始...")
    time.sleep(5)

    vision = VisionSystem()
    vision.load_template("chest_marker", ASSETS_DIR / "icon_health.png")
    vision.load_template("tip_bosschest", ASSETS_DIR / "tip_bosschest.png")
    nav = NavigationSystem()
    
    # 1. 导航至理想位置
    target_dx, target_dy = 13.0, 109.0
    x1, y1, _, _ = MINIMAP_REGION
    print("\n[第一步] 正在利用血井图标导航至理想位置...")
    arrived = False
    for i in range(30):
        minimap = vision.capture_minimap()
        res = vision.find_template(minimap, "chest_marker", threshold=0.5)
        if res:
            curr_x, curr_y, score = res
            abs_curr_x = x1 + curr_x
            abs_curr_y = y1 + curr_y
            raw_dx = abs_curr_x - PLAYER_POS[0]
            raw_dy = abs_curr_y - PLAYER_POS[1]
            error_x = raw_dx - target_dx
            error_y = raw_dy - target_dy
            
            if i % 5 == 0:
                print(f"步数 {i+1} | 误差: {error_x:.1f}, {error_y:.1f}")
            
            if abs(error_x) <= 1 and abs(error_y) <= 1:
                print("✅ 已到达理想位置！")
                arrived = True
                break
            
            if abs(error_x) > 1:
                nav.move("right" if error_x > 0 else "left", nav.calculate_duration(abs(error_x)))
            if abs(error_y) > 1:
                nav.move("down" if error_y > 0 else "up", nav.calculate_duration(abs(error_y)))
            time.sleep(0.1)
        else:
            print("❌ 丢失参考目标，停止导航。")
            break

    if not arrived: return

    # 2. 寻找宝箱交互
    print("\n[第二步] 正在寻找 Boss 宝箱交互触发点...")
    center_x, center_y = 1280, 720
    pyautogui.moveTo(center_x, center_y)
    time.sleep(0.5)
    
    trigger_pos = None
    for offset_y in range(0, 450, 40):
        current_pos = (center_x, center_y - offset_y)
        pyautogui.moveTo(current_pos[0], current_pos[1], duration=0.02)
        time.sleep(0.15) 
        
        screen = vision.capture_screen()
        res = vision.find_template(screen, "tip_bosschest", threshold=0.7)
        text_items = vision.scan_screen_for_text_events(screen, roi=(900, 100, 1660, 600))
        found_by_ocr = any("强效" in item['text'] for item in text_items)

        if res or found_by_ocr:
            # 🎯 记录触发点，并向上微调 65 像素以到达点击判定区
            trigger_pos = (current_pos[0], current_pos[1] - 65)
            print(f"🎯 检测到交互提示，锁定触发坐标 (已上移 65px): {trigger_pos}")
            break

    if trigger_pos:
        print(f"🖱️ 执行 F 键交互开启 (移动到 {trigger_pos})...")
        
        # 📸 调试：在点击前截屏并标注位置
        screen_debug = vision.capture_screen()
        tx, ty = int(trigger_pos[0]), int(trigger_pos[1])
        cv2.drawMarker(screen_debug, (tx, ty), (0, 0, 255), cv2.MARKER_CROSS, 50, 2)
        # 画标尺
        for i in range(0, 2560, 100):
            cv2.line(screen_debug, (i, 0), (i, 20), (0, 255, 0), 1)
            cv2.putText(screen_debug, str(i), (i, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
        for i in range(0, 1440, 100):
            cv2.line(screen_debug, (0, i), (20, i), (0, 255, 0), 1)
            cv2.putText(screen_debug, str(i), (25, i+5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
        vision.save_debug_image(screen_debug, "debug_chest_click_target.png")
        print(f"📸 调试图已保存至 logs/debug_chest_click_target.png，点击点: {trigger_pos}")

        pyautogui.moveTo(trigger_pos[0], trigger_pos[1]) 
        time.sleep(0.2)
        kb.press_and_release('f')
        print("⌨️ 已按下 F 键进行交互。")
        time.sleep(1.5) 
        
        print("⌨️ 正在吸取拾取...")
        kb.press('alt')
        time.sleep(0.5)
        nav.loot_vacuum(duration=6.0, center_pos=trigger_pos)
        kb.release('alt')
        
        print("\n[第五步] 8秒后回城...")
        time.sleep(8)
        kb.press_and_release('t')
    else:
        print("❌ 未能触发宝箱提示。")

if __name__ == "__main__":
    verify_open_chest()
