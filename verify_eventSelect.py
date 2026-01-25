import cv2
import time
import numpy as np
from core.vision import VisionSystem
from core.navigation import NavigationSystem
from core.agent import CompassBot
from config import EVENT_SCAN_ROI

def verify_event_selection():
    print("=== 事件选择深度验证工具 ===")
    print("1. 正在初始化系统...")
    bot = CompassBot()
    vision = bot.vision
    nav = bot.nav
    
    print("\n请切换到游戏窗口，脚本将在 5 秒后开始...")
    for i in range(5, 0, -1):
        print(f"{i}...")
        time.sleep(1)

    # 1. 强制导航到中心
    print("2. 正在导航至中心点 (确保事件选项在屏幕上)...")
    nav.move_mouse_to_center()
    success = bot.execute_return_to_center(template_name="bonehand")
    if success:
        print("✅ 已到达中心点。")
    else:
        print("⚠️ 未能完全对齐中心，但将继续扫描。")

    # 2. 截图并扫描
    print("3. 正在截取屏幕并分析 OCR 结果...")
    time.sleep(0.5) # 等待 UI 稳定
    screen = vision.capture_screen()
    
    # 绘制 ROI 框用于调试
    debug_img = screen.copy()
    x1, y1, x2, y2 = EVENT_SCAN_ROI
    cv2.rectangle(debug_img, (x1, y1), (x2, y2), (0, 255, 0), 3)
    
    text_items = vision.scan_screen_for_text_events(screen, roi=EVENT_SCAN_ROI)
    
    print("\n--- OCR 原始扫描结果 (ROI 区域内) ---")
    found_events = []
    for item in text_items:
        raw_text = item['text']
        center = item['center']
        
        # 过滤掉干扰项
        if any(kw in raw_text for kw in ["选择", "开始", "混沌浪潮", "Select", "start"]):
            continue
            
        matched_name = bot.fuzzy_match_event(raw_text)
        if matched_name:
            print(f"🌟 [匹配成功] '{raw_text}' -> 识别为: {matched_name} (位置: {center})")
            found_events.append({'name': matched_name, 'center': center})
            # 在图上标记
            cv2.putText(debug_img, matched_name, (center[0], center[1] - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            cv2.circle(debug_img, center, 10, (0, 0, 255), -1)
        else:
            # 仅在控制台静默记录，不作为主要输出
            pass

    print("\n--- 最终决策 ---")
    if found_events:
        best = bot.select_best_event(found_events)
        print(f"🎯 最终决定选择: {best['name']}")
        if "混沌" in best['name']:
            print("🔥 注意：检测到混沌供品，已作为最高优先级锁定！")
    else:
        print("❌ 未能识别到任何有效事件。请检查 logs/verify_event_debug.png 查看绿色框是否覆盖了选项。")

    # 3. 保存调试图像
    save_path = "logs/verify_event_debug.png"
    vision.save_debug_image(debug_img, "verify_event_debug.png")
    print(f"\n✅ 调试截图已保存至: {save_path}")

if __name__ == "__main__":
    verify_event_selection()
