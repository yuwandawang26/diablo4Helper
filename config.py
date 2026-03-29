import json
from pathlib import Path

# Paths
ROOT_DIR = Path(__file__).parent
ASSETS_DIR = ROOT_DIR / "assets"
TRANSLATIONS_PATH = ASSETS_DIR / "translations.json"
EVENTS_LIB_DIR = ASSETS_DIR / "events_library"
REFS_DIR = ROOT_DIR / "refs"
LOGS_DIR = ROOT_DIR / "logs"
UNKNOWN_EVENTS_DIR = LOGS_DIR / "unknown_events"
CALIBRATION_PATH = ROOT_DIR / "config" / "calibration.json"

# Ensure dirs exist
LOGS_DIR.mkdir(exist_ok=True)
UNKNOWN_EVENTS_DIR.mkdir(exist_ok=True)
EVENTS_LIB_DIR.mkdir(exist_ok=True)

# ── Default constants (2560×1440 reference) ───────────────────────────────────
# All values below can be overridden via config/calibration.json
MINIMAP_REGION = (2159, 91, 2523, 352)  # (x1, y1, x2, y2) minimap bounding box
PLAYER_POS = (2341, 221)                # Pixel position of player icon centre in minimap
COMPASS_ICON_POS = (2331, 226)
BOSS_DOOR_POS = (2464, 1426)

# Navigation centre offset: (dx, dy) the event icon should sit relative to
# PLAYER_POS when the player is considered "at centre".  Tune this if the bot
# stops too far north/south of the arena centre.
NAV_CENTER_DX = 0
NAV_CENTER_DY = 0

# ── Per-type chest navigation offsets ────────────────────────────────────────
# Each is the (DX, DY) where the blood-well (chest_marker / icon_health) icon
# sits relative to PLAYER_POS when standing at that specific chest's position.
# The generic CHEST_NAV_DX/DY is kept as the "any" fallback.
# Calibrate: stand in front of each chest, use "标记…" button in calibration tab.
CHEST_NAV_DX = 12.0
CHEST_NAV_DY = 111.0

EQUIP_CHEST_NAV_DX   = 12.0    # 装备箱
EQUIP_CHEST_NAV_DY   = 111.0
EQUIP_CHEST_SCAN_REGION   = (900, 200, 1660, 900)   # screen area to search for chest

MATERIAL_CHEST_NAV_DX = 12.0   # 材料箱
MATERIAL_CHEST_NAV_DY = 111.0
MATERIAL_CHEST_SCAN_REGION = (900, 200, 1660, 900)

GOLD_CHEST_NAV_DX    = 12.0    # 金币箱
GOLD_CHEST_NAV_DY    = 111.0
GOLD_CHEST_SCAN_REGION    = (900, 200, 1660, 900)

# Boss-door approach offset: where bossdoor icon should sit relative to
# PLAYER_POS when standing at the door interaction point.
BOSS_DOOR_NAV_DX = -3.0
BOSS_DOOR_NAV_DY = -6.0

# Wave Number Region
WAVE_REGION = (1960, 80, 2100, 120)
ETHER_REGION = (1960, 190, 2150, 260)

# Compass Instance HUD region: the icon+wave-counter cluster in the top-right corner.
# Only visible when the player is inside a compass instance.
# Deliberately wider than WAVE_REGION so both the icon box and "波次" label are covered.
INSTANCE_HUD_REGION = (1680, 20, 2150, 140)

# Inventory panel region (approx, 2560x1440)
INVENTORY_REGION = (1600, 120, 2550, 1380)

# Event Scanning ROI — full-screen area scanned for event text choices
EVENT_SCAN_ROI = (50, 20, 2000, 1420)

# Death screen scan region — lower-centre band where "在存档点重生" button appears
DEATH_SCAN_REGION = (640, 792, 1920, 1296)

