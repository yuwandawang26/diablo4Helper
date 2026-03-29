import time
import cv2
import json
import numpy as np
import pyautogui
from datetime import datetime
from pathlib import Path
from config import (
    ASSETS_DIR, PLAYER_POS, MINIMAP_REGION, MATCH_THRESHOLD,
    CENTER_TOLERANCE, BOSS_DOOR_TOLERANCE, CHEST_TOLERANCE, MAX_STEPS,
    DESIRED_EVENTS_CN, DESIRED_EVENTS_EN, LOGS_DIR, INVENTORY_REGION,
    EVENT_SCAN_ROI, TRANSLATIONS_PATH, NAV_CENTER_DX, NAV_CENTER_DY,
    INSTANCE_HUD_REGION, DEATH_SCAN_REGION, MODAL_SCAN_REGION,
    EQUIP_CHEST_NAV_DX, EQUIP_CHEST_NAV_DY, EQUIP_CHEST_SCAN_REGION,
    MATERIAL_CHEST_NAV_DX, MATERIAL_CHEST_NAV_DY, MATERIAL_CHEST_SCAN_REGION,
    GOLD_CHEST_NAV_DX, GOLD_CHEST_NAV_DY, GOLD_CHEST_SCAN_REGION,
)
from core.vision import VisionSystem
from core.navigation import NavigationSystem
from core.enums import GameState
from core.settings_manager import (
    load_settings, pick_tribute,
    CHEST_TEMPLATE_NAMES, CHEST_OPEN_ORDER,
    CHEST_TYPE_KEYWORDS, CHEST_LABEL_CN, identify_chest_type,
)
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
        # UI integration hooks
        self._running = True
        self._log_callback = None    # callable(str) - receives formatted log lines
        self._state_callback = None  # callable(state, compass, wave_curr, wave_max, ether)
        self._quest_callback = None  # callable(str) - receives current quest-tracker text
        self._last_ether = None
        self._last_quest_text = ""   # last emitted quest text (suppress duplicate updates)
        self._compass_keys = ["compass"]
        self._last_death_check = 0.0   # throttle death checks
        self._last_quest_refresh = 0.0 # throttle periodic quest-tracker refresh
        # ── Chest queue (multi-chest run) ─────────────────────────────────────
        self._chest_queue: list[str] = []   # ordered chest types yet to open
        self._chest_attempts: int = 0       # attempts at current chest
        self._MAX_CHEST_ATTEMPTS: int = 5
        self._chest_at_base: bool = False   # True once we've reached the base point
        # ── Run counter ───────────────────────────────────────────────────────
        self.run_count: int = 0             # completed runs this session
        self.max_runs: int = 0              # 0 = unlimited; set at start of run()
        self._run_count_callback = None     # callable(current, max) → UI update
        # Wire navigation stop-check
        self.nav.running_check = lambda: self._running
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

    # Map: logical template key -> primary filename stem (used for variant glob scanning)
    _TEMPLATE_REGISTRY = [
        ("bonehand",      "minimap_bonehand"),
        ("extrahand",     "minimap_extrahand"),
        ("bosshand",      "minimap_bosshand"),
        ("bossdoor",      "icon_bossdoor"),
        ("bossdoor_merge","icon_bossdoor_merge"),
        ("chest_marker",  "icon_health"),
        ("tip_bosschest", "tip_bosschest"),
        ("chest_icon",    "icon_key"),
        ("backpack_key",  "backpack_key"),
        ("compass",       "icon_compass"),   # kept as "compass" key for agent logic
        ("compass_door",  "icon_compassdoor"),
        ("modal_usekey",  "modal_usekey"),
        ("modal_tp",      "modal_tp_compass"),
        ("start_icon",    "icon_start"),
        ("tip_huifu",     "tip_huifu"),
        ("icon_taigu_tag","icon_taigu_tag"),
        ("hundun_event",  "hundun_event"),
        ("modal_death",   "modal_death"),
        ("hud_instance",  "hud_instance"),  # compass instance HUD icon (top-right wave box)
    ]

    def load_assets(self):
        """Load all templates with multi-variant support.

        For each template key, the primary file is loaded first, followed by
        any variants named  <stem>_v2.png, <stem>_v3.png, etc.
        All variants are stored as a list in VisionSystem.templates[key] so
        find_template automatically tries every variant and returns the best match.
        """
        for key, stem in self._TEMPLATE_REGISTRY:
            # 1. Load the canonical file (e.g. icon_compass.png)
            self.vision.load_template(key, ASSETS_DIR / f"{stem}.png")
            # 2. Load any additional variant files (icon_compass_v2.png, icon_compass_v3.png …)
            for variant in sorted(ASSETS_DIR.glob(f"{stem}_v*.png")):
                self.vision.load_template(key, variant)

        # Print how many variants were loaded for multi-variant templates
        for key, _stem in self._TEMPLATE_REGISTRY:
            n = self.vision.variant_count(key)
            if n > 1:
                print(f"[资源] {key}: {n} 个变种模板已加载")

        # Compass special: keep backward-compatible _compass_keys for any future use
        self._compass_keys = ["compass"]

    def check_and_handle_death(self) -> bool:
        """Detect the death screen and click the resurrection button.

        Detection priority:
          1. Template match against assets/modal_death.png (fast, no OCR).
             The template should contain the full-screen death overlay including
             the resurrection button.  Multiple variants (_v2.png …) are supported.
          2. OCR scan of the lower-centre screen band for resurrection keywords.
             Used when no death template has been uploaded.

        Returns True if death was detected and resurrection was triggered.
        Throttled to at most once every 4 seconds.
        """
        now = time.time()
        if now - self._last_death_check < 4.0:
            return False
        self._last_death_check = now

        try:
            screen = self.vision.capture_screen()
            h, w = screen.shape[:2]

            # ── Method 1: template match (fast) ──────────────────────────────
            if self.vision.variant_count("modal_death") > 0:
                result = self.vision.find_template(screen, "modal_death", threshold=0.55)
                if result:
                    cx, cy, conf = result
                    self.log_status(f"💀 死亡模板匹配！(conf={conf:.2f}) 点击: ({cx},{cy})")
                    self._do_resurrect((cx, cy))
                    return True

            # ── Method 2: OCR fallback ────────────────────────────────────────
            from config import DEATH_SCAN_REGION
            text_items = self.vision.scan_screen_for_text_events(screen, roi=DEATH_SCAN_REGION)
            for item in text_items:
                t = item["text"]
                if any(kw in t for kw in [
                    "在存档点重生", "存档点重生", "重生",
                    "Resurrect", "checkpoint", "Checkpoint",
                ]):
                    self.log_status(f"💀 OCR 检测到死亡！点击复活: {item['center']}")
                    self._do_resurrect(item["center"])
                    return True

        except Exception as e:
            print(f"[death check error] {e}")
        return False

    def _do_resurrect(self, click_pos: tuple):
        """Click the resurrection button and wait for respawn."""
        self.state = GameState.DEAD
        self.nav.click_position(click_pos)
        time.sleep(6.0)
        self.log_status("✅ 已复活，重新导航至中心")
        self.state = GameState.NAVIGATING_TO_CENTER
        self._last_death_check = time.time()

    # ── Quest-tracker helpers ─────────────────────────────────────────────────

    def _emit_run_count(self):
        """Push run-count update to the overlay via callback."""
        if self._run_count_callback:
            self._run_count_callback(self.run_count, self.max_runs)

    def _emit_quest(self, text: str):
        """Emit quest text to overlay if changed; always print when non-empty."""
        if text != self._last_quest_text:
            self._last_quest_text = text
            print(f"[QUEST-CHANGE] {text!r}")
            if self._quest_callback and text:
                self._quest_callback(text)
        elif text and self._quest_callback:
            # Still emit periodically so overlay stays populated after reconnect
            self._quest_callback(text)

    # ── Behaviour-tree priority monitor ──────────────────────────────────────────
    def _priority_tick(self, interrupt: dict) -> bool:
        """BT Root Selector — checks high-priority conditions in order.

        Does ONE quest-tracker OCR scan per call and fans the result to all
        three checks so there is only one screenshot+OCR per tick.

        Parameters
        ----------
        interrupt : dict
            Shared mutable dict updated with the reason when True is returned.
            Keys: ``reason`` → one of ``'dead'``, ``'offering'``, ``'combat'``.

        Returns True if an interrupt was triggered and the caller should stop
        its current blocking operation.
        """
        # P1 ── Death (handles click + wait + state change internally)
        if self.check_and_handle_death():
            interrupt['reason'] = 'dead'
            return True

        # Single OCR scan for P2/P3
        quest_text = self.vision.read_quest_tracker()
        self._emit_quest(quest_text)

        # P2 ── Horde complete — detectable from any non-boss state.
        # "已击败炼狱魔潮" means the final offering was chosen; go to boss room.
        _horde_states = (
            GameState.COMBAT, GameState.NAVIGATING_TO_CENTER,
            GameState.SCANNING_FOR_EVENTS, GameState.SELECTING_EVENT,
            GameState.WAITING_FOR_WAVE_START,
        )
        if self.state in _horde_states and self.vision.check_horde_complete(quest_text):
            if not getattr(self, "_bt_last_reason", None) == "horde_complete":
                self._bt_last_reason = "horde_complete"
                self.log_status("[BT-P2] 「已击败炼狱魔潮」→ 最终供奉完成，前往 Boss 房")
            interrupt['reason'] = 'horde_complete'
            return True

        # P3 ── Offering-selection phase — only meaningful while in COMBAT.
        # Once we leave combat (navigating / scanning / etc.) this signal has
        # already served its purpose; re-firing it would cause state ping-pong.
        if self.state == GameState.COMBAT and self.vision.check_offering_selection(quest_text):
            if not getattr(self, "_bt_last_reason", None) == "offering":
                self._bt_last_reason = "offering"
                self.log_status("[BT-P3] 「选择炼狱供奉」→ 战斗结束，前往中心")
            interrupt['reason'] = 'offering'
            return True

        # P4 ── Combat re-triggered from any non-combat state (teammate picked
        # an offering and a new wave started while we were navigating / scanning).
        if self.state != GameState.COMBAT and self.vision.check_combat_quest(quest_text):
            if not getattr(self, "_bt_last_reason", None) == "combat":
                self._bt_last_reason = "combat"
                self.log_status("[BT-P4] 战斗任务「消灭怪物」→ 进入战斗")
            interrupt['reason'] = 'combat'
            return True

        self._bt_last_reason = None

        return False

    def log_status(self, message):
        """标准化日志格式，包含罗盘、波次和以太信息。"""
        ether_count = self.vision.read_ether_count()
        self._last_ether = ether_count
        ether_str = f"[E:{ether_count}]" if ether_count is not None else "[E:?]"
        line = f"[C{self.compass_count}][W{self.current_wave}/{self.max_waves}]{ether_str} {message}"
        print(line)
        if self._log_callback:
            self._log_callback(line)
        if self._state_callback:
            try:
                self._state_callback(
                    self.state.name, self.compass_count,
                    self.current_wave, self.max_waves, ether_count
                )
            except Exception:
                pass

    # ── Instance detection ────────────────────────────────────────────────────

    def is_in_compass_instance(self) -> bool:
        """Detect whether the player is currently inside a compass instance.

        Detection priority:
          1. Template match for ``hud_instance.png`` inside INSTANCE_HUD_REGION
             (fast, reliable — user must upload a screenshot of the wave-counter
             icon box visible in the top-right corner).
          2. OCR wave-counter read — if the wave counter is legible we are inside.
          3. Minimap event-icon check — if bonehand/extrahand is visible we are
             inside (slower, but works without any uploaded templates).

        Returns True if any method confirms we are inside an instance.
        """
        from config import INSTANCE_HUD_REGION

        # ── Method 1: template match (fast, no OCR) ──────────────────────────
        if self.vision.variant_count("hud_instance") > 0:
            try:
                screen = self.vision.capture_screen()
                x1, y1, x2, y2 = INSTANCE_HUD_REGION
                hud_crop = screen[y1:y2, x1:x2]
                result = self.vision.find_template(hud_crop, "hud_instance", threshold=0.50)
                if result:
                    _, _, conf = result
                    self.log_status(f"[启动检测] HUD 模板匹配到副本图标 (conf={conf:.2f})")
                    return True
            except Exception as e:
                print(f"[hud_instance check error] {e}")

        # ── Method 2: OCR wave number ─────────────────────────────────────────
        wave_data = self.vision.read_wave_number()
        if isinstance(wave_data, tuple):
            self.log_status(f"[启动检测] OCR 读到波次 {wave_data} → 已在副本")
            return True
        if isinstance(wave_data, str) and any(kw in wave_data for kw in ["波", "Wave", "/"]):
            self.log_status(f"[启动检测] OCR 读到波次文本 '{wave_data}' → 已在副本")
            return True

        # ── Method 3: minimap event icon ─────────────────────────────────────
        try:
            minimap = self.vision.capture_minimap()
            if (self.vision.find_template(minimap, "extrahand", threshold=MATCH_THRESHOLD) or
                    self.vision.find_template(minimap, "bonehand", threshold=MATCH_THRESHOLD)):
                self.log_status("[启动检测] 小地图发现事件图标 → 已在副本")
                return True
        except Exception as e:
            print(f"[minimap hud check error] {e}")

        return False

    def _sync_state_inside_instance(self, minimap):
        """Choose the correct starting state when we know we are already
        inside a compass instance.  Called once during run() startup.

        Decision tree:
          1. Read wave count first (updates self.current_wave / max_waves)
          2. Boss room / chest are only reachable after ALL waves complete →
             only check minimap for bosshand/bossdoor/chest when waves_done
          3. During active waves: scan for event choices or fall back to
             navigating to the combat centre
          4. Wave == 0 or unreadable → just entered, navigate to centre
        """
        # ── Step 1: read wave count first so the overlay shows the right value ──
        wave_data = self.vision.read_wave_number()
        curr_wave, max_wave = 0, 10
        if isinstance(wave_data, tuple):
            curr_wave, max_wave = wave_data
            self.current_wave = curr_wave
            self.max_waves = max_wave
            self.log_status(f"[启动检测] OCR 读波次: {curr_wave}/{max_wave}")

        waves_done = (curr_wave > 0 and curr_wave >= max_wave)

        # ── Step 2: boss/chest only exist after all waves are complete ───────────
        if waves_done:
            if (self.vision.find_template(minimap, "bosshand", threshold=0.55) or
                    self.vision.find_template(minimap, "bossdoor", threshold=0.55)):
                self.log_status(self.get_text("sync_boss"))
                return GameState.NAVIGATING_TO_BOSS
            if self.vision.find_template(minimap, "chest_marker", threshold=0.55):
                self.log_status(self.get_text("sync_chest"))
                return GameState.NAVIGATING_TO_CHEST
            # waves done but no boss/chest icon yet → keep navigating to centre
            self.log_status("[启动检测] 波次已结束，等待首领房刷出...")
            return GameState.NAVIGATING_TO_CENTER

        # ── Step 3: active waves ──────────────────────────────────────────────────
        if curr_wave > 0:
            screen = self.vision.capture_screen()
            text_items = self.vision.scan_screen_for_text_events(screen, roi=EVENT_SCAN_ROI)
            found_any_event = any(self.fuzzy_match_event(it["text"]) for it in text_items)
            if found_any_event:
                self.log_status(self.get_text("sync_events"))
                return GameState.SCANNING_FOR_EVENTS
            self.log_status(self.get_text("sync_wave"))
            return GameState.NAVIGATING_TO_CENTER

        # ── Step 4: wave == 0 or unreadable ──────────────────────────────────────
        self.log_status("[启动检测] 波次为 0 或未读到 → 副本刚进入，导航至中心")
        return GameState.ENTERING_INSTANCE

    def run(self):
        """主状态机循环 - 恢复全自动化"""
        self._running = True
        # Read run limit from settings at startup
        _s = load_settings()
        self.max_runs = int(_s.get("max_runs", 0))
        self.run_count = 0
        self._emit_run_count()
        self.log_status(
            f"[RUN] 最大运行次数: {'不限' if self.max_runs == 0 else self.max_runs}"
        )
        print(self.get_text("start_prompt"))
        time.sleep(3)

        # ── Startup state sync ────────────────────────────────────────────────
        # Primary check: are we already inside a compass instance?
        # If yes → skip the whole inventory/key activation flow.
        minimap = self.vision.capture_minimap()

        if self.is_in_compass_instance():
            self.state = self._sync_state_inside_instance(minimap)
        elif self.vision.find_template(minimap, "bosshand") or self.vision.find_template(minimap, "bossdoor"):
            # Edge case: HUD not detected but minimap shows boss area
            self.log_status(self.get_text("sync_boss"))
            self.state = GameState.NAVIGATING_TO_BOSS
        elif self.vision.find_template(minimap, "chest_marker"):
            self.log_status(self.get_text("sync_chest"))
            self.state = GameState.NAVIGATING_TO_CHEST
        else:
            self.log_status(self.get_text("sync_town"))
            self.state = GameState.ACTIVATING_NEXT_COMPASS

        self.current_wave = 0 if self.current_wave == 0 else self.current_wave
        if self.max_waves == 0:
            self.max_waves = 10

        while self._running:
            try:
                # Emit state to UI
                if self._state_callback:
                    try:
                        self._state_callback(
                            self.state.name, self.compass_count,
                            self.current_wave, self.max_waves, self._last_ether
                        )
                    except Exception:
                        pass

                # ── Periodic quest-tracker refresh for overlay (every 5 s) ──
                now = time.time()
                if now - self._last_quest_refresh >= 5.0:
                    self._last_quest_refresh = now
                    qt = self.vision.read_quest_tracker()
                    self._emit_quest(qt)

                # ── Death check (active states only, throttled) ──────────────
                if self.state not in (
                    GameState.IDLE, GameState.FINISHED, GameState.DEAD,
                    GameState.RETURNING_TO_TOWN,
                    GameState.ACTIVATING_NEXT_COMPASS, GameState.TELEPORTING_TO_INSTANCE,
                ):
                    if self.check_and_handle_death():
                        continue

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
                    self.nav.move_mouse_to_center()
                    _nav_interrupt = {'reason': None}
                    _nav_tick = lambda: self._priority_tick(_nav_interrupt)
                    # No skills while navigating to center (offering phase, no mobs)
                    success = self.execute_return_to_center(
                        template_name="bonehand",
                        interrupt_check=_nav_tick,
                        cast_while_moving=False,
                    )
                    self._nav_to_center_reason = None
                    if success:
                        self.log_status(self.get_text("reached_center"))
                        self.state = GameState.SCANNING_FOR_EVENTS
                    else:
                        _r = _nav_interrupt['reason']
                        if _r == 'dead':
                            pass  # _do_resurrect set state
                        elif _r == 'horde_complete':
                            self.state = GameState.NAVIGATING_TO_BOSS
                        elif _r == 'combat':
                            self.state = GameState.COMBAT
                        else:
                            # Nav timed out — proceed to scan anyway (player may
                            # be close enough to interact with the altar)
                            self.log_status("[NAV] 导航超时，尝试直接扫描")
                            self.state = GameState.SCANNING_FOR_EVENTS

                elif self.state == GameState.SCANNING_FOR_EVENTS:
                    # BT check: a teammate may have selected offering already,
                    # triggering a new combat wave while we are still scanning.
                    # 'offering' will NOT fire here (see _priority_tick) — only
                    # 'dead' and 'combat' are relevant from this state.
                    _scan_interrupt = {'reason': None}
                    if self._priority_tick(_scan_interrupt):
                        _r = _scan_interrupt['reason']
                        if _r == 'dead':
                            pass
                        elif _r == 'horde_complete':
                            self.log_status("[SCAN] 魔潮已完成 → NAVIGATING_TO_BOSS")
                            self.state = GameState.NAVIGATING_TO_BOSS
                        elif _r == 'combat':
                            self.state = GameState.COMBAT
                        continue
                    self.nav.move_mouse_to_center()
                    time.sleep(0.5)
                    screen = self.vision.capture_screen()

                    # ── Pass 1: tribute icon template matching (fast, reliable) ─
                    icon_events = self.vision.scan_tribute_icons(
                        screen, roi=EVENT_SCAN_ROI, threshold=0.60
                    )
                    if icon_events:
                        self.log_status(
                            f"[贡品] 图标扫描找到 {len(icon_events)} 个贡品: "
                            f"{[e['category'] for e in icon_events]}"
                        )
                        best_choice = self.select_best_event(icon_events)
                        self.log_status(
                            f"[贡品] 选择: {best_choice['name']}  "
                            f"pos={best_choice['center']}"
                        )
                        self.selected_event_target = best_choice
                        self.state = GameState.SELECTING_EVENT
                        continue

                    # ── Pass 2: OCR fallback ──────────────────────────────────
                    # Legacy hundun template check first (fast single-template)
                    hundun_result = self.vision.find_template(screen, "hundun_event", threshold=0.7)
                    if hundun_result:
                        hundun_x, hundun_y, confidence = hundun_result
                        self.log_status(
                            f"🔥 [OpenCV] 混沌事件模板 pos=({hundun_x},{hundun_y}) "
                            f"conf={confidence:.2f}"
                        )
                        self.selected_event_target = {
                            'name': self.get_text("hellborne_event_name"),
                            'category': '混沌贡品',
                            'center': (hundun_x, hundun_y),
                        }
                        self.state = GameState.SELECTING_EVENT
                        continue

                    text_items = self.vision.scan_screen_for_text_events(screen, roi=EVENT_SCAN_ROI)
                    found_events = []
                    matches_output = []
                    is_boss_phase = False

                    for item in text_items:
                        raw_text = item['text']
                        if any(kw in raw_text for kw in ["选择", "开始", "混沌浪潮", "Select", "start", "Wave", "Offerings"]):
                            continue
                        if any(kw in raw_text for kw in ["理事会", "巴图克", "Council", "Barthuk"]):
                            self.log_status(self.get_text("boss_text_sync", raw_text))
                            self.state = GameState.SELECTING_BOSS_ENTRY
                            is_boss_phase = True
                            break
                        matched_name = self.fuzzy_match_event(raw_text)
                        if matched_name:
                            found_events.append({'name': matched_name, 'center': item['center']})
                            matches_output.append(
                                f"🌟 [MATCH] '{raw_text}' -> {matched_name} ({item['center']})"
                            )

                    if is_boss_phase:
                        continue

                    if found_events:
                        print(self.get_text("ocr_raw_header"))
                        for line in matches_output:
                            print(line)
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
                    # Quest-driven combat: keep patrolling until "选择炼狱供奉"
                    # (offering phase) or death is detected via _priority_tick.
                    # No hard time limit — the BT check drives the exit condition.
                    # A 10-minute safety cap guards against detection failures.
                    _interrupt = {'reason': None}
                    self.nav.patrol_until_done(
                        event_check=lambda: self._priority_tick(_interrupt),
                        safety_timeout=600,
                    )
                    self.log_status(self.get_text("patrol_end"))

                    reason = _interrupt['reason']
                    if reason == 'dead':
                        # _do_resurrect already set state to NAVIGATING_TO_CENTER
                        pass
                    elif reason == 'horde_complete':
                        # Final offering selected — skip center nav, go straight to boss
                        self.log_status("[COMBAT] 魔潮已完成 → NAVIGATING_TO_BOSS")
                        self.state = GameState.NAVIGATING_TO_BOSS
                    elif reason == 'offering' and self.current_wave >= self.max_waves and self.max_waves > 0:
                        self.log_status(self.get_text("all_waves_done"))
                        self.state = GameState.NAVIGATING_TO_BOSS
                    else:
                        # offering detected (or safety timeout) → navigate to centre
                        self.state = GameState.NAVIGATING_TO_CENTER

                elif self.state == GameState.NAVIGATING_TO_BOSS:
                    # If the horde is already complete (quest = "已击败炼狱魔潮"),
                    # the Council offering was already chosen — bosshand icon is gone.
                    # Skip navigation/selection and go straight to the boss door.
                    qt = self.vision.read_quest_tracker()
                    self._emit_quest(qt)
                    if self.vision.check_horde_complete(qt):
                        self.log_status(
                            "[BOSS] 「已击败炼狱魔潮」确认，议会已选，直接前往Boss门"
                        )
                        self.state = GameState.NAVIGATING_TO_BOSS_DOOR
                    else:
                        self.log_status(self.get_text("moving_to_boss_entry"))
                        _nav_intr = {'reason': None}
                        success = self.execute_return_to_center(
                            template_name="bosshand",
                            interrupt_check=lambda: self._priority_tick(_nav_intr),
                        )
                        if success:
                            self.log_status(self.get_text("arrived_boss_entry"))
                            time.sleep(1.0)
                            self.state = GameState.SELECTING_BOSS_ENTRY
                        else:
                            # Nav failed — re-check quest; if horde is now complete,
                            # the player or a teammate must have selected in the
                            # meantime → skip straight to the door.
                            qt2 = self.vision.read_quest_tracker()
                            self._emit_quest(qt2)
                            if self.vision.check_horde_complete(qt2):
                                self.log_status(
                                    "[BOSS] 导航失败但检测到「已击败炼狱魔潮」→ 直接前往Boss门"
                                )
                                self.state = GameState.NAVIGATING_TO_BOSS_DOOR
                            else:
                                time.sleep(1)

                elif self.state == GameState.SELECTING_BOSS_ENTRY:
                    # Guard: if offering is already done, skip selection.
                    qt = self.vision.read_quest_tracker()
                    self._emit_quest(qt)
                    if self.vision.check_horde_complete(qt):
                        self.log_status(
                            "[BOSS] 「已击败炼狱魔潮」确认，跳过议会选择 → Boss门"
                        )
                        self.state = GameState.NAVIGATING_TO_BOSS_DOOR
                    else:
                        self.nav.move_mouse_to_center()

                        ether_count = self.vision.read_ether_count()
                        if ether_count is not None:
                            self.log_status(self.get_text("ether_count", ether_count))
                            target_text = "巴图克" if ether_count > 1066 else "理事会"
                            if self.lang == "en":
                                target_text = "Barthuk" if ether_count > 1066 else "Council"
                        else:
                            self.log_status(self.get_text("no_ether_reading"))
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
                            time.sleep(2)
                            self.state = GameState.NAVIGATING_TO_BOSS_DOOR
                        else:
                            # Not found on screen — check quest again in case
                            # a teammate just completed the selection.
                            qt2 = self.vision.read_quest_tracker()
                            if self.vision.check_horde_complete(qt2):
                                self.log_status(
                                    "[BOSS] 未找到议会选项，但「已击败炼狱魔潮」→ 直接前往Boss门"
                                )
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
                    self.log_status("[BOSS] 向前移动进入Boss房间...")
                    self.nav.move("up", 6.0)
                    self.log_status("[BOSS] 到达Boss区域，开始战斗循环")

                    BOSS_TIMEOUT = 300  # 5 min hard cap
                    QUEST_CHECK_INTERVAL = 3.0
                    boss_start = time.time()
                    last_quest_check = 0.0
                    boss_killed = False

                    while self._running and (time.time() - boss_start) < BOSS_TIMEOUT:
                        # Cast skills continuously
                        self.nav.cast_skills()
                        time.sleep(0.1)

                        now = time.time()
                        elapsed = now - boss_start

                        # Quest-tracker poll every QUEST_CHECK_INTERVAL seconds
                        if now - last_quest_check >= QUEST_CHECK_INTERVAL:
                            last_quest_check = now
                            quest_text = self.vision.read_quest_tracker()
                            self._emit_quest(quest_text)
                            self.log_status(
                                f"[BOSS] ⏱{elapsed:.0f}s 任务状态: {quest_text!r}"
                            )

                            # P1: Boss dead — dungeon complete
                            if self.vision.check_boss_complete(quest_text):
                                self.log_status(
                                    "[BOSS] ✅ 「已完成地下城」→ Boss已击败！"
                                )
                                boss_killed = True
                                break

                            # P2: Still in boss fight — log for visibility
                            if any(kw in quest_text for kw in
                                   ["击败堕落理事会", "击败", "Defeat", "Fallen Council",
                                    "Council", "理事会"]):
                                self.log_status(
                                    f"[BOSS] ⚔ Boss仍存活 ({elapsed:.0f}s / {BOSS_TIMEOUT}s)"
                                )
                            elif quest_text:
                                # Unexpected quest text — log it but keep fighting
                                self.log_status(
                                    f"[BOSS] ❓ 未识别任务文本: {quest_text!r}"
                                )
                            else:
                                self.log_status(
                                    f"[BOSS] ⚠ 任务状态未读取到 ({elapsed:.0f}s)"
                                )

                            # P3: Death during boss fight
                            if self.check_and_handle_death():
                                self.log_status("[BOSS] 💀 Boss战中死亡，等待复活...")
                                break  # _do_resurrect already set state

                    # Loop exited — determine reason
                    if boss_killed:
                        # Build ordered chest queue from user settings.
                        # Order is ALWAYS: equipment → material → gold.
                        # Equipment chest MUST come first (fixed 400-ether cost;
                        # other chests drain all remaining ether).
                        _cs = load_settings().get("chest_selection", [])
                        self._chest_queue = [c for c in CHEST_OPEN_ORDER if c in _cs]
                        # Default when user selected nothing → open material chest
                        if not self._chest_queue:
                            self._chest_queue = ["material"]
                            self.log_status(
                                "[BOSS] 未勾选宝箱类型，默认开材料箱"
                            )
                        self._chest_attempts = 0
                        self._chest_at_base = False   # must navigate to base first
                        self.log_status(
                            f"[BOSS] 转换 → NAVIGATING_TO_CHEST  "
                            f"宝箱队列（装备优先）: {self._chest_queue}"
                        )
                        self.state = GameState.NAVIGATING_TO_CHEST
                    elif self.state != GameState.NAVIGATING_TO_CENTER:
                        # Timeout or _running set to False
                        total = time.time() - boss_start
                        self.log_status(
                            f"[BOSS] ⚠ 循环结束（{total:.0f}s）"
                            f"{'超时' if total >= BOSS_TIMEOUT else '手动停止'}，"
                            f"强制跳转 NAVIGATING_TO_CHEST"
                        )
                        self.state = GameState.NAVIGATING_TO_CHEST

                elif self.state == GameState.NAVIGATING_TO_CHEST:
                    # ── Queue empty → all chests done → return to town first ─
                    if not self._chest_queue:
                        self.log_status("[CHEST] 宝箱队列为空 → 回城")
                        self.state = GameState.RETURNING_TO_TOWN
                        continue

                    import config as _cfg
                    _cfg._load_calibration()

                    # ── Phase A: navigate to base point first ─────────────────
                    # CHEST_NAV_DX/DY is the staging area between all three chests.
                    # Every chest interaction starts and ends here.
                    if not self._chest_at_base:
                        self.log_status(
                            f"[CHEST] 导航至宝箱区域基准点  "
                            f"偏移=({_cfg.CHEST_NAV_DX:.0f},{_cfg.CHEST_NAV_DY:.0f})"
                        )
                        self.nav.move_mouse_to_center()
                        ok_base = self.execute_return_to_center(
                            template_name="chest_marker",
                            override_dx=_cfg.CHEST_NAV_DX,
                            override_dy=_cfg.CHEST_NAV_DY,
                        )
                        if ok_base:
                            self.log_status("[CHEST] ✅ 已到达基准点")
                            self._chest_at_base = True
                        else:
                            self.log_status("[CHEST] ⚠ 基准点导航失败，重试")
                            time.sleep(1)
                        continue   # re-enter state; now _chest_at_base may be True

                    # ── Phase B: navigate from base to specific chest ──────────
                    chest_pref = self._chest_queue[0]   # peek — pop on success/skip
                    target_label = CHEST_LABEL_CN.get(chest_pref, chest_pref)

                    if chest_pref == "equipment":
                        _nav_dx, _nav_dy = _cfg.EQUIP_CHEST_NAV_DX, _cfg.EQUIP_CHEST_NAV_DY
                    elif chest_pref == "material":
                        _nav_dx, _nav_dy = _cfg.MATERIAL_CHEST_NAV_DX, _cfg.MATERIAL_CHEST_NAV_DY
                    elif chest_pref == "gold":
                        _nav_dx, _nav_dy = _cfg.GOLD_CHEST_NAV_DX, _cfg.GOLD_CHEST_NAV_DY
                    else:
                        _nav_dx, _nav_dy = _cfg.CHEST_NAV_DX, _cfg.CHEST_NAV_DY

                    self.log_status(
                        f"[CHEST] 基准点→{target_label}  "
                        f"偏移=({_nav_dx:.0f},{_nav_dy:.0f})  "
                        f"队列: {'→'.join(self._chest_queue)}"
                    )
                    self.nav.move_mouse_to_center()
                    success = self.execute_return_to_center(
                        template_name="chest_marker",
                        override_dx=_nav_dx,
                        override_dy=_nav_dy,
                    )
                    if success:
                        self.log_status(
                            f"[CHEST] ✅ 已到达 {target_label}"
                        )
                        self._chest_attempts = 0
                        self.state = GameState.INTERACTING_WITH_CHEST
                    else:
                        self.log_status(
                            f"[CHEST] ⚠ 导航到 {target_label} 失败，重试"
                        )
                        time.sleep(1)

                elif self.state == GameState.INTERACTING_WITH_CHEST:
                    # Determine target chest type from queue
                    target_type = self._chest_queue[0] if self._chest_queue else None
                    target_label = CHEST_LABEL_CN.get(target_type, "任意") if target_type else "任意"

                    # Per-type scan region
                    import config as _cfg
                    _cfg._load_calibration()
                    if target_type == "equipment":
                        _scan_region = tuple(_cfg.EQUIP_CHEST_SCAN_REGION)
                    elif target_type == "material":
                        _scan_region = tuple(_cfg.MATERIAL_CHEST_SCAN_REGION)
                    elif target_type == "gold":
                        _scan_region = tuple(_cfg.GOLD_CHEST_SCAN_REGION)
                    else:
                        _scan_region = (800, 150, 1760, 950)  # broad fallback

                    self.log_status(
                        f"[宝箱] 开始扫描  目标={target_label}  "
                        f"扫描范围={_scan_region}"
                    )
                    trigger_pos = self._find_chest_by_type(target_type, _scan_region)

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

                        # 3. 流程结束 — pop this chest from queue, go back
                        self.log_status(self.get_text("pickup_finished"))
                        if self._chest_queue:
                            done = self._chest_queue.pop(0)
                            self.log_status(
                                f"[CHEST] {done}箱已完成  "
                                f"队列剩余: {self._chest_queue or '（全部完成）'}"
                            )
                        self._chest_attempts = 0

                        if self._chest_queue:
                            # More chests — reset to base-point phase before next
                            self.log_status(
                                f"[CHEST] 返回基准点，然后前往下一个宝箱 "
                                f"{CHEST_LABEL_CN.get(self._chest_queue[0], '?')}..."
                            )
                            self._chest_at_base = False
                            time.sleep(1.5)
                            self.state = GameState.NAVIGATING_TO_CHEST
                        else:
                            # All chests done → go back to town then activate
                            self.log_status("[CHEST] 所有宝箱已开完 → 回城")
                            self.state = GameState.RETURNING_TO_TOWN
                    else:
                        # Chest interaction not found — count as one attempt
                        self._chest_attempts += 1
                        chest_label = (
                            self._chest_queue[0] if self._chest_queue else "unknown"
                        )
                        if self._chest_attempts >= self._MAX_CHEST_ATTEMPTS:
                            skipped = (
                                self._chest_queue.pop(0)
                                if self._chest_queue else chest_label
                            )
                            self.log_status(
                                f"[CHEST] ⚠ {skipped}箱连续 "
                                f"{self._MAX_CHEST_ATTEMPTS} 次未找到交互点，跳过  "
                                f"队列剩余: {self._chest_queue or '（无）'}"
                            )
                            self._chest_attempts = 0
                            self._chest_at_base = False   # return to base before next
                            self.state = GameState.NAVIGATING_TO_CHEST
                        else:
                            self.log_status(
                                f"[CHEST] 未找到 {chest_label}箱交互点，"
                                f"重试 ({self._chest_attempts}/{self._MAX_CHEST_ATTEMPTS})"
                            )
                            time.sleep(1)

                elif self.state == GameState.RETURNING_TO_TOWN:
                    self.log_status("[回城] 按 T 传送回城...")
                    kb.press_and_release('t')
                    # Wait for the town-portal loading screen to finish
                    time.sleep(10.0)
                    self.log_status("[回城] 已回城，准备激活下一个罗盘")
                    self.state = GameState.ACTIVATING_NEXT_COMPASS

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
                        compass = None
                        for _ck in self._compass_keys:
                            _res = self.vision.find_template_in_region(screen, _ck, INVENTORY_REGION, threshold=0.7)
                            if _res:
                                compass = _res
                                self.log_status(self.get_text("compass_found", _res[:2], _res[2]) + f" [{_ck}]")
                                break
                        if compass:
                            pyautogui.rightClick(compass[0], compass[1])
                            time.sleep(1.5)
                            if self.handle_modal_accept("modal_usekey"):
                                # Compass activated — count this as a completed run
                                self.run_count += 1
                                self._emit_run_count()
                                self.log_status(
                                    f"[RUN] 第 {self.run_count}"
                                    + (f"/{self.max_runs}" if self.max_runs > 0 else "")
                                    + " 次罗盘已激活"
                                )
                                # Check run limit
                                if self.max_runs > 0 and self.run_count >= self.max_runs:
                                    self.log_status(
                                        f"[RUN] ✅ 已完成设定的 {self.max_runs} 次，自动停止"
                                    )
                                    kb.press_and_release('i')
                                    time.sleep(1.0)
                                    self._running = False
                                else:
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
                    # 副本初始区有怪物 — 先原地释放技能3秒再导航
                    self.log_status("🗡️ 入场先清场3秒...")
                    pre_cast_start = time.time()
                    while time.time() - pre_cast_start < 3.0 and self._running:
                        self.nav.cast_skills()
                        time.sleep(0.05)

                    # Navigate directly to event center using calibrated offset
                    success = self.execute_return_to_center(
                        template_name="bonehand",
                        cast_while_moving=False,
                    )
                    if success:
                        self.log_status(self.get_text("arrived_start_pos"))
                    else:
                        self.log_status("[ENTRY] 导航到中心超时，继续扫描")
                    # Whether nav succeeded or timed out, proceed to scanning
                    self.state = GameState.SCANNING_FOR_EVENTS

                elif self.state == GameState.DEAD:
                    # Death was already handled in check_and_handle_death();
                    # if we somehow land here without recovery, just wait.
                    time.sleep(1)

                elif self.state == GameState.IDLE:
                    time.sleep(1)

            except KeyboardInterrupt:
                print(self.get_text("stopped_by_user"))
                self._running = False
                break
            except Exception as e:
                print(self.get_text("error_occurred", e))
                import traceback
                traceback.print_exc()
                self._running = False
                break

    def handle_modal_accept(self, template_name, timeout=3.0):
        """扫描弹窗并点击 '接受' 按钮。"""
        from config import MODAL_SCAN_REGION
        start_time = time.time()
        while time.time() - start_time < timeout:
            screen = self.vision.capture_screen()
            modal = self.vision.find_template(screen, template_name, threshold=0.8)
            if modal:
                text_items = self.vision.scan_screen_for_text_events(screen, roi=MODAL_SCAN_REGION)
                for item in text_items:
                    if any(kw in item['text'] for kw in ["接受", "Accept"]):
                        self.log_status(self.get_text("modal_accepted", item['text']))
                        self.nav.click_position(item['center'])
                        return True
            time.sleep(0.3)
        return False

    def execute_return_to_center(
        self,
        template_name="bonehand",
        verbose=False,
        tolerance=None,
        interrupt_check=None,
        override_dx=None,
        override_dy=None,
        cast_while_moving=True,
    ):
        """通过跟随模板图标导航到中心。到达时返回 True。

        Parameters
        ----------
        interrupt_check : callable | None
            Optional zero-argument callable (e.g. ``_priority_tick``).
            Called every 3 nav steps.  If it returns True the navigation is
            aborted.
        override_dx / override_dy : float | None
            If provided, these values replace the default target offset for
            *template_name*.  Used by NAVIGATING_TO_CHEST to pass the
            per-chest-type calibrated offsets without branching inside here.
        """
        from config import (CHEST_TOLERANCE, NAV_CENTER_DX, NAV_CENTER_DY,
                            CHEST_NAV_DX, CHEST_NAV_DY,
                            BOSS_DOOR_NAV_DX, BOSS_DOOR_NAV_DY)
        if tolerance is None:
            if template_name == "bossdoor":
                tolerance = BOSS_DOOR_TOLERANCE
            elif template_name == "chest_marker":
                tolerance = CHEST_TOLERANCE
            else:
                tolerance = CENTER_TOLERANCE

        target_dx, target_dy = 0, 0
        if template_name == "chest_marker":
            target_dx, target_dy = float(CHEST_NAV_DX), float(CHEST_NAV_DY)
        elif template_name == "bossdoor":
            target_dx, target_dy = float(BOSS_DOOR_NAV_DX), float(BOSS_DOOR_NAV_DY)
        elif template_name in ("bonehand", "extrahand"):
            target_dx, target_dy = float(NAV_CENTER_DX), float(NAV_CENTER_DY)

        # Caller-supplied override takes priority over defaults above
        if override_dx is not None:
            target_dx = float(override_dx)
        if override_dy is not None:
            target_dy = float(override_dy)

        self.log_status(
            f"[NAV] 开始导航 template={template_name} "
            f"target_offset=({target_dx:.0f},{target_dy:.0f}) "
            f"tolerance={tolerance}  MAX_STEPS={MAX_STEPS}"
        )

        for step in range(1, MAX_STEPS + 1):
            if not self._running:
                return False
            # BT priority tick every 3 nav steps (~3-5 s interval)
            if interrupt_check and step % 3 == 0:
                if interrupt_check():
                    return False
            minimap = self.vision.capture_minimap()
            icon_rel_x, icon_rel_y = None, None

            if template_name == "chest_marker":
                haystack_gray = cv2.cvtColor(minimap, cv2.COLOR_BGR2GRAY)
                template = self.vision.get_template("chest_marker")
                if template is None: return False
                th, tw = template.shape[:2]
                x1, y1, _, _ = MINIMAP_REGION
                res = cv2.matchTemplate(haystack_gray, template, cv2.TM_CCOEFF_NORMED)
                loc = np.where(res >= MATCH_THRESHOLD)
                points = list(zip(*loc[::-1]))
                if not points:
                    self.log_status(
                        f"[NAV] [{step}/{MAX_STEPS}] chest_marker 未在小地图找到，等待..."
                    )
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
                    self.log_status(
                        f"[NAV] [{step}/{MAX_STEPS}] {template_name} 未找到图标，等待..."
                    )
                    time.sleep(0.2)
                    continue
                
                icon_rel_x, icon_rel_y, _ = result
                template_name = current_used_template # 更新显示的模板名称以便日志准确

            if icon_rel_x is not None:
                x1, y1, _, _ = MINIMAP_REGION
                abs_icon_x = x1 + icon_rel_x
                abs_icon_y = y1 + icon_rel_y

                raw_dx = abs_icon_x - PLAYER_POS[0]
                raw_dy = abs_icon_y - PLAYER_POS[1]

                # error = distance between current icon offset and desired offset
                error_x = raw_dx - target_dx
                error_y = raw_dy - target_dy

                self.log_status(
                    self.get_text("nav_log",
                        f"[{step}/{MAX_STEPS}] {template_name} | "
                        f"raw=({raw_dx:.0f},{raw_dy:.0f}) err=({error_x:.0f},{error_y:.0f})"
                    )
                )

                if abs(error_x) <= tolerance and abs(error_y) <= tolerance:
                    # ── Arrival confirmation ──────────────────────────────────
                    # Wait briefly and re-verify to reject false positives caused
                    # by the character being knocked through the target zone.
                    time.sleep(0.4)
                    confirm = self._read_icon_error(template_name, target_dx, target_dy)
                    if confirm is not None:
                        cx, cy = confirm
                        if abs(cx) <= tolerance and abs(cy) <= tolerance:
                            self.log_status(
                                self.get_text("nav_log",
                                    f"✅ 确认到达 {template_name}! "
                                    f"(err={cx:.0f},{cy:.0f})"
                                )
                            )
                            return True
                        # Transient pass-through (e.g. knockback) — keep navigating
                        self.log_status(
                            self.get_text("nav_log",
                                f"⚠ 误判到达 (被击飞?) re-err=({cx:.0f},{cy:.0f}), 继续导航"
                            )
                        )
                        error_x, error_y = cx, cy
                    # Icon lost on re-check — continue loop

                # Move toward target; cast skills only during combat phases
                if abs(error_x) > tolerance:
                    dur = self.nav.calculate_duration(abs(error_x))
                    if cast_while_moving:
                        self.nav.move_while_casting("right" if error_x > 0 else "left", dur)
                    else:
                        self.nav.move("right" if error_x > 0 else "left", dur)
                if abs(error_y) > tolerance:
                    dur = self.nav.calculate_duration(abs(error_y))
                    if cast_while_moving:
                        self.nav.move_while_casting("down" if error_y > 0 else "up", dur)
                    else:
                        self.nav.move("down" if error_y > 0 else "up", dur)
                time.sleep(0.15)
        self.log_status(
            f"[NAV] ⚠ 导航超时！已尝试 {MAX_STEPS} 步，template={template_name} "
            f"target=({target_dx:.0f},{target_dy:.0f}) tolerance={tolerance}"
        )
        return False

    def _read_icon_error(
        self,
        template_name: str,
        target_dx: float,
        target_dy: float,
    ) -> tuple[float, float] | None:
        """Capture minimap and return (error_x, error_y) for the event icon.

        Returns None if the icon cannot be found.
        Used for arrival re-verification after the main nav loop detects it is
        within tolerance, to guard against knockback false-positives.
        """
        try:
            minimap = self.vision.capture_minimap()
            x1, y1 = MINIMAP_REGION[0], MINIMAP_REGION[1]

            result = self.vision.find_template(minimap, "extrahand", threshold=MATCH_THRESHOLD)
            if not result:
                result = self.vision.find_template(minimap, "bonehand", threshold=MATCH_THRESHOLD)
            if not result and template_name not in ("bonehand", "extrahand"):
                result = self.vision.find_template(minimap, template_name, threshold=MATCH_THRESHOLD)
            if not result:
                return None

            rx, ry, _ = result
            raw_dx = (x1 + rx) - PLAYER_POS[0]
            raw_dy = (y1 + ry) - PLAYER_POS[1]
            return (raw_dx - target_dx, raw_dy - target_dy)
        except Exception:
            return None

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

    # ── Chest type detection ──────────────────────────────────────────────────

    def _find_chest_by_type(
        self,
        target_type: str | None,
        scan_region: tuple,
    ) -> tuple | None:
        """Upward hover-scan from screen centre to find and identify chests.

        The mouse starts at the screen centre and moves upward step by step,
        exactly as the player would manually hover over chests.  When the game
        shows a tooltip (detected via template match OR OCR keywords) the
        tooltip text is OCR-read to classify the chest type.

        If *target_type* is None → first tooltip found is used ("any" mode).
        If *target_type* is specified:
          - Matching type     → return position immediately.
          - Non-matching type → record position, nudge mouse sideways to dismiss
                                tooltip, continue scanning upward.
        After the full upward pass, a second pass with a slight X offset is
        attempted so that chests at different horizontal positions are covered.

        Returns (click_x, click_y) ready to press F on, or None.
        """
        sr_x1, sr_y1, sr_x2, sr_y2 = scan_region
        target_label = CHEST_LABEL_CN.get(target_type, "任意") if target_type else "任意"

        # ── Optional fast path: visual template match ─────────────────────────
        if target_type and target_type in CHEST_TEMPLATE_NAMES:
            tmpl = CHEST_TEMPLATE_NAMES[target_type]
            if self.vision.variant_count(tmpl) > 0:
                screen = self.vision.capture_screen()
                res = self.vision.find_template_in_region(
                    screen, tmpl, scan_region, threshold=0.60
                )
                if res:
                    cx, cy, conf = res
                    self.log_status(
                        f"[宝箱] 模板快速匹配到 {target_label} ({cx},{cy}) "
                        f"conf={conf:.2f}"
                    )
                    return (cx, cy)
                self.log_status(
                    f"[宝箱] 模板未命中，切换悬停+OCR扫描"
                )

        # ── Upward hover scan ─────────────────────────────────────────────────
        # Scan origin: horizontal centre of scan_region, start at bottom.
        center_x = (sr_x1 + sr_x2) // 2
        start_y  = min(sr_y2, 780)          # don't start below 780 (HUD area)
        end_y    = max(sr_y1, 100)          # don't scan above 100

        # X offsets to try: centre first, then slight left/right nudges
        # so chests not directly in front are still reached.
        x_offsets = [0, -160, 160, -320, 320]

        # OCR bounding box (wide to catch tooltip no matter where it renders)
        _ocr_roi = (
            max(0,    sr_x1 - 80),
            max(0,    sr_y1 - 60),
            min(2560, sr_x2 + 80),
            min(1440, sr_y2 + 30),
        )

        found_map: dict[str, tuple] = {}  # type → click position

        def _upward_pass(mx: int) -> tuple | None:
            """Scan upward at column mx.  Returns matching click pos or None."""
            pyautogui.moveTo(mx, start_y, duration=0.05)
            time.sleep(0.15)

            step = 35
            for my in range(start_y, end_y, -step):
                if not self._running:
                    return None

                pyautogui.moveTo(mx, my, duration=0.02)
                time.sleep(0.13)

                screen = self.vision.capture_screen()

                # Quick trigger: template OR keyword presence
                triggered = bool(
                    self.vision.find_template(
                        screen, "tip_bosschest", threshold=0.65
                    )
                )
                if not triggered:
                    items = self.vision.scan_screen_for_text_events(
                        screen, roi=_ocr_roi
                    )
                    triggered = any(
                        kw in item["text"]
                        for item in items
                        for kw in ["强效", "Greater", "Spoils", "战利品"]
                    )

                if not triggered:
                    continue

                # Tooltip found → full OCR to classify
                items = self.vision.scan_screen_for_text_events(
                    screen, roi=_ocr_roi
                )
                full_text = " ".join(item["text"] for item in items)
                det_type  = identify_chest_type(full_text)

                # Click position: hover point itself (F-key interaction)
                click_pos = (
                    mx,
                    max(end_y, min(1440, my)),
                )

                self.log_status(
                    f"[宝箱] 悬停 ({mx},{my})  "
                    f"OCR={full_text[:60]!r}  "
                    f"类型={det_type or '未识别'}"
                )

                if target_type is None or det_type == target_type:
                    self.log_status(
                        f"[宝箱] ✅ 目标 {target_label} @ {click_pos}"
                    )
                    return click_pos

                # Wrong type — record, dismiss tooltip, keep going up
                if det_type and det_type not in found_map:
                    found_map[det_type] = click_pos
                    wrong = CHEST_LABEL_CN.get(det_type, det_type or "?")
                    self.log_status(
                        f"[宝箱] 发现 {wrong}箱（非目标 {target_label}），继续向上"
                    )

                # Nudge mouse sideways briefly to dismiss tooltip
                pyautogui.moveTo(mx + 200, my, duration=0.03)
                time.sleep(0.10)
                pyautogui.moveTo(mx, my - step, duration=0.02)

            return None

        # Try each X offset until target type is found
        for dx in x_offsets:
            if not self._running:
                break
            mx = max(sr_x1 + 40, min(sr_x2 - 40, center_x + dx))
            result = _upward_pass(mx)
            if result is not None:
                return result

        # ── Post-scan fallback ────────────────────────────────────────────────
        if found_map:
            self.log_status(
                f"[宝箱] ⚠ 未找到目标 {target_label}，"
                f"扫描到: "
                f"{', '.join(CHEST_LABEL_CN.get(t,t) for t in found_map)}"
            )
        else:
            self.log_status(
                f"[宝箱] ⚠ 未扫描到任何悬停提示（扫描范围 {sr_x1}-{sr_x2}）"
            )
        return None

    def select_best_event(self, found_events):
        """Pick the best tribute using the user's category preferences.

        Delegates to settings_manager.pick_tribute so that the category-filter
        and fallback logic live in one place.
        """
        settings = load_settings()
        chosen = pick_tribute(found_events, settings, self.desired_events)
        if chosen:
            self.log_status(
                f"[贡品选择] 优先类别={settings.get('tribute_categories')} "
                f"→ 选中: {chosen['name']!r}"
            )
        return chosen

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
