"""
分析截图，在 config 中的关键位置上绘制标记并验证。

模式 1 - 从 minimap_info.png 校准小地图（2K 显示器新截图）：
  - 图中 #fbf23c 纯色覆盖区域 = 小地图；仅检测小地图，波次 WAVE_REGION 沿用 config。
  - 更新 config 中 MINIMAP_REGION，生成 logs/verify_positions.png 供检查。
  - 若小地图 bbox 不在右上，默认不覆盖 config；可加 --force 强制覆盖。--dry-run 仅检测与出图，不写 config。

模式 2 - 使用 config 验证 minimap_readyloop.png：
  - 在 config 位置上绘制标记，并在小地图内查找 icon_health 参照物。
"""
import argparse
import cv2
import numpy as np
import re
from pathlib import Path

from config import MINIMAP_REGION, PLAYER_POS, COMPASS_ICON_POS, WAVE_REGION, BOSS_DOOR_POS, LOGS_DIR, ASSETS_DIR, MATCH_THRESHOLD, ROOT_DIR

LOGS_DIR.mkdir(exist_ok=True)

# 校准用截图：黄 #fbf23c=小地图覆盖层；波次沿用 config
CALIBRATE_IMAGE = ASSETS_DIR / "minimap_info.png"
MINIMAP_HEX = "#fbf23c"
TOLERANCE = 12       # 默认颜色容差
MINIMAP_TOLERANCE = 20  # 小地图黄色容差（截图/压缩可能有色偏）

def rgb_to_bgr(hex_color: str):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b, g, r)

def _bbox_from_mask(mask):
    ys, xs = np.where(mask > 0)
    if xs.size == 0 or ys.size == 0:
        return None
    return (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))

def detect_color_region(img, hex_color: str, tolerance: int = TOLERANCE, top_right_only: bool = True):
    """
    在图中找出指定 hex 颜色的连通区域，返回 (x1, y1, x2, y2)。
    top_right_only: 若为 True，只考虑右上（x>宽/2, y<高*0.6）内连通块，取面积最大者；
                    若无一符合则退回全图同色最大连通块。
    """
    b, g, r = rgb_to_bgr(hex_color)
    lo = np.array([max(0, b - tolerance), max(0, g - tolerance), max(0, r - tolerance)], dtype=np.uint8)
    hi = np.array([min(255, b + tolerance), min(255, g + tolerance), min(255, r + tolerance)], dtype=np.uint8)
    mask = cv2.inRange(img, lo, hi)
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n < 2:
        return _bbox_from_mask(mask)
    h_img, w_img = img.shape[:2]
    mid_x = w_img // 2
    top_frac = 0.6 * h_img
    best_idx = -1
    best_area = 0
    fallback_idx = -1
    fallback_area = 0
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < 100:
            continue
        if area > fallback_area:
            fallback_area = area
            fallback_idx = i
        cx, cy = centroids[i]
        if top_right_only and (cx <= mid_x or cy >= top_frac):
            continue
        if area > best_area:
            best_area = area
            best_idx = i
    idx = best_idx if best_idx >= 0 else fallback_idx
    if idx < 0:
        return _bbox_from_mask(mask)
    x1 = int(stats[idx, cv2.CC_STAT_LEFT])
    y1 = int(stats[idx, cv2.CC_STAT_TOP])
    w = int(stats[idx, cv2.CC_STAT_WIDTH])
    h = int(stats[idx, cv2.CC_STAT_HEIGHT])
    return (x1, y1, x1 + w, y1 + h)

def update_config_minimap_only(minimap_region: tuple):
    """仅用检测到的小地图区域覆盖 config.py 中 MINIMAP_REGION；WAVE_REGION 不变。"""
    path = ROOT_DIR / "config.py"
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"MINIMAP_REGION\s*=\s*\([^)]+\)\s*(?:#.*)?", f"MINIMAP_REGION = {minimap_region}  # (x1, y1, x2, y2)", text)
    path.write_text(text, encoding="utf-8")


def draw_label(img, text: str, pt: tuple, color: tuple, font_scale=0.5):
    (x, y) = pt
    # 文字阴影
    cv2.putText(img, text, (x + 1, y + 1), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), 2)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, 1)


