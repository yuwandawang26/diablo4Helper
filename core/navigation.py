import time
import json
import keyboard as kb
import pyautogui
import random
from pathlib import Path
from core.settings_manager import load_settings, resolve_direction

class NavigationSystem:
    def __init__(self, lang="cn", translations=None):
        self.lang = lang
        self.translations = translations or {}
        self.running_check = None  # callable() -> bool; set by agent to allow clean stop
        self._skills_last_cast: dict = {}
        self._load_skills()

    def _key(self, direction: str) -> str:
        """Resolve a logical direction ('up','down','left','right') to the
        actual keyboard key configured in settings (arrows or WASD)."""
        scheme = load_settings().get("move_keys", "arrows")
        return resolve_direction(direction, scheme)

    def _load_skills(self):
        """Load skill config from config/skills.json."""
        skills_path = Path(__file__).parent.parent / "config" / "skills.json"
        try:
            with open(skills_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.skills = data.get("skills", [])
        except Exception:
            self.skills = [
                {"id": 0, "key": "2", "interval": 0.25, "enabled": True},
                {"id": 1, "key": "3", "interval": 0.25, "enabled": True},
                {"id": 2, "key": "4", "interval": 0.25, "enabled": True},
            ]

    def reload_skills(self):
        """Hot-reload skills config (called after UI edits)."""
        self._load_skills()
        self._skills_last_cast.clear()

    def get_text(self, key, *args):
        txt = self.translations.get(key, key)
        if args:
            try:
                return txt.format(*args)
            except Exception:
                return txt
        return txt

    def move(self, direction: str, duration: float):
        """Presses a key for a specific duration."""
        key = self._key(direction)
        kb.press(key)
        time.sleep(duration)
        kb.release(key)
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
        print(self.get_text("clicking", x, y))
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
        """Cast each skill when its individual cooldown interval has elapsed."""
        now = time.time()
        for skill in self.skills:
            if not skill.get("enabled", True):
                continue
            sid = skill.get("id", skill.get("key", "?"))
            last = self._skills_last_cast.get(sid, 0)
            if now - last >= skill.get("interval", 0.25):
                key = skill.get("key", "")
                if key:
                    kb.press(key)
                    kb.release(key)
                    self._skills_last_cast[sid] = now

    def move_while_casting(self, direction, duration):
        """Moves in a direction while casting skills with per-skill intervals."""
        key = self._key(direction)
        kb.press(key)
        start = time.time()
        while time.time() - start < duration:
            if self.running_check and not self.running_check():
                break
            self.cast_skills()
            time.sleep(0.05)
        kb.release(key)

    def patrol_until_done(self, event_check=None, safety_timeout=600):
        """Quest-driven patrol: runs until event_check() returns True or
        safety_timeout seconds elapse.  No fixed duration — the caller's
        event_check decides when combat is over.

        Parameters
        ----------
        event_check : callable
            Called at the end of each patrol cycle (~3-4 s each).  Returning
            True stops the patrol immediately.
        safety_timeout : float
            Hard cap in seconds to avoid an infinite loop if OCR fails.
        """
        print(self.get_text("patrol_start", safety_timeout))
        start_time = time.time()

        quadrants = [
            ('up',    'down'),
            ('right', 'left'),
            ('down',  'up'),
            ('left',  'right'),
        ]
        current_quad_idx = 0

        while True:
            if self.running_check and not self.running_check():
                break
            if time.time() - start_time >= safety_timeout:
                print(f"[Patrol] 安全超时 {safety_timeout}s，退出巡逻")
                break
            if event_check and event_check():
                print("[Patrol] 任务完成信号，退出巡逻")
                break

            move_out_dir, move_back_dir = quadrants[current_quad_idx % 4]
            current_quad_idx += 1

            self.move_while_casting(move_out_dir, 0.8)

            wiggle_start = time.time()
            while time.time() - wiggle_start < 2.5:
                if self.running_check and not self.running_check():
                    break
                if time.time() - start_time >= safety_timeout:
                    break
                if event_check and event_check():
                    break
                rand_dir = random.choice(['up', 'down', 'left', 'right'])
                self.move_while_casting(rand_dir, 0.25)

            if event_check and event_check():
                print("[Patrol] 任务完成信号，退出巡逻")
                break

            self.move_while_casting(move_back_dir, 0.8)

        print(self.get_text("patrol_end"))

    def patrol_circular(self, duration=50, event_check=None):
        """按顺序在 4 个象限巡逻，但半径更紧凑。

        Parameters
        ----------
        duration : float
            Maximum patrol time in seconds.
        event_check : callable | None
            Optional zero-argument callable.  When it returns True the patrol
            stops immediately (e.g. offering-selection phase detected).
        """
        print(self.get_text("patrol_start", duration))
        start_time = time.time()
        
        quadrants = [
            ('up', 'down'),    
            ('right', 'left'), 
            ('down', 'up'),    
            ('left', 'right')  
        ]
        
        current_quad_idx = 0
        
        while time.time() - start_time < duration:
            if self.running_check and not self.running_check():
                break
            if event_check and event_check():
                print("[Patrol] 贡品选择阶段已检测到，提前结束巡逻")
                break
            move_out_dir, move_back_dir = quadrants[current_quad_idx % 4]
            current_quad_idx += 1

            self.move_while_casting(move_out_dir, 0.8)

            wiggle_start = time.time()
            while time.time() - wiggle_start < 2.5:
                if time.time() - start_time >= duration:
                    break
                if self.running_check and not self.running_check():
                    break
                if event_check and event_check():
                    break
                rand_dir = random.choice(['up', 'down', 'left', 'right'])
                self.move_while_casting(rand_dir, 0.25)

            if time.time() - start_time >= duration:
                break
            if self.running_check and not self.running_check():
                break
            if event_check and event_check():
                print("[Patrol] 贡品选择阶段已检测到，提前结束巡逻")
                break

            self.move_while_casting(move_back_dir, 0.8)
            
        print(self.get_text("patrol_end"))

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
        """已弃用：此函数不再使用F键拾取。请使用click_position直接点击装备。"""
        # 保留此函数以保持兼容性，但实际不再使用
        pass
