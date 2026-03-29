import cv2
import numpy as np
import pyautogui
import easyocr
import re
from pathlib import Path
from config import MINIMAP_REGION, WAVE_REGION, ETHER_REGION, LOGS_DIR

class VisionSystem:
    def __init__(self, lang="cn", translations=None):
        # Each key maps to a *list* of grayscale numpy arrays (variant templates).
        # find_template tries all variants and returns the best match above threshold.
        self.templates: dict[str, list] = {}
        self.lang = lang
        self.translations = translations or {}
        
        print(self.get_text("ocr_init"))
        # gpu=False: CUDA is not required; avoids DLL init failures on systems
        # without a compatible CUDA toolkit even if a GPU is present.
        self.reader = easyocr.Reader(['ch_sim', 'en'], gpu=False, verbose=False)
        print(self.get_text("ocr_init_done"))

    def get_text(self, key, *args):
        txt = self.translations.get(key, key)
        if args:
            try:
                return txt.format(*args)
            except Exception:
                return txt
        return txt

    def load_template(self, name: str, path: Path) -> bool:
        """Load a template image and append it as a variant under *name*.

        Calling this multiple times with the same *name* accumulates variants;
        find_template will try all of them and return the best match.
        """
        if not path.exists():
            return False

        img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            return False

        h, w = img.shape
        if h > 20 and w > 20:
            img = img[4:-4, 4:-4]

        if name not in self.templates:
            self.templates[name] = []
        self.templates[name].append(img)
        return True

    def get_template(self, name: str):
        """Return the primary (first) template array, or None."""
        variants = self.templates.get(name)
        return variants[0] if variants else None

    def variant_count(self, name: str) -> int:
        """Return how many variant templates are loaded for *name*."""
        return len(self.templates.get(name, []))

    def capture_minimap(self):
        x1, y1, x2, y2 = MINIMAP_REGION
        width = x2 - x1
        height = y2 - y1
        
        # Check bounds to avoid crash
        sw, sh = pyautogui.size()
        if x2 > sw or y2 > sh:
            raise ValueError(self.get_text("screen_error", MINIMAP_REGION, (sw, sh)))
            
        shot = pyautogui.screenshot(region=(x1, y1, width, height))
        return cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
    
    def capture_screen(self):
        return cv2.cvtColor(np.array(pyautogui.screenshot()), cv2.COLOR_RGB2BGR)

    def find_template(self, haystack, template_name, threshold=0.6):
        """Try ALL loaded variants for *template_name* and return the best match.

        Returns (center_x, center_y, score) in haystack-local coordinates, or None.
        """
        variants = self.templates.get(template_name)
        if not variants:
            return None

        haystack_gray = cv2.cvtColor(haystack, cv2.COLOR_BGR2GRAY)

        best_val = -1.0
        best_loc = None
        best_shape = None

        for tmpl in variants:
            # Skip if template is larger than haystack
            if tmpl.shape[0] > haystack_gray.shape[0] or tmpl.shape[1] > haystack_gray.shape[1]:
                continue
            res = cv2.matchTemplate(haystack_gray, tmpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val > best_val:
                best_val = max_val
                best_loc = max_loc
                best_shape = tmpl.shape[:2]

        if best_val < threshold or best_loc is None:
            return None

        th, tw = best_shape
        center_x = best_loc[0] + tw // 2
        center_y = best_loc[1] + th // 2
        return (center_x, center_y, best_val)

    def find_template_in_region(self, haystack, template_name, roi, threshold=0.6):
        """
        Template match inside ROI and return global center coords.
        roi format: (x1, y1, x2, y2)
        """
        roi_x1, roi_y1, roi_x2, roi_y2 = roi
        crop = haystack[roi_y1:roi_y2, roi_x1:roi_x2]
        result = self.find_template(crop, template_name, threshold=threshold)
        if not result:
            return None
        cx, cy, score = result
        return (roi_x1 + cx, roi_y1 + cy, score)

    def scan_screen_for_text_events(self, screen_img, roi=None):
        """
        Scans a region for events. If roi is None, scans full screen.
        roi format: (x1, y1, x2, y2)
        """
        h, w = screen_img.shape[:2]
        
        if roi:
            roi_x1, roi_y1, roi_x2, roi_y2 = roi
            crop = screen_img[roi_y1:roi_y2, roi_x1:roi_x2]
        else:
            # Default to full screen if no ROI provided
            roi_x1, roi_y1 = 0, 0
            crop = screen_img
        
        # 图像预处理：提高 OCR 识别率
        # 1. 转换为灰度图
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        # 2. 放大图像（对于小字体很有帮助）
        upscaled = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
        
        try:
            # 使用预处理后的图像进行识别
            results = self.reader.readtext(upscaled, detail=1)
        except Exception:
            return []

        detected_items = []
        for (bbox, text, prob) in results:
            if prob < 0.2: # Increased threshold for speed/accuracy
                continue
                
            tl, tr, br, bl = bbox
            # 映射回原始 crop 坐标（除以放大倍数 1.5）
            center_x = int(((tl[0] + br[0]) / 2) / 1.5)
            center_y = int(((tl[1] + br[1]) / 2) / 1.5)
            
            global_x = roi_x1 + center_x
            global_y = roi_y1 + center_y
            
            detected_items.append({
                'text': text,
                'center': (global_x, global_y),
                'confidence': prob
            })
            
        return detected_items

    # ── Quest-tracker helpers ─────────────────────────────────────────────────

    def read_quest_tracker(self) -> str:
        """Scan QUEST_TRACKER_REGION and return all recognised lines joined with ' | '.

        This is the single OCR source for all quest-related checks.
        Callers should cache the result for the current tick rather than
        calling multiple check_* methods independently.

        The raw text is always printed so calibration issues can be spotted
        immediately in the log.

        Returns empty string on failure.
        """
        from config import QUEST_TRACKER_REGION
        x1, y1, x2, y2 = QUEST_TRACKER_REGION
        try:
            sw, sh = pyautogui.size()
            rx2, ry2 = min(x2, sw), min(y2, sh)
            if rx2 <= x1 or ry2 <= y1:
                return ""
            shot = pyautogui.screenshot(region=(x1, y1, rx2 - x1, ry2 - y1))
            img = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # 2× upscale improves OCR accuracy on small game fonts
            up = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
            results = self.reader.readtext(up, detail=0)
            text = " | ".join(r.strip() for r in results if r.strip())
            # Only print when text changes to avoid log flooding
            if not hasattr(self, "_last_quest_ocr") or self._last_quest_ocr != text:
                self._last_quest_ocr = text
                print(f"[QUEST-OCR] region={QUEST_TRACKER_REGION}  raw={text!r}")
            return text
        except Exception as e:
            print(f"[read_quest_tracker error] {e}")
            return ""

    def check_combat_quest(self, quest_text: str = "") -> bool:
        """Return True when quest-tracker shows a COMBAT objective.

        Trigger phrase: "消灭怪物" (or variants).
        Pass an already-read quest_text to avoid a second OCR call.
        """
        if not quest_text:
            quest_text = self.read_quest_tracker()
        # Primary keyword + individual fallbacks in case OCR splits characters
        keywords = [
            "消灭怪物",          # exact match (preferred)
            "消灭",              # partial — OCR may drop "怪物"
            "怪物",              # OCR may drop "消灭"
            "击败",              # alternate game phrasing
            "Slay", "Kill", "Defeat",
        ]
        return any(kw in quest_text for kw in keywords)

    def check_offering_selection(self, quest_text: str = "") -> bool:
        """Return True when quest-tracker shows the tribute-selection phase.

        Trigger phrase: "选择炼狱供奉".
        Pass an already-read quest_text to avoid a second OCR call.
        """
        if not quest_text:
            quest_text = self.read_quest_tracker()
        # Try progressively shorter fragments so a partial OCR read still works.
        # "炼狱供奉" is the most reliable substring; "供奉" alone is too broad.
        keywords = [
            "选择炼狱供奉",      # full phrase (best)
            "炼狱供奉",          # without leading "选择"
            "炼狱供",            # OCR may drop last char
            "狱供奉",            # OCR may drop first char
            "Select Infernal", "Infernal Offering",
        ]
        return any(kw in quest_text for kw in keywords)

    def scan_tribute_icons(
        self,
        screen,
        roi: tuple,
        threshold: float = 0.60,
    ) -> list[dict]:
        """Template-match all uploaded tribute category icons within *roi*.

        Returns a list of found tributes, each a dict:
            {'name': <category_key>, 'category': <category_key>, 'center': (x, y)}

        The 'name' and 'category' fields are the same string (e.g. "魔裔类") so
        that the result is directly compatible with ``pick_tribute``.

        Parameters
        ----------
        screen : np.ndarray
            Full-screen capture (BGR).
        roi : tuple
            (x1, y1, x2, y2) region to search within.
        threshold : float
            Template-matching confidence threshold (0–1).
        """
        from core.settings_manager import TRIBUTE_ICON_TEMPLATES

        found = []
        for category, tmpl_name in TRIBUTE_ICON_TEMPLATES.items():
            if self.variant_count(tmpl_name) == 0:
                continue  # user hasn't uploaded this icon yet
            result = self.find_template_in_region(screen, tmpl_name, roi, threshold=threshold)
            if result:
                cx, cy, conf = result
                print(
                    f"[贡品图标] ✅ {category} ({tmpl_name}) 匹配 "
                    f"pos=({cx},{cy}) conf={conf:.2f}"
                )
                found.append({
                    'name':     category,
                    'category': category,
                    'center':   (cx, cy),
                })
            else:
                if self.variant_count(tmpl_name) > 0:
                    print(f"[贡品图标] ✗ {category} 未匹配 (threshold={threshold})")
        return found

    def check_horde_complete(self, quest_text: str = "") -> bool:
        """Return True when the Infernal Horde pre-boss waves are all done.

        Trigger phrase: "已击败炼狱魔潮" — appears after the final (10th-wave)
        offering is selected, signalling that the Council boss room is now open.

        NOTE: Do NOT use "炼狱魔潮" alone — that is the dungeon name and appears
        in every quest line for this activity (e.g. "炼狱魔潮 | 选择炼狱供奉").
        Only match when the "击败" (defeat) verb is present.
        """
        if not quest_text:
            quest_text = self.read_quest_tracker()
        keywords = [
            "已击败炼狱魔潮",          # full phrase with "已"
            "击败炼狱魔潮",            # OCR may drop the leading "已"
            "Defeated Infernal Horde", "Infernal Horde defeated",
        ]
        return any(kw in quest_text for kw in keywords)

    def check_final_choice(self, quest_text: str = "") -> bool:
        """Return True when the Council-boss selection UI is showing.

        Trigger phrase: "做出你最终选择" — appears when the player is at the
        boss-selection altar and must choose between 巴图克 and 堕落理事会.
        Maps to SELECTING_BOSS_ENTRY.
        """
        if not quest_text:
            quest_text = self.read_quest_tracker()
        keywords = [
            "做出你最终选择",    # full phrase
            "最终选择",          # OCR may drop leading chars
            "Make Your Final Choice", "Final Choice",
        ]
        return any(kw in quest_text for kw in keywords)

    def check_boss_fight(self, quest_text: str = "") -> bool:
        """Return True when the boss fight (Council / Barthuk) is in progress.

        The quest objective switches to "击败堕落理事会" or "击败巴图克" once
        the player enters the boss arena.
        """
        if not quest_text:
            quest_text = self.read_quest_tracker()
        keywords = [
            "击败堕落理事会", "堕落理事会",
            "击败巴图克", "巴图克",
            "Defeat the Fell Council", "Fell Council",
            "Defeat Bartuc", "Bartuc",
        ]
        return any(kw in quest_text for kw in keywords)

    def check_boss_complete(self, quest_text: str = "") -> bool:
        """Return True when quest-tracker shows dungeon/boss completion.

        Trigger phrase: "已完成地下城".
        Pass an already-read quest_text to avoid a second OCR call.
        """
        if not quest_text:
            quest_text = self.read_quest_tracker()
        keywords = [
            "已完成地下城",      # exact
            "地下城已完成",      # alternate word order
            "完成地下城",        # OCR may drop "已"
            "Dungeon Complete", "dungeon complete",
        ]
        return any(kw in quest_text for kw in keywords)

    def read_wave_number(self):
        """
        Captures the wave number region and parses current wave.
        Returns: (current_wave, max_wave) e.g., (0, 10) or None if failed.
        """
        x1, y1, x2, y2 = WAVE_REGION
        w = x2 - x1
        h = y2 - y1
        
        # Check bounds
        sw, sh = pyautogui.size()
        if x2 > sw or y2 > sh:
            return None # Don't crash, just return None
            
        shot = pyautogui.screenshot(region=(x1, y1, w, h))
        img = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
        
        # Debug save to see what we are OCRing
        self.save_debug_image(img, "debug_wave_region.png")
        
        try:
            results = self.reader.readtext(img, detail=0)
            if not results:
                return None
                
            full_text = " ".join(results).replace(" ", "")
            
            # 1. Standard match: "0/10", "1/10"
            match = re.search(r'(\d+)/(\d+)', full_text)
            if match:
                curr, total = int(match.group(1)), int(match.group(2))
                # Total waves in compass are usually 8 or 10. 
                # If total is something like 59, it's likely a timer.
                if total in [8, 10] and curr <= total:
                    return curr, total
                else:
                    return None # Ignore timer-like reads

            # 2. Handle common misread: "21" instead of "2/10", "31" instead of "3/10"
            # If we see "波次:X1" or just "X1" where X is a digit
            match = re.search(r'(?:波次:)?(\d)1$', full_text) # Matches "21" at the end
            if not match:
                match = re.search(r'(?:波次:)?(\d)1\D', full_text) # Matches "31" followed by non-digit
            
            if match:
                curr = int(match.group(1))
                return curr, 10 # Assume total is 10 if it ends in 1
            
            # 3. Fallback: separator is not a slash
            match = re.search(r'(\d+)\D+(\d+)', full_text)
            if match:
                curr, total = int(match.group(1)), int(match.group(2))
                if curr <= total and total > 0:
                    return curr, total
                
            return full_text
            
        except Exception:
            pass
            
        return None

    def read_ether_count(self):
        """
        Captures the ether count region and parses the number.
        Returns: int or None if failed.
        """
        x1, y1, x2, y2 = ETHER_REGION
        w = x2 - x1
        h = y2 - y1
        
        # Check bounds
        sw, sh = pyautogui.size()
        if x2 > sw or y2 > sh:
            return None
            
        shot = pyautogui.screenshot(region=(x1, y1, w, h))
        img = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
        
        try:
            results = self.reader.readtext(img, detail=0)
            # 合并所有文本，移除空格、逗号等干扰项
            full_text = "".join(results).replace(",", "").replace(".", "").replace(" ", "")
            # 寻找数字部分
            match = re.search(r'(\d+)', full_text)
            if match:
                return int(match.group(1))
        except Exception:
            pass
            
        return None

    def save_debug_image(self, image, name="debug.png"):
        path = LOGS_DIR / name
        cv2.imwrite(str(path), image)