# Modal dialog scan region — area searched for "接受"/"Accept" button text
MODAL_SCAN_REGION = (400, 600, 2160, 1200)

# Quest-tracker region: the right-side panel that shows current quest objectives
# such as "选择炼狱供奉" / "消灭怪物" / "已完成地下城".
# The panel starts well below the minimap (≈y=420) and extends to ≈y=810.
# If OCR reads stray numbers (e.g. "9", "4"), the region is overlapping the
# wave-counter / timer rows — move it downward via the calibration tool.
QUEST_TRACKER_REGION = (1850, 420, 2540, 810)

# Screen region where "议会大门" interaction prompt / bossdoor text is searched.
# Covers the upper half of the screen where door prompts typically appear.
BOSS_DOOR_SCAN_REGION = (0, 100, 2560, 900)

# Vision Parameters
MATCH_THRESHOLD = 0.40
EVENT_MATCH_THRESHOLD = 0.80
CENTER_TOLERANCE = 8
BOSS_DOOR_TOLERANCE = 8
CHEST_TOLERANCE = 8

# Navigation Limits
MAX_STEPS = 50

# ── Load calibration overrides ────────────────────────────────────────────────
def _load_calibration():
    global MINIMAP_REGION, PLAYER_POS, BOSS_DOOR_POS, NAV_CENTER_DX, NAV_CENTER_DY
    global CHEST_NAV_DX, CHEST_NAV_DY, BOSS_DOOR_NAV_DX, BOSS_DOOR_NAV_DY
    global EQUIP_CHEST_NAV_DX, EQUIP_CHEST_NAV_DY, EQUIP_CHEST_SCAN_REGION
    global MATERIAL_CHEST_NAV_DX, MATERIAL_CHEST_NAV_DY, MATERIAL_CHEST_SCAN_REGION
    global GOLD_CHEST_NAV_DX, GOLD_CHEST_NAV_DY, GOLD_CHEST_SCAN_REGION
    global WAVE_REGION, ETHER_REGION, INVENTORY_REGION, EVENT_SCAN_ROI
    global INSTANCE_HUD_REGION, DEATH_SCAN_REGION, MODAL_SCAN_REGION, QUEST_TRACKER_REGION
    global CENTER_TOLERANCE, BOSS_DOOR_TOLERANCE, CHEST_TOLERANCE, MATCH_THRESHOLD
    global BOSS_DOOR_SCAN_REGION
    if not CALIBRATION_PATH.exists():
        return
    try:
        with open(CALIBRATION_PATH, "r", encoding="utf-8") as f:
            cal = json.load(f)
        if "minimap_region" in cal:
            MINIMAP_REGION = tuple(cal["minimap_region"])
        if "player_pos" in cal:
            PLAYER_POS = tuple(cal["player_pos"])
        if "boss_door_pos" in cal:
            BOSS_DOOR_POS = tuple(cal["boss_door_pos"])
        if "nav_center_dx" in cal:
            NAV_CENTER_DX = cal["nav_center_dx"]
        if "nav_center_dy" in cal:
            NAV_CENTER_DY = cal["nav_center_dy"]
        if "match_threshold" in cal:
            MATCH_THRESHOLD = cal["match_threshold"]
        if "center_tolerance" in cal:
            CENTER_TOLERANCE = cal["center_tolerance"]
        if "instance_hud_region" in cal:
            INSTANCE_HUD_REGION = tuple(cal["instance_hud_region"])
        if "death_scan_region" in cal:
            DEATH_SCAN_REGION = tuple(cal["death_scan_region"])
        if "modal_scan_region" in cal:
            MODAL_SCAN_REGION = tuple(cal["modal_scan_region"])
        if "event_scan_roi" in cal:
            EVENT_SCAN_ROI = tuple(cal["event_scan_roi"])
        if "wave_region" in cal:
            WAVE_REGION = tuple(cal["wave_region"])
        if "ether_region" in cal:
            ETHER_REGION = tuple(cal["ether_region"])
        if "inventory_region" in cal:
            INVENTORY_REGION = tuple(cal["inventory_region"])
        if "quest_tracker_region" in cal:
            QUEST_TRACKER_REGION = tuple(cal["quest_tracker_region"])
        if "boss_door_scan_region" in cal:
            BOSS_DOOR_SCAN_REGION = tuple(cal["boss_door_scan_region"])
        if "chest_nav_dx" in cal:
            CHEST_NAV_DX = float(cal["chest_nav_dx"])
        if "chest_nav_dy" in cal:
            CHEST_NAV_DY = float(cal["chest_nav_dy"])
        if "boss_door_nav_dx" in cal:
            BOSS_DOOR_NAV_DX = float(cal["boss_door_nav_dx"])
        if "boss_door_nav_dy" in cal:
            BOSS_DOOR_NAV_DY = float(cal["boss_door_nav_dy"])
        # Per-type chest nav offsets
        if "equip_chest_nav_dx" in cal:
            EQUIP_CHEST_NAV_DX = float(cal["equip_chest_nav_dx"])
        if "equip_chest_nav_dy" in cal:
            EQUIP_CHEST_NAV_DY = float(cal["equip_chest_nav_dy"])
        if "equip_chest_scan_region" in cal:
            EQUIP_CHEST_SCAN_REGION = tuple(cal["equip_chest_scan_region"])
        if "material_chest_nav_dx" in cal:
            MATERIAL_CHEST_NAV_DX = float(cal["material_chest_nav_dx"])
        if "material_chest_nav_dy" in cal:
            MATERIAL_CHEST_NAV_DY = float(cal["material_chest_nav_dy"])
        if "material_chest_scan_region" in cal:
            MATERIAL_CHEST_SCAN_REGION = tuple(cal["material_chest_scan_region"])
        if "gold_chest_nav_dx" in cal:
            GOLD_CHEST_NAV_DX = float(cal["gold_chest_nav_dx"])
        if "gold_chest_nav_dy" in cal:
            GOLD_CHEST_NAV_DY = float(cal["gold_chest_nav_dy"])
        if "gold_chest_scan_region" in cal:
            GOLD_CHEST_SCAN_REGION = tuple(cal["gold_chest_scan_region"])
    except Exception as e:
        print(f"[CONFIG] calibration.json 加载失败: {e}")

