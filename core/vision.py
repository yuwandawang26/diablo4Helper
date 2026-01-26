import cv2
import numpy as np
import pyautogui
import easyocr
import re
from pathlib import Path
from config import MINIMAP_REGION, WAVE_REGION, ETHER_REGION, LOGS_DIR

class VisionSystem:
    def __init__(self, lang="cn", translations=None):
        self.templates = {}
        self.lang = lang
        self.translations = translations or {}
        
        print(self.get_text("ocr_init"))
        # 抑制详细输出
        self.reader = easyocr.Reader(['ch_sim', 'en'], gpu=True, verbose=False) 
        print(self.get_text("ocr_init_done"))

    def get_text(self, key, *args):
        txt = self.translations.get(key, key)
        if args:
            try:
                return txt.format(*args)
            except Exception:
                return txt
        return txt

    def load_template(self, name: str, path: Path):
        """Loads a single template image (e.g. minimap icon)."""
        if not path.exists():
            return False
        
        img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            return False
            
        h, w = img.shape
        crop = 4
        if h > 20 and w > 20:
            img = img[crop:-crop, crop:-crop]
            
        self.templates[name] = img
        return True

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
        if template_name not in self.templates:
            return None

        template = self.templates[template_name]
        haystack_gray = cv2.cvtColor(haystack, cv2.COLOR_BGR2GRAY)

        res = cv2.matchTemplate(haystack_gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        if max_val < threshold:
            return None

        th, tw = template.shape[:2]
        center_x = max_loc[0] + tw // 2
        center_y = max_loc[1] + th // 2
        
        return (center_x, center_y, max_val)

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
