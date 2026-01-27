import time
import cv2
import json
import numpy as np
import pyautogui
from datetime import datetime
from pathlib import Path
from config import ASSETS_DIR, PLAYER_POS, MINIMAP_REGION, MATCH_THRESHOLD, CENTER_TOLERANCE, BOSS_DOOR_TOLERANCE, MAX_STEPS, DESIRED_EVENTS_CN, DESIRED_EVENTS_EN, LOGS_DIR, INVENTORY_REGION, EVENT_SCAN_ROI, TRANSLATIONS_PATH
from core.vision import VisionSystem
from core.navigation import NavigationSystem
from core.enums import GameState
import keyboard as kb

class CompassBot:
    def __init__(self, lang="cn"):
        self.lang = lang
        self.load_translations()
        self.vision = VisionSystem(lang=lang, translations=self.translations)
        self.nav = NavigationSystem(lang=lang, translations=self.translations)
        self.state = GameState.IDLE
        self.current_wave = 0
        self.max_waves = 10
        self.compass_count = 1
        self.selected_event_target = None 
        self.desired_events = DESIRED_EVENTS_EN if lang == "en" else DESIRED_EVENTS_CN
        self.load_assets()

    def load_translations(self):
        """Load translations from JSON file."""
        try:
            with open(TRANSLATIONS_PATH, "r", encoding="utf-8") as f:
                all_translations = json.load(f)
                self.translations = all_translations.get(self.lang, all_translations.get("en", {}))
        except Exception as e:
            print(f"Error loading translations: {e}")
            self.translations = {}

    def get_text(self, key, *args):
        """Helper to get translated text."""
        txt = self.translations.get(key, key)
        if args:
            try:
                return txt.format(*args)
            except Exception:
                return txt
        return txt

    def load_assets(self):
        """Load all necessary assets on startup."""
        self.vision.load_template("bonehand", ASSETS_DIR / "minimap_bonehand.png")
        self.vision.load_template("extrahand", ASSETS_DIR / "minimap_extrahand.png")
        self.vision.load_template("bosshand", ASSETS_DIR / "minimap_bosshand.png")
        self.vision.load_template("bossdoor", ASSETS_DIR / "icon_bossdoor.png")
        self.vision.load_template("bossdoor_merge", ASSETS_DIR / "icon_bossdoor_merge.png")
        # icon_health.png = 玩家在宝箱跟前时小地图上的位置参照（血井图标）
        self.vision.load_template("chest_marker", ASSETS_DIR / "icon_health.png")
        # 宝箱交互提示图标 (OpenCV 识别)
        self.vision.load_template("tip_bosschest", ASSETS_DIR / "tip_bosschest.png")
        # icon_key.png = 宝箱在小地图上的图标 (key tab in inventory)
        self.vision.load_template("chest_icon", ASSETS_DIR / "icon_key.png")
        # Optional key tab icon from backpack UI
        self.vision.load_template("backpack_key", ASSETS_DIR / "backpack_key.png")
        # New assets for next compass activation
        self.vision.load_template("compass", ASSETS_DIR / "icon_compass.png")
        self.vision.load_template("compass_door", ASSETS_DIR / "icon_compassdoor.png")
        self.vision.load_template("modal_usekey", ASSETS_DIR / "modal_usekey.png")
        self.vision.load_template("modal_tp", ASSETS_DIR / "modal_tp_compass.png")
        self.vision.load_template("start_icon", ASSETS_DIR / "icon_start.png")
        # 装备拾取模板
        self.vision.load_template("tip_huifu", ASSETS_DIR / "tip_huifu.png")      # 恢复卷轴
        self.vision.load_template("icon_taigu_tag", ASSETS_DIR / "icon_taigu_tag.png")  # 太古标签
        # 混沌事件模板（优先检测）
        self.vision.load_template("hundun_event", ASSETS_DIR / "hundun_event.png")  # 混沌事件

    def log_status(self, message):
        """标准化日志格式，包含罗盘、波次和以太信息。"""
        ether_count = self.vision.read_ether_count()
        ether_str = f"[E:{ether_count}]" if ether_count is not None else "[E:?]"
        print(f"[C{self.compass_count}][W{self.current_wave}/{self.max_waves}]{ether_str} {message}")

    def run(self):
        """主状态机循环 - 恢复全自动化"""
        print(self.get_text("start_prompt"))
        time.sleep(3)
        
        # 初始状态同步：智能检测当前位置
        screen = self.vision.capture_screen()
        minimap = self.vision.capture_minimap()
        wave_data = self.vision.read_wave_number()
        
        # 1. 优先检查是否在副本波次中
        if isinstance(wave_data, tuple) or (isinstance(wave_data, str) and (any(kw in wave_data for kw in ["波", "Wave", "/"]))):
            text_items = self.vision.scan_screen_for_text_events(screen, roi=EVENT_SCAN_ROI)
            found_any_event = any(self.fuzzy_match_event(it['text']) for it in text_items)
            
            if found_any_event:
                self.log_status(self.get_text("sync_events"))
                self.state = GameState.SCANNING_FOR_EVENTS
            else:
                self.log_status(self.get_text("sync_wave"))
                self.state = GameState.NAVIGATING_TO_CENTER
                
        # 2. 检查是否在首领房入口或大门前
        elif self.vision.find_template(minimap, "bosshand") or self.vision.find_template(minimap, "bossdoor"):
            self.log_status(self.get_text("sync_boss"))
            self.state = GameState.NAVIGATING_TO_BOSS
            
        # 3. 检查是否已经在宝箱房（打完 Boss）
        elif self.vision.find_template(minimap, "chest_marker"):
            self.log_status(self.get_text("sync_chest"))
            self.state = GameState.NAVIGATING_TO_CHEST
            
        # 4. 默认状态：在城镇
        else:
            self.log_status(self.get_text("sync_town"))
            self.state = GameState.ACTIVATING_NEXT_COMPASS

        self.current_wave = 0
        self.max_waves = 10

        while True:
            try:
                # 1. 检查波次信息（仅在战斗或等待阶段）
                if self.state in [GameState.SCANNING_FOR_EVENTS, GameState.SELECTING_EVENT, GameState.WAITING_FOR_WAVE_START, GameState.COMBAT]:
                    wave_data = self.vision.read_wave_number()
                    if isinstance(wave_data, tuple):
                        curr, m_waves = wave_data
                        if curr != self.current_wave:
                            self.current_wave = curr
                            self.max_waves = m_waves
                            self.log_status(self.get_text("wave_update", curr, m_waves))
                            
                            if self.state == GameState.WAITING_FOR_WAVE_START and curr > 0:
                                self.log_status(self.get_text("wave_start_combat"))
                                self.state = GameState.COMBAT
                    elif isinstance(wave_data, str):
                        # 如果不是元组但获取了文本，记录原始 OCR
                        if any(kw in wave_data for kw in ["波", "Wave", "/"]):
                            self.log_status(self.get_text("wave_ocr_debug", wave_data))

                # 2. 状态机
                if self.state == GameState.NAVIGATING_TO_CENTER:
                    # 导航前确保鼠标在中心
                    self.nav.move_mouse_to_center()
                    success = self.execute_return_to_center(template_name="bonehand")
                    if success:
                        self.log_status(self.get_text("reached_center"))
                        self.state = GameState.SCANNING_FOR_EVENTS
                    else:
                        time.sleep(1)

                elif self.state == GameState.SCANNING_FOR_EVENTS:
                    self.nav.move_mouse_to_center()
                    time.sleep(0.5)
                    screen = self.vision.capture_screen()
                    
                    # 🔥 优先使用OpenCV模板匹配检测混沌事件
                    hundun_result = self.vision.find_template(screen, "hundun_event", threshold=0.7)
                    if hundun_result:
                        hundun_x, hundun_y, confidence = hundun_result
                        self.log_status(f"🔥 [OpenCV] 优先检测到混沌事件! 位置: ({hundun_x}, {hundun_y}), 置信度: {confidence:.2f}")
                        # 直接选择混沌事件，跳过OCR识别
                        self.selected_event_target = {
                            'name': self.get_text("hellborne_event_name"),
                            'center': (hundun_x, hundun_y)
                        }
                        self.state = GameState.SELECTING_EVENT
                        continue
                    
                    # 如果OpenCV未检测到，继续使用OCR识别
                    text_items = self.vision.scan_screen_for_text_events(screen, roi=EVENT_SCAN_ROI)
                    
                    found_events = []
                    matches_output = []
                    is_boss_phase = False
                    
                    for item in text_items:
                        raw_text = item['text']
                        if any(kw in raw_text for kw in ["选择", "开始", "混沌浪潮", "Select", "start", "Wave", "Offerings"]):
                            continue
                            
                        # 📍 关键修复：如果在扫描事件界面看到了首领入口文字，立即同步状态
                        if any(kw in raw_text for kw in ["理事会", "巴图克", "Council", "Barthuk"]):
                            self.log_status(self.get_text("boss_text_sync", raw_text))
                            self.state = GameState.SELECTING_BOSS_ENTRY
                            is_boss_phase = True
                            break

                        matched_name = self.fuzzy_match_event(raw_text)
                        if matched_name:
                            found_events.append({'name': matched_name, 'center': item['center']})
                            matches_output.append(f"🌟 [MATCH] '{raw_text}' -> {matched_name} ({item['center']})")
                    
                    if is_boss_phase:
                        continue # 直接进入下一轮状态机循环处理 SELECTING_BOSS_ENTRY
                        
                    if found_events:
                        print(self.get_text("ocr_raw_header"))
                        for line in matches_output: print(line)
                        
                        best_choice = self.select_best_event(found_events)
                        print(self.get_text("final_decision_header"))
                        print(self.get_text("final_decision_pick", best_choice['name']))
                        if any(kw in best_choice['name'] for kw in ['混沌', 'Offerings']):
                            print(self.get_text("aether_warning"))
                        print("-" * 30 + "\n")
                        
                        self.selected_event_target = best_choice
                        self.state = GameState.SELECTING_EVENT
                    else:
                        time.sleep(1)

                elif self.state == GameState.SELECTING_EVENT:
                    if self.selected_event_target:
                        target = self.selected_event_target
                        self.nav.click_position(target['center'])
                        self.log_status(self.get_text("click_wait_wave", target['center']))
                        self.state = GameState.WAITING_FOR_WAVE_START
                        self.wave_wait_start_time = time.time()
                    else:
                        self.state = GameState.SCANNING_FOR_EVENTS

                elif self.state == GameState.WAITING_FOR_WAVE_START:
                    if time.time() - self.wave_wait_start_time > 15:
                        self.log_status(self.get_text("timeout_wait_wave"))
                        self.state = GameState.NAVIGATING_TO_CENTER
                    else:
                        time.sleep(1)

                elif self.state == GameState.COMBAT:
                    self.log_status(self.get_text("combat_start", self.current_wave, self.max_waves))
                    # 围绕校准中心进行圆形巡逻
                    self.nav.patrol_circular(duration=60)
                    self.log_status(self.get_text("patrol_end"))
                    
                    if self.current_wave >= self.max_waves and self.max_waves > 0:
                        self.log_status(self.get_text("all_waves_done"))
                        self.state = GameState.NAVIGATING_TO_BOSS
                    else:
                        self.state = GameState.NAVIGATING_TO_CENTER

                elif self.state == GameState.NAVIGATING_TO_BOSS:
                    self.log_status(self.get_text("moving_to_boss_entry"))
                    success = self.execute_return_to_center(template_name="bosshand")
                    if success:
                        self.log_status(self.get_text("arrived_boss_entry"))
                        time.sleep(1.0)
                        self.state = GameState.SELECTING_BOSS_ENTRY
                    else:
                        time.sleep(1)

                elif self.state == GameState.SELECTING_BOSS_ENTRY:
                    self.nav.move_mouse_to_center()
                    
                    # 选择前读取以太数量
                    ether_count = self.vision.read_ether_count()
                    if ether_count is not None:
                        self.log_status(self.get_text("ether_count", ether_count))
                        # 修正判断数值：大于 1066 时选择巴图克
                        target_text = "巴图克" if ether_count > 1066 else "理事会"
                        if self.lang == "en":
                            target_text = "Barthuk" if ether_count > 1066 else "Council"
                    else:
                        self.log_status(self.get_text("no_ether_reading"))
                        target_text = "Barthuk" if self.lang == "en" else "巴图克" # Based on user preference or safety
                        # The original code used "理事会", let's stick to that default
                        target_text = "Council" if self.lang == "en" else "理事会"
                    
                    self.log_status(self.get_text("scanning_boss", target_text))
                    screen = self.vision.capture_screen()
                    text_items = self.vision.scan_screen_for_text_events(screen)
                    
                    target = None
                    for item in text_items:
                        if target_text in item['text']:
                            target = item
                            break
                    
                    if target:
                        self.log_status(self.get_text("clicking_boss", target['text']))
                        self.nav.click_position(target['center'])
                        time.sleep(2)  # 减少等待时间，因为没有传送
                        self.state = GameState.NAVIGATING_TO_BOSS_DOOR
                    else:
                        time.sleep(2)

                elif self.state == GameState.NAVIGATING_TO_BOSS_DOOR:
                    self.log_status(self.get_text("moving_to_boss_door"))
                    self.nav.move_mouse_to_center()
                    success = self.execute_return_to_center(template_name="bossdoor")
                    if success:
                        self.log_status(self.get_text("arrived_boss_door"))
                        self.state = GameState.INTERACTING_WITH_BOSS_DOOR
                    else:
                        time.sleep(1)

                elif self.state == GameState.INTERACTING_WITH_BOSS_DOOR:
                    center_x, center_y = 1280, 720
                    # 将鼠标移动到通常出现交互文本的上部区域
                    self.nav.move_mouse_to_position((center_x, center_y - 200))
                    time.sleep(1.2) # 等待文本出现
                    
                    screen = self.vision.capture_screen()
                    # 扩大 ROI 以覆盖更多屏幕上部
                    # 从 y=100 到 y=720 (中心)，全宽度
                    interaction_roi = (0, 100, 2560, 720)
                    text_items = self.vision.scan_screen_for_text_events(screen, roi=interaction_roi)
                    
                    # 调试：如果未匹配到任何内容，记录发现的内容
                    if not text_items:
                        self.log_status(self.get_text("ocr_empty"))
                    
                    found_interaction = None
                    for item in text_items:
                        t = item['text']
                        # 对 "议会大门" 进行更广泛的匹配
                        if any(kw in t for kw in ["议", "会", "大", "门", "Council", "Door"]):
                            found_interaction = item
                            break
                    
                    if found_interaction:
                        self.log_status(self.get_text("opening_door", found_interaction['text'], found_interaction['center']))
                        self.nav.click_position(found_interaction['center'])
                        self.log_door_opened()
                        time.sleep(2.0)
                        
                        # 弃用录制，回归之前的逻辑
                        self.state = GameState.BOSS_FIGHT
                    else:
                        # 记录前几个检测到的文本，以帮助调试 OCR 看到的内容
                        if text_items:
                            detected_sample = ", ".join([it['text'] for it in text_items[:3]])
                            self.log_status(self.get_text("ocr_no_door_kw", detected_sample))
                        
                        self.log_status(self.get_text("no_interaction_retry"))
                        time.sleep(1)

                elif self.state == GameState.BOSS_FIGHT:
                    self.log_status(self.get_text("boss_fight_start"))
                    self.nav.move("up", 6.0)
                    self.log_status(self.get_text("arrived_boss_area"))
                    
                    start_time = time.time()
                    while time.time() - start_time < 10:
                        self.nav.cast_skills()
                        time.sleep(0.1)
                    
                    self.log_status(self.get_text("boss_fight_done"))
                    self.state = GameState.NAVIGATING_TO_CHEST

                elif self.state == GameState.NAVIGATING_TO_CHEST:
                    self.log_status(self.get_text("moving_to_chest"))
                    self.nav.move_mouse_to_center()
                    # 使用参照物逻辑：寻找 icon_health 并将其对齐到目标偏移 (13, 109)
                    # 109 表示图标在玩家中心下方，即人物在图标上方（宝箱前）
                    success = self.execute_return_to_center(template_name="chest_marker")
                    if success:
                        self.log_status(self.get_text("arrived_chest_precision"))
                        self.state = GameState.INTERACTING_WITH_CHEST
                    else:
                        self.log_status(self.get_text("failed_chest_alignment"))
                        time.sleep(1)

                elif self.state == GameState.INTERACTING_WITH_CHEST:
                    self.log_status(self.get_text("searching_boss_chest"))
                    center_x, center_y = 1280, 720
                    
                    trigger_pos = None
                    pyautogui.moveTo(center_x, center_y)
                    time.sleep(0.3)
                    
                    # 极速向上寻找
                    for offset_y in range(0, 450, 40): 
                        current_mouse_pos = (center_x, center_y - offset_y)
                        pyautogui.moveTo(current_mouse_pos[0], current_mouse_pos[1], duration=0.02)
                        time.sleep(0.15) 
                        
                        screen = self.vision.capture_screen()
                        
                        # 检查是否触发了宝箱悬停文字
                        # 1. 优先模板匹配
                        res = self.vision.find_template(screen, "tip_bosschest", threshold=0.7)
                        # 2. OCR 备选
                        chest_roi = (900, 100, 1660, 600)
                        text_items = self.vision.scan_screen_for_text_events(screen, roi=chest_roi)
                        found_by_ocr = any(kw in item['text'] for item in text_items for kw in ["强效", "Greater", "Chest", "Spoils"])

                        if res or found_by_ocr:
                            # 🎯 关键改进：记录当前的鼠标位置，并按照要求向上微调 65 像素
                            calculated_y = current_mouse_pos[1] - 65
                            # 验证坐标有效性，防止移动到屏幕外
                            if calculated_y < 0:
                                calculated_y = max(0, current_mouse_pos[1] - 30)  # 如果减去65会变成负数，只减去30
                            trigger_pos = (current_mouse_pos[0], calculated_y)
                            # 再次验证坐标范围
                            trigger_pos = (max(0, min(2560, trigger_pos[0])), max(0, min(1440, trigger_pos[1])))
                            self.log_status(self.get_text("interaction_detected", trigger_pos))
                            break

                    if trigger_pos:
                        self.log_status(self.get_text("executing_open"))
                        
                        # 📸 调试：在点击前截屏并标注位置
                        screen_debug = self.vision.capture_screen()
                        # 画一个红色的十字准星在 trigger_pos
                        tx, ty = int(trigger_pos[0]), int(trigger_pos[1])
                        cv2.drawMarker(screen_debug, (tx, ty), (0, 0, 255), cv2.MARKER_CROSS, 50, 2)
                        # 画标尺
                        for i in range(0, 2560, 100):
                            cv2.line(screen_debug, (i, 0), (i, 20), (0, 255, 0), 1)
                            cv2.putText(screen_debug, str(i), (i, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
                        for i in range(0, 1440, 100):
                            cv2.line(screen_debug, (0, i), (20, i), (0, 255, 0), 1)
                            cv2.putText(screen_debug, str(i), (25, i+5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
                        self.vision.save_debug_image(screen_debug, "debug_chest_click_target.png")
                        self.log_status(self.get_text("debug_saved", "logs/debug_chest_click_target.png", trigger_pos))

                        # 1. 交互开启逻辑 (使用 F 键代替长按左键，防止攻击干扰)
                        pyautogui.moveTo(trigger_pos[0], trigger_pos[1], duration=0.2)
                        time.sleep(0.2)
                        kb.press_and_release('f')
                        self.log_status(self.get_text("pressed_f"))
                        time.sleep(1.5) # 等待开启完成
                        
                        # 2. 使用OpenCV模板匹配识别恢复卷轴并用鼠标左键点击拾取
                        self.log_status(self.get_text("precise_pickup_scan"))
                        
                        # 定义扫描范围：宽度±250像素，高度1380px（长条长方形）
                        scan_radius = 250  # 横向半径
                        scan_height = 1380  # 纵向高度（几乎全屏）
                        chest_x, chest_y = trigger_pos
                        # 形成长条长方形：以chest_x为中心±250px宽度，从顶部开始1380px高度
                        scan_roi = (
                            max(0, chest_x - scan_radius),           # x1: 左侧边界
                            0,                                        # y1: 从屏幕顶部开始
                            min(2560, chest_x + scan_radius),        # x2: 右侧边界
                            min(1440, scan_height)                    # y2: 高度1380px（接近全屏）
                        )
                        
                        # 📸 生成调试截图：框住扫描范围并标注坐标
                        screen_debug = self.vision.capture_screen()
                        roi_x1, roi_y1, roi_x2, roi_y2 = scan_roi
                        # 绘制扫描范围矩形框（绿色）
                        cv2.rectangle(screen_debug, (roi_x1, roi_y1), (roi_x2, roi_y2), (0, 255, 0), 3)
                        # 标注坐标信息
                        cv2.putText(screen_debug, f"Scan ROI: ({roi_x1}, {roi_y1}) to ({roi_x2}, {roi_y2})", 
                                   (roi_x1, roi_y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                        cv2.putText(screen_debug, f"Chest Click: ({chest_x}, {chest_y})", 
                                   (chest_x - 100, chest_y - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                        # 在宝箱点击位置画十字
                        cv2.drawMarker(screen_debug, (chest_x, chest_y), (0, 0, 255), cv2.MARKER_CROSS, 30, 3)
                        # 标注扫描范围信息
                        cv2.putText(screen_debug, f"Width: {scan_radius*2}px, Height: {scan_height}px", 
                                   (roi_x1, roi_y2 + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                        self.vision.save_debug_image(screen_debug, "debug_loot_scan_roi.png")
                        self.log_status(f"📸 扫描范围截图已保存: logs/debug_loot_scan_roi.png, ROI: {scan_roi}")
                        
                        # 拾取循环，最多30秒
                        start_loot_time = time.time()
                        max_loot_duration = 30.0
                        last_scan_time = 0
                        last_alt_time = 0
                        scan_interval = 0.5  # 每0.5秒扫描一次
                        alt_interval = 0.3   # 每0.3秒按一次Alt显示物品名称
                        
                        self.log_status("👀 开始拾取，不间断按Alt显示物品名称...")
                        
                        while time.time() - start_loot_time < max_loot_duration:
                            current_time = time.time()
                            
                            # 不间断按Alt显示物品名称
                            if current_time - last_alt_time >= alt_interval:
                                kb.press_and_release('alt')
                                last_alt_time = current_time
                            
                            # 控制扫描频率
                            if current_time - last_scan_time < scan_interval:
                                time.sleep(0.05)
                                continue
                            
                            last_scan_time = current_time
                            screen = self.vision.capture_screen()
                            found_item = False
                            
                            # 优先拾取列表：恢复卷轴和太古标签装备
                            priority_items = [
                                ("tip_huifu", "恢复卷轴", 0.7),
                                ("icon_taigu_tag", "太古标签装备", 0.7)
                            ]
                            
                            # 在扫描范围内查找优先物品
                            for tmpl_name, desc, thresh in priority_items:
                                res = self.vision.find_template_in_region(screen, tmpl_name, scan_roi, threshold=thresh)
                                if res:
                                    item_x, item_y, confidence = res
                                    # 验证坐标是否在扫描范围内
                                    if roi_x1 <= item_x <= roi_x2 and roi_y1 <= item_y <= roi_y2:
                                        self.log_status(f"✨ 发现{desc}! 点击拾取: ({item_x}, {item_y}), 置信度: {confidence:.2f}")
                                        # 使用鼠标左键点击装备位置
                                        self.nav.click_position((item_x, item_y))
                                        time.sleep(0.2)  # 等待拾取完成
                                        found_item = True
                                        break  # 捡完一个重新扫描，以免位置变动
                            
                            if not found_item:
                                time.sleep(0.05)
                        
                        self.log_status("✅ 装备拾取完成（30秒时间到）")
                        
                        # 3. 流程结束
                        self.log_status(self.get_text("pickup_finished"))
                        kb.press_and_release('t')
                        # 增加缓冲时间
                        time.sleep(8.0) 
                        self.state = GameState.ACTIVATING_NEXT_COMPASS
                    else:
                        self.log_status(self.get_text("no_interaction_retry"))
                        time.sleep(1)

                elif self.state == GameState.ACTIVATING_NEXT_COMPASS:
                    self.log_status(self.get_text("activating_next_compass"))
                    kb.press_and_release('i')
                    time.sleep(1.5) # 增加等待背包打开的时间
                    
                    screen = self.vision.capture_screen()
                    # 使用模板匹配寻找钥匙栏
                    key_tab = self.vision.find_template_in_region(screen, "chest_icon", INVENTORY_REGION, threshold=0.7)
                    if not key_tab:
                        key_tab = self.vision.find_template_in_region(screen, "backpack_key", INVENTORY_REGION, threshold=0.6)

                    if key_tab:
                        self.log_status(self.get_text("key_tab_found", key_tab[:2], key_tab[2]))
                        self.nav.click_position(key_tab[:2])
                        time.sleep(1.0)
                        
                        screen = self.vision.capture_screen()
                        compass = self.vision.find_template_in_region(screen, "compass", INVENTORY_REGION, threshold=0.7)
                        if compass:
                            self.log_status(self.get_text("compass_found", compass[:2], compass[2]))
                            pyautogui.rightClick(compass[0], compass[1])
                            time.sleep(1.5)
                            if self.handle_modal_accept("modal_usekey"):
                                # self.log_status handled inside handle_modal_accept
                                time.sleep(1.0)
                                kb.press_and_release('i')
                                time.sleep(1.0)
                                self.state = GameState.TELEPORTING_TO_INSTANCE
                            else:
                                self.log_status(self.get_text("modal_failed"))
                                # 保存弹窗调试图像
                                self.vision.save_debug_image(screen, "debug_modal_failed.png")
                        else:
                            self.log_status(self.get_text("compass_missing"))
                            roi_x1, roi_y1, roi_x2, roi_y2 = INVENTORY_REGION
                            debug_crop = screen[roi_y1:roi_y2, roi_x1:roi_x2]
                            self.vision.save_debug_image(debug_crop, "debug_compass_not_found.png")
                    else:
                        # 备选方案：尝试 OCR 钥匙栏文本
                        self.log_status(self.get_text("ocr_key_retry"))
                        text_items = self.vision.scan_screen_for_text_events(screen, roi=INVENTORY_REGION)
                        key_text = None
                        for item in text_items:
                            if any(kw in item['text'] for kw in ["钥", "钥匙", "Key", "KEY"]):
                                key_text = item
                                break

                        if key_text:
                            self.log_status(self.get_text("key_text_found", key_text['text'], key_text['center']))
                            self.nav.click_position(key_text['center'])
                            time.sleep(1.0)
                        else:
                            self.log_status(self.get_text("key_tab_missing"))
                            roi_x1, roi_y1, roi_x2, roi_y2 = INVENTORY_REGION
                            debug_crop = screen[roi_y1:roi_y2, roi_x1:roi_x2]
                            self.vision.save_debug_image(debug_crop, "debug_inventory_keytab.png")
                            # 同时保存全屏以检查背包是否已打开
                            self.vision.save_debug_image(screen, "debug_full_screen_inventory.png")

                elif self.state == GameState.TELEPORTING_TO_INSTANCE:
                    kb.press_and_release('tab')
                    time.sleep(1.5)
                    screen = self.vision.capture_screen()
                    door_icon = self.vision.find_template(screen, "compass_door", threshold=0.7)
                    if door_icon:
                        self.nav.click_position(door_icon[:2])
                        time.sleep(1.0)
                        if self.handle_modal_accept("modal_tp"):
                            self.log_status(self.get_text("teleporting"))
                            time.sleep(8.0)
                            self.compass_count += 1
                            self.current_wave = 0
                            self.state = GameState.ENTERING_INSTANCE
                    else:
                        self.log_status(self.get_text("no_instance_icon"))

                elif self.state == GameState.ENTERING_INSTANCE:
                    self.log_status(self.get_text("entering_instance"))
                    success = self.execute_return_to_center(template_name="start_icon", tolerance=10)
                    if success:
                        self.log_status(self.get_text("arrived_start_pos"))
                        start_check = time.time()
                        while time.time() - start_check < 15.0: # 等待时间缩短至 15 秒
                            minimap = self.vision.capture_minimap()
                            if self.vision.find_template(minimap, "bonehand", threshold=0.6) or \
                               self.vision.find_template(minimap, "extrahand", threshold=0.6):
                                self.log_status(self.get_text("detected_event_icon"))
                                self.state = GameState.NAVIGATING_TO_CENTER
                                break
                            time.sleep(1.0)
                        
                        if self.state != GameState.NAVIGATING_TO_CENTER:
                            self.log_status(self.get_text("wait_icon_timeout"))
                            self.state = GameState.NAVIGATING_TO_CENTER
                    else:
                        self.log_status(self.get_text("blind_move_up"))
                        self.nav.move_while_casting("up", 3.0)
                # 盲移后，尝试直接寻找 bonehand/extrahand
                        minimap = self.vision.capture_minimap()
                        if self.vision.find_template(minimap, "bonehand", threshold=0.5) or \
                           self.vision.find_template(minimap, "extrahand", threshold=0.5):
                            self.state = GameState.NAVIGATING_TO_CENTER

                elif self.state == GameState.IDLE:
                    time.sleep(1)

            except KeyboardInterrupt:
                print(self.get_text("stopped_by_user"))
                break
            except Exception as e:
                print(self.get_text("error_occurred", e))
                import traceback
                traceback.print_exc()
                break

    def handle_modal_accept(self, template_name, timeout=3.0):
        """扫描弹窗并点击 '接受' 按钮。"""
        start_time = time.time()
        modal_roi = (400, 600, 2160, 1200) 
        while time.time() - start_time < timeout:
            screen = self.vision.capture_screen()
            modal = self.vision.find_template(screen, template_name, threshold=0.8)
            if modal:
                text_items = self.vision.scan_screen_for_text_events(screen, roi=modal_roi)
                for item in text_items:
                    if any(kw in item['text'] for kw in ["接受", "Accept"]):
                        self.log_status(self.get_text("modal_accepted", item['text']))
                        self.nav.click_position(item['center'])
                        return True
            time.sleep(0.3)
        return False

    def execute_return_to_center(self, template_name="bonehand", verbose=False, tolerance=None):
        """通过跟随模板图标导航到中心。到达时返回 True。"""
        from config import CHEST_TOLERANCE
        if tolerance is None:
            if template_name == "bossdoor":
                tolerance = BOSS_DOOR_TOLERANCE
            elif template_name == "chest_marker":
                tolerance = CHEST_TOLERANCE
            else:
                tolerance = CENTER_TOLERANCE
        
        target_dx, target_dy = 0, 0
        if template_name == "chest_marker":
            target_dx, target_dy = 12.0, 111.0  # 校准：在宝箱处时血井图标相对于中心的位置
        elif template_name == "bossdoor":
            target_dx, target_dy = -3.0, -6.0  # 目标位置：图标相对于玩家中心的位置

        for step in range(1, MAX_STEPS + 1):
            minimap = self.vision.capture_minimap()
            icon_rel_x, icon_rel_y = None, None
            
            if template_name == "chest_marker":
                haystack_gray = cv2.cvtColor(minimap, cv2.COLOR_BGR2GRAY)
                template = self.vision.templates.get("chest_marker")
                if template is None: return False
                th, tw = template.shape[:2]
                x1, y1, _, _ = MINIMAP_REGION
                res = cv2.matchTemplate(haystack_gray, template, cv2.TM_CCOEFF_NORMED)
                loc = np.where(res >= MATCH_THRESHOLD)
                points = list(zip(*loc[::-1]))
                if not points:
                    # 备选方案：如果未找到血井，也许尝试宝箱图标作为备份？
                    # 目前仅等待并重试。
                    time.sleep(0.2)
                    continue
                
                # 如果有多个，使用最接近校准相对位置的心形图标
                best_pt = points[0] 
                # 如果有多个，寻找最接近我们预期 target_dx, target_dy 的那个
                if len(points) > 1:
                    def dist_to_target(p):
                        curr_dx = (x1 + p[0] + tw//2) - PLAYER_POS[0]
                        curr_dy = (y1 + p[1] + th//2) - PLAYER_POS[1]
                        return abs(curr_dx - target_dx) + abs(curr_dy - target_dy)
                    best_pt = min(points, key=dist_to_target)

                icon_rel_x = best_pt[0] + tw // 2
                icon_rel_y = best_pt[1] + th // 2
            else:
                # 优先尝试识别 extrahand (混沌事件)
                result = self.vision.find_template(minimap, "extrahand", threshold=MATCH_THRESHOLD)
                current_used_template = "extrahand"
                
                if not result:
                    # 如果没有 extrahand，再尝试 bonehand
                    result = self.vision.find_template(minimap, "bonehand", threshold=MATCH_THRESHOLD)
                    current_used_template = "bonehand"
                
                if not result:
                    # 如果是其他特定的模板（如 bossdoor），则尝试它
                    if template_name not in ["bonehand", "extrahand"]:
                        result = self.vision.find_template(minimap, template_name, threshold=MATCH_THRESHOLD)
                        current_used_template = template_name
                
                if not result:
                    if template_name == "bossdoor":
                        merge_result = self.vision.find_template(minimap, "bossdoor_merge", threshold=MATCH_THRESHOLD)
                        if merge_result:
                            mx, my, _ = merge_result
                            x1, y1, _, _ = MINIMAP_REGION
                            mdx = (x1 + mx) - PLAYER_POS[0]
                            mdy = (y1 + my) - PLAYER_POS[1]
                            if abs(mdx) <= tolerance and abs(mdy) <= tolerance:
                                return True
                    time.sleep(0.2)
                    continue
                
                icon_rel_x, icon_rel_y, _ = result
                template_name = current_used_template # 更新显示的模板名称以便日志准确

            if icon_rel_x is not None:
                x1, y1, _, _ = MINIMAP_REGION
                abs_icon_x = x1 + icon_rel_x
                abs_icon_y = y1 + icon_rel_y
                
                # 计算当前图标相对于玩家中心的偏移 (raw_dx, raw_dy)
                raw_dx = abs_icon_x - PLAYER_POS[0]
                raw_dy = abs_icon_y - PLAYER_POS[1]
                
                # 误差 = 当前偏移 - 理想偏移
                error_x = raw_dx - target_dx
                error_y = raw_dy - target_dy

                if step % 10 == 1:
                    self.log_status(self.get_text("nav_log", f"{template_name} | Raw: {raw_dx:.1f}, {raw_dy:.1f} | Error: {error_x:.1f}, {error_y:.1f}"))

                # 只有当误差在容差范围内时，才认为到达
                if abs(error_x) <= tolerance and abs(error_y) <= tolerance:
                    self.log_status(self.get_text("nav_log", f"Reached {template_name}! (Final Error: {error_x:.1f}, {error_y:.1f})"))
                    return True

                if abs(error_x) > tolerance:
                    self.nav.move("right" if error_x > 0 else "left", self.nav.calculate_duration(abs(error_x)))
                if abs(error_y) > tolerance:
                    self.nav.move("down" if error_y > 0 else "up", self.nav.calculate_duration(abs(error_y)))
                time.sleep(0.2) 
        return False

    def fuzzy_match_event(self, ocr_text):
        if not ocr_text: return None
        clean_text = ocr_text.replace(" ", "").replace(".", "").replace("'", "").lower()
        # 优先匹配混沌
        if any(kw.lower() in clean_text for kw in ["混沌", "Hellborne", "Offerings"]):
            return self.get_text("hellborne_event_name")
        for event in self.desired_events:
            clean_event = event.replace(" ", "").lower()
            if clean_event in clean_text: return event
            if len(clean_event) >= 4:
                if clean_event[:2] in clean_text and clean_event[-1] in clean_text: return event
        return None

    def select_best_event(self, found_events):
        if not found_events: return None
        def get_priority(event_obj):
            name = event_obj['name']
            if name in self.desired_events: return self.desired_events.index(name)
            return 999
        found_events.sort(key=get_priority)
        return found_events[0]

    def log_door_opened(self):
        """Log door opening event to file."""
        log_file = LOGS_DIR / "door_openings.log"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = self.get_text("door_log_msg")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {msg}\n")
        print(f"Logged to: {log_file}")

if __name__ == "__main__":
    bot = CompassBot()
    bot.run()