def find_icon_health_ref(img, minimap_region):
    """
    在 minimap_readyloop.png 的小地图区域内匹配 icon_health.png
    （玩家在宝箱跟前时的位置参照），返回其在小地图中的位置。
    返回: (abs_x, abs_y, score, (bx, by, tw, th)) 或 None；框为整图绝对坐标。
    """
    template_path = ASSETS_DIR / "icon_health.png"
    if not template_path.exists():
        print(f"   [warn] Template not found: {template_path}")
        return None

    template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
    if template is None:
        print(f"   [warn] Failed to load template: {template_path}")
        return None

    h, w = template.shape
    crop = 4
    if h > 20 and w > 20:
        template = template[crop:-crop, crop:-crop]

    x1, y1, x2, y2 = minimap_region
    minimap_img = img[y1:y2, x1:x2]
    minimap_gray = cv2.cvtColor(minimap_img, cv2.COLOR_BGR2GRAY)
    res = cv2.matchTemplate(minimap_gray, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    thresh = MATCH_THRESHOLD
    if max_val < thresh:
        thresh = 0.50
    if max_val < thresh:
        thresh = 0.40
    if max_val < thresh:
        print(f"   [warn] minimap match {max_val:.3f} < {thresh}")
        return None

    rx, ry = max_loc
    tw, th = template.shape[1], template.shape[0]
    center_x = x1 + rx + tw // 2
    center_y = y1 + ry + th // 2
    bx, by = x1 + rx, y1 + ry
    return (center_x, center_y, max_val, (bx, by, tw, th))


# 固定分析的截图路径（无校准图时使用）
ANALYZE_IMAGE = ASSETS_DIR / "minimap_readyloop.png"


def run_calibrate(force_update: bool = False, dry_run: bool = False):
    """从 minimap_info.png 检测 #fbf23c 小地图区域，更新 config 中 MINIMAP_REGION；波次沿用 config。"""
    print(f"[*] 校准模式: 加载 {CALIBRATE_IMAGE}，小地图色 {MINIMAP_HEX}")
    if not CALIBRATE_IMAGE.exists():
        print(f"   [X] file not found: {CALIBRATE_IMAGE}")
        return False
    img = cv2.imread(str(CALIBRATE_IMAGE))
    if img is None:
        print(f"   [X] cannot read image: {CALIBRATE_IMAGE}")
        return False
    print(f"   [size] {img.shape[1]}x{img.shape[0]}")

    minimap = detect_color_region(img, MINIMAP_HEX, tolerance=MINIMAP_TOLERANCE)
    b, g, r = rgb_to_bgr(MINIMAP_HEX)
    tol = MINIMAP_TOLERANCE
    lo = np.array([max(0, b - tol), max(0, g - tol), max(0, r - tol)], dtype=np.uint8)
    hi = np.array([min(255, b + tol), min(255, g + tol), min(255, r + tol)], dtype=np.uint8)
    mask_y = cv2.inRange(img, lo, hi)
    cv2.imwrite(str(LOGS_DIR / "debug_calibrate_minimap.png"), mask_y)
    if not minimap:
        print(f"   [X] no {MINIMAP_HEX} minimap region")
        print("   请确认 minimap_info.png 已用 #fbf23c 纯色覆盖小地图并保存。")
        return False

    print(f"   [OK] MINIMAP_REGION: {minimap}")
    print(f"   [OK] WAVE_REGION:    (from config) {WAVE_REGION}")
    h_img, w_img = img.shape[:2]
    mx = (minimap[0] + minimap[2]) / 2
    my = (minimap[1] + minimap[3]) / 2
    in_top_right = mx > 0.5 * w_img and my < 0.5 * h_img
    if dry_run:
        print("   [dry-run] Config NOT updated.")
    elif not in_top_right and not force_update:
        print("   [warn] MINIMAP bbox not in top-right; detection may be wrong. Config NOT updated. (use --force to override)")
    else:
        update_config_minimap_only(minimap)
        print("   [OK] config.py MINIMAP_REGION updated")

    overlay = img.copy()
    GREEN = (0, 255, 0)
    MAGENTA = (255, 0, 255)
    x1, y1, x2, y2 = minimap
    cv2.rectangle(overlay, (x1, y1), (x2, y2), GREEN, 2)
    draw_label(overlay, "MINIMAP_REGION", (x1, max(0, y1 - 6)), GREEN)
    wx1, wy1, wx2, wy2 = WAVE_REGION
    cv2.rectangle(overlay, (wx1, wy1), (wx2, wy2), MAGENTA, 2)
    draw_label(overlay, "WAVE_REGION (config)", (wx1, max(0, wy1 - 6)), MAGENTA)

    out_path = LOGS_DIR / "verify_positions.png"
    cv2.imwrite(str(out_path), overlay)
    print(f"[OK] 已保存: {out_path}")
    print("   请打开图片，确认绿框与 #fbf23c 小地图覆盖区域一致；洋红框为 config 波次区域。")
    print("   Debug: logs/debug_calibrate_minimap.png")
    return True


def main():
    ap = argparse.ArgumentParser(description="Verify/calibrate UI positions.")
    ap.add_argument("--force", action="store_true", help="Always overwrite config with detected regions (calibrate mode).")
    ap.add_argument("--dry-run", action="store_true", help="Detect and save verify image only; do not update config.")
    args = ap.parse_args()
    if CALIBRATE_IMAGE.exists():
        if run_calibrate(force_update=args.force, dry_run=args.dry_run):
            return
        print("[*] Calibration failed, fallback to config verify mode")

    print(f"[*] 加载截图: {ANALYZE_IMAGE}")
    if not ANALYZE_IMAGE.exists():
        print(f"   [X] file not found: {ANALYZE_IMAGE}")
        return
    img = cv2.imread(str(ANALYZE_IMAGE))
    if img is None:
        print(f"   [X] cannot read image: {ANALYZE_IMAGE}")
        return
    overlay = img.copy()
    print(f"   [size] {img.shape[1]}x{img.shape[0]}")

    GREEN = (0, 255, 0)
    BLUE = (255, 0, 0)
    RED = (0, 0, 255)
    CYAN = (255, 255, 0)
    MAGENTA = (255, 0, 255)
    YELLOW_REF = (60, 242, 251)

    x1, y1, x2, y2 = MINIMAP_REGION
    cv2.rectangle(overlay, (x1, y1), (x2, y2), GREEN, 2)
    draw_label(overlay, "MINIMAP_REGION", (x1, y1 - 6), GREEN)

    cv2.circle(overlay, PLAYER_POS, 8, BLUE, 2)
    cv2.circle(overlay, PLAYER_POS, 3, BLUE, -1)
    draw_label(overlay, "PLAYER_POS", (PLAYER_POS[0] + 12, PLAYER_POS[1]), BLUE)

    cv2.circle(overlay, COMPASS_ICON_POS, 6, CYAN, 2)
    cv2.circle(overlay, COMPASS_ICON_POS, 2, CYAN, -1)
    draw_label(overlay, "COMPASS", (COMPASS_ICON_POS[0] + 12, COMPASS_ICON_POS[1]), CYAN)

    wx1, wy1, wx2, wy2 = WAVE_REGION
    cv2.rectangle(overlay, (wx1, wy1), (wx2, wy2), MAGENTA, 2)
    draw_label(overlay, "WAVE_REGION", (wx1, wy1 - 6), MAGENTA)

    cv2.circle(overlay, BOSS_DOOR_POS, 10, RED, 2)
    cv2.circle(overlay, BOSS_DOOR_POS, 4, RED, -1)
    draw_label(overlay, "BOSS_DOOR", (BOSS_DOOR_POS[0] + 14, BOSS_DOOR_POS[1]), RED)

    print("[*] 在 minimap_readyloop.png 小地图中查找 icon_health 参照物位置...")
    ref_result = find_icon_health_ref(img, MINIMAP_REGION)
    if ref_result:
        abs_x, abs_y, score, (bx, by, tw, th) = ref_result
        cv2.rectangle(overlay, (bx, by), (bx + tw, by + th), YELLOW_REF, 2)
        cv2.circle(overlay, (abs_x, abs_y), 6, YELLOW_REF, 2)
        cv2.circle(overlay, (abs_x, abs_y), 3, YELLOW_REF, -1)
        draw_label(overlay, f"icon_health (score={score:.2f})", (abs_x + 12, abs_y), YELLOW_REF)
        print(f"   [OK] icon_health at ({abs_x}, {abs_y}), score={score:.3f}")
    else:
        print("   [X] icon_health not found")

    out_path = LOGS_DIR / "verify_positions.png"
    cv2.imwrite(str(out_path), overlay)
    print(f"[OK] 已保存: {out_path}")
    print("   请打开图片，检查各标记是否对准对应 UI 元素。")
    print("   - 绿色框: 小地图区域 | 洋红框: 波次区域 | 蓝点: PLAYER_POS | 青点: COMPASS | 红点: BOSS_DOOR | 黄: icon_health")


if __name__ == "__main__":
    main()