_load_calibration()

# Event Priority List (High to Low) - Chinese
DESIRED_EVENTS_CN = [
    '混沌供品',
    '以太地精',
    '尾行恶魔',
    '肿胀物质',
    '蒙召魔裔',
    '伏击的魔裔',
    '贵族魔裔',
    '巨型凶魔',
    '涌动魔裔',
    '凶魔军团',
    '集结物质',
    '囤宝之塔',
    '充盈物质',
    '锚定物质',
    '凶恶物质',
    '珍贵之塔',
    '高贵魔潮',
    '高贵凶魔',
    '高贵魔裔',
    '汲血尖塔',
    '迸燃物质',
    '饥饿尖塔',
    '崛起之塔',
    '燃烧的火雨'
]

# Event Priority List (High to Low) - English
DESIRED_EVENTS_EN = [
    'Hellborne Offerings',
    'Ether Goblins',
    'Stalking Devils',
    'Swelling Aether',
    'Summons of the Hellborne',
    'Hellborne Ambush',
    'Noble Hellborne',
    'Elite Fiends',
    'Surging Hellborne',
    'Fiend Hordes',
    'Massing Aether',
    'Hoard of Wealth',
    'Filling Aether',
    'Anchored Aether',
    'Vicious Aether',
    'Precious Spire',
    'Noble Hellhorde',
    'Noble Fiend',
    'Noble Hellborne',
    'Bloodspire',
    'Bursting Aether',
    'Hungry Spire',
    'Rising Spire',
    'Burning Rain'
]
