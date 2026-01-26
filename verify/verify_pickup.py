import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import time
import numpy as np
import pyautogui
import keyboard as kb
from core.vision import VisionSystem
from core.navigation import NavigationSystem
from config import ASSETS_DIR

def verify_pickup():
    print("=== 强制交互 F 键拾取测试脚本 ===")
    print("请切换到游戏窗口。")
    print("确保宝箱已开启，且掉落物在视野内。")
    print("脚本将在 5 秒后开始...")
    time.sleep(5)

    vision = VisionSystem()
    nav = NavigationSystem()
    
    # 1. 准备工作：按住 ALT 显示标签
    print("\n[第一步] 正在按住 ALT 以显示物品标签...")
    kb.press('alt')
    time.sleep(0.5)

    # 2. 寻找掉落物 (以恢复卷轴为例)
    print("[第二步] 正在扫描屏幕上的掉落物...")
    screen = vision.capture_screen()
    text_items = vision.scan_screen_for_text_events(screen)
    
    targets = []
    for item in text_items:
        if any(kw in item['text'] for kw in ["恢复", "卷轴", "强效", "战利品", "Scroll", "Restoration"]):
            targets.append(item)
            print(f"📍 发现目标: '{item['text']}' 位于 {item['center']}")

    # 3. 执行拾取流程
    if targets:
        print(f"\n[第三步] 开始执行精准 F 键拾取流程 (共 {len(targets)} 个目标)...")
        for i, target in enumerate(targets):
            pos = target['center']
            print(f"📦 正在前往第 {i+1} 个物品: {target['text']} ({pos})")
            pyautogui.moveTo(pos[0], pos[1], duration=0.1)
            time.sleep(0.1) 
            nav.loot_vacuum(duration=1.5, center_pos=pos)
    else:
        print("⚠️ 未能在屏幕上识别到特定标签，执行盲吸模式...")
        # 在屏幕中心偏上位置（通常是宝箱掉落区）执行一次长时间的强力盲吸
        blind_pos = (1280, 600) 
        pyautogui.moveTo(blind_pos[0], blind_pos[1], duration=0.2)
        nav.loot_vacuum(duration=6.0, center_pos=blind_pos)

    # 4. 结束
    kb.release('alt')
    print("\n=== 测试脚本执行完毕 ===")

if __name__ == "__main__":
    verify_pickup()
