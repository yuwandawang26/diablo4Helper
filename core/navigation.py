import time
import keyboard as kb
import pyautogui
import random

class NavigationSystem:
    def __init__(self):
        pass

    def move(self, direction: str, duration: float):
        """Presses a key for a specific duration."""
        kb.press(direction)
        time.sleep(duration)
        kb.release(direction)
        time.sleep(0.1)

    def move_mouse_to_center(self):
        """Moves mouse to screen center (for 2560x1440)."""
        center_x, center_y = 1280, 720
        pyautogui.moveTo(center_x, center_y, duration=0.2)
        time.sleep(0.1)

    def move_mouse_to_position(self, pos):
        """Moves mouse to a specific position."""
        x, y = pos
        pyautogui.moveTo(x, y, duration=0.2)
        time.sleep(0.1)

    def click_position(self, pos):
        """移动鼠标到指定位置并左键点击。"""
        x, y = pos
        print(f"🖱️ 正在点击 ({x}, {y})")
        pyautogui.moveTo(x, y, duration=0.2)
        time.sleep(0.1)
        pyautogui.click()
        time.sleep(0.1)

    def calculate_duration(self, delta_pixels: int) -> float:
        ad = abs(delta_pixels)
        if ad > 150: return 1.0
        if ad > 80: return 0.5
        if ad > 40: return 0.25
        if ad > 20: return 0.12
        if ad > 8: return 0.06
        return 0.04

    def cast_skills(self):
        """Helper to cast skills quickly."""
        for skill_key in ['2', '3', '4']:
            kb.press(skill_key)
            kb.release(skill_key)
            time.sleep(0.02) 

    def move_while_casting(self, direction, duration):
        """Moves in a direction while spamming skills."""
        kb.press(direction)
        start = time.time()
        while time.time() - start < duration:
            self.cast_skills()
            time.sleep(0.1)
        kb.release(direction)

    def patrol_circular(self, duration=50):
        """
        按顺序在 4 个象限巡逻，但半径更紧凑。
        """
        print(f"⚔️ 开始紧凑巡逻，持续 {duration} 秒...")
        start_time = time.time()
        
        quadrants = [
            ('up', 'down'),    
            ('right', 'left'), 
            ('down', 'up'),    
            ('left', 'right')  
        ]
        
        current_quad_idx = 0
        
        while time.time() - start_time < duration:
            move_out_dir, move_back_dir = quadrants[current_quad_idx % 4]
            current_quad_idx += 1
            
            # 1. 向外移动（减小半径）
            # 原为 1.5s，现为 0.8s 以避免撞墙
            self.move_while_casting(move_out_dir, 0.8)
            
            # 2. 扭动/战斗（短时间）
            wiggle_start = time.time()
            while time.time() - wiggle_start < 2.5: # 从 4.0s 减小
                if time.time() - start_time >= duration: break
                
                # 随机小步移动
                rand_dir = random.choice(['up', 'down', 'left', 'right'])
                self.move_while_casting(rand_dir, 0.25)
            
            if time.time() - start_time >= duration: break

            # 3. 向后移动（与向外移动时间相同，以返回中心）
            self.move_while_casting(move_back_dir, 0.8)
            
        print("⚔️ 巡逻结束。")

    def playback_recorded_actions(self, filepath):
        """同步回放录制的键盘和鼠标动作。"""
        import json
        import ctypes
        import threading
        from pathlib import Path
        
        path = Path(filepath)
        if not path.exists():
            print(f"❌ 录制文件不存在: {filepath}")
            return False
            
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        mouse_actions = data['mouse_actions']
        kb_events = data['keyboard_events']
        
        if not mouse_actions and not kb_events:
            print("❌ 录制文件为空。")
            return False
            
        print(f"🎬 开始同步回放: {len(kb_events)} 个键盘动作, {len(mouse_actions)} 帧鼠标动作")
        
        start_time = time.time()
        # 使用 Windows API 进行更可靠的点击
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004
        
        def win32_click(down=True):
            if down:
                ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            else:
                ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

        def replay_keyboard():
            for ev in kb_events:
                # 目标时间点
                target_t = ev['t']
                # 等待到目标时间点
                while (time.time() - start_time) < target_t:
                    diff = target_t - (time.time() - start_time)
                    if diff > 0.005:
                        time.sleep(diff / 2)
                
                if ev['event_type'] == 'down':
                    kb.press(ev['name'])
                else:
                    kb.release(ev['name'])

        # 启动键盘回放线程
        kb_thread = threading.Thread(target=replay_keyboard)
        kb_thread.daemon = True
        kb_thread.start()

        # 主线程处理鼠标和进度日志
        last_click_state = False
        last_log_t = -1
        
        for action in mouse_actions:
            target_t = action['t']
            
            if int(target_t) > last_log_t:
                print(f"⏳ 回放进度: {int(target_t)}s")
                last_log_t = int(target_t)

            while (time.time() - start_time) < target_t:
                diff = target_t - (time.time() - start_time)
                if diff > 0.005:
                    time.sleep(diff / 2)
            
            # 移动鼠标
            pyautogui.moveTo(action['x'], action['y'])
            
            # 处理点击状态
            current_click = action['click']
            if current_click and not last_click_state:
                win32_click(True)
            elif not current_click and last_click_state:
                win32_click(False)
            last_click_state = current_click
                
        if last_click_state:
            win32_click(False)
            
        kb_thread.join(timeout=2.0)
        print("✅ 同步回放结束。")
        return True

    def loot_vacuum(self, duration=5.0, center_pos=(1280, 720)):
        """强制交互拾取：以重心周围进行扫动，并狂按 F 键进行拾取。"""
        cx, cy = center_pos
        print(f"🧹 强制交互拾取模式 (F 键)：以 {center_pos} 为中心执行 F 键吸取...")
        
        start_time = time.time()
        
        # 极窄轨道：微量偏移
        small_lanes = [cx, cx - 60, cx + 60]
        top_y = cy - 180
        bottom_y = cy + 40
        
        while time.time() - start_time < duration:
            for x in small_lanes:
                # 移动鼠标的同时狂按 F
                pyautogui.moveTo(x, top_y, duration=0.04)
                kb.press_and_release('f')
                pyautogui.moveTo(x, bottom_y, duration=0.04)
                kb.press_and_release('f')
                if time.time() - start_time >= duration: break
                    
        print("✅ 强制交互拾取结束。")
