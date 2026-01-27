import time
import cv2
import pyautogui
import keyboard as kb
from pathlib import Path
from core.vision import VisionSystem
from core.navigation import NavigationSystem
from config import ASSETS_DIR, INVENTORY_REGION, MINIMAP_REGION, PLAYER_POS

def test_looting():
    print("=== 宝箱定位与智能拾取测试 (test_looting) ===")
    print("请确保你已经打完 BOSS，并且在血井附近。")
    print("脚本将在 3 秒后开始...")
    time.sleep(3)

    # 初始化系统
    vision = VisionSystem()
    nav = NavigationSystem()
    
    # 加载必要资源
    # 1. 定位用的血井
    vision.load_template("chest_marker", ASSETS_DIR / "icon_health.png")
    # 2. 宝箱提示
    vision.load_template("tip_bosschest", ASSETS_DIR / "tip_bosschest.png")
    # 3. 掉落物识别
    vision.load_template("tip_huifu", ASSETS_DIR / "tip_huifu.png")      # 恢复卷轴 (最重要)
    vision.load_template("icon_taigu", ASSETS_DIR / "icon_taigu.png")    # 太古
    vision.load_template("icon_myth", ASSETS_DIR / "icon_myth.png")      # 暗金/神话
    vision.load_template("icon_star", ASSETS_DIR / "icon_star.png")      # 传奇星号

    # --- 阶段 1: 重新定位到宝箱 ---
    print("\n[阶段 1] 正在前往宝箱 (使用修正后的偏移)...")
    
    # 目标偏移 (已修正为 3.0, 109.0)
    target_dx, target_dy = 12.0, 111.0 
    
    arrived = False
    for _ in range(20): # 最多尝试 20 次调整
        minimap = vision.capture_minimap()
        res = vision.find_template(minimap, "chest_marker", threshold=0.5)
        
        if not res:
            print("⚠️ 未在小地图找到血井 (chest_marker)，尝试盲找或等待...")
            time.sleep(0.5)
            continue
            
        icon_rel_x, icon_rel_y, _ = res
        
        # 计算图标相对于屏幕中心的偏移
        x1, y1, _, _ = MINIMAP_REGION
        abs_icon_x = x1 + icon_rel_x
        abs_icon_y = y1 + icon_rel_y
        
        raw_dx = abs_icon_x - PLAYER_POS[0]
        raw_dy = abs_icon_y - PLAYER_POS[1]
        
        error_x = raw_dx - target_dx
        error_y = raw_dy - target_dy
        
        print(f"定位误差: dx={error_x:.1f}, dy={error_y:.1f}")
        
        if abs(error_x) <= 2.0 and abs(error_y) <= 2.0: # 容差
            print("✅ 已到达宝箱位置！")
            arrived = True
            break
            
        if abs(error_x) > 2.0:
            nav.move("right" if error_x > 0 else "left", nav.calculate_duration(abs(error_x)))
        if abs(error_y) > 2.0:
            nav.move("down" if error_y > 0 else "up", nav.calculate_duration(abs(error_y)))
        time.sleep(0.2)

    if not arrived:
        print("⚠️ 未能精确对齐，但尝试继续...")

    # --- 阶段 2: 打开宝箱 ---
    print("\n[阶段 2] 寻找并打开宝箱...")
    nav.move_mouse_to_center()
    time.sleep(0.5)
    
    # 向上扫描寻找宝箱提示
    trigger_pos = None
    center_x, center_y = 1280, 720
    
    for offset_y in range(0, 450, 40):
        curr_pos = (center_x, center_y - offset_y)
        pyautogui.moveTo(curr_pos)
        time.sleep(0.15)
        
        screen = vision.capture_screen()
        if vision.find_template(screen, "tip_bosschest", threshold=0.7):
            # 修正点击位置 (向上 65 像素)
            trigger_pos = (curr_pos[0], curr_pos[1] - 65)
            print(f"🎯 发现宝箱提示！锁定位置: {trigger_pos}")
            break
    
    if trigger_pos:
        pyautogui.moveTo(trigger_pos)
        time.sleep(0.2)
        kb.press_and_release('f')
        print("🔓 按下 F 开启宝箱")
        time.sleep(1.5) # 等待掉落
    else:
        print("⚠️ 未找到宝箱提示，尝试直接在当前位置开启...")
        kb.press_and_release('f')
        time.sleep(1.5)

    # --- 阶段 3: 智能拾取循环 (30秒) ---
    print("\n[阶段 3] 开始智能拾取 (30秒限时)...")
    start_loot_time = time.time()
    last_alt_time = 0
    
    # 优先拾取列表 (模板名称, 描述, 阈值)
    priority_items = [
        ("tip_huifu", "恢复卷轴", 0.7),
        ("icon_taigu", "太古装备", 0.7),
        ("icon_myth", "暗金/神话", 0.7),
        ("icon_star", "传奇", 0.7)
    ]

    while time.time() - start_loot_time < 30:
        # 1. 每 5 秒按一次 Alt
        if time.time() - last_alt_time > 5.0:
            print("👀 按下 ALT 显示物品名称...")
            kb.press('alt')
            time.sleep(0.2)
            kb.release('alt')
            last_alt_time = time.time()
            time.sleep(0.5) # 等待标签浮现

        screen = vision.capture_screen()
        found_item = False

        # 2. 扫描高优先级物品
        for tmpl_name, desc, thresh in priority_items:
            res = vision.find_template(screen, tmpl_name, threshold=thresh)
            if res:
                item_x, item_y, _ = res
                print(f"✨ 发现 {desc}! 前往拾取: ({item_x}, {item_y})")
                
                # 移动并拾取 (笔刷式)
                nav.loot_vacuum(duration=1.5, center_pos=(item_x, item_y))
                found_item = True
                break # 捡完一个重新扫描，以免位置变动

        if not found_item:
            time.sleep(0.1)

    print("\n✅ 30秒拾取时间结束。自动停车。")

if __name__ == "__main__":
    test_looting()
