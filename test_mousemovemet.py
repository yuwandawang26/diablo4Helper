import time
import pyautogui
from core.navigation import NavigationSystem

def test_loot_brush():
    print("=== 宝箱开启瞬间：爆发拾取 (笔刷动作) 测试 ===")
    print("请将鼠标放在宝箱上（确保点击即可开启的位置）。")
    print("脚本将在 5 秒后开始...")
    time.sleep(5)

    nav = NavigationSystem()
    
    # 1. 获取当前开启位置
    trigger_pos = pyautogui.position()
    print(f"📍 开启位置确认: {trigger_pos}")

    # 2. 点击开启
    pyautogui.click(trigger_pos)
    print("🔓 宝箱已点击开启！")

    # 3. 立即执行爆发拾取 (阶段 1 的笔刷动作)
    # 用户要求延迟至 8 秒，并每 3 秒按一次 ALT
    print("🚀 开始爆发笔刷拾取...")
    nav.loot_vacuum(duration=8.0, center_pos=trigger_pos, loot_start_time=time.time())

    print("\n✅ 测试结束。请观察宝箱正下方的物品是否被吸起。")

if __name__ == "__main__":
    test_loot_brush()
