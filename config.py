from pathlib import Path

# Paths
ROOT_DIR = Path(__file__).parent
ASSETS_DIR = ROOT_DIR / "assets"
EVENTS_LIB_DIR = ASSETS_DIR / "events_library"
REFS_DIR = ROOT_DIR / "refs"
LOGS_DIR = ROOT_DIR / "logs"
UNKNOWN_EVENTS_DIR = LOGS_DIR / "unknown_events"

# Ensure dirs exist
LOGS_DIR.mkdir(exist_ok=True)
UNKNOWN_EVENTS_DIR.mkdir(exist_ok=True)
EVENTS_LIB_DIR.mkdir(exist_ok=True)

# Minmap & Navigation Constants (2560x1440)
MINIMAP_REGION = (2159, 91, 2523, 352)  # (x1, y1, x2, y2) - Calibrated from Yellow Box
PLAYER_POS = (2341, 221)                # Center of the new MINIMAP_REGION
COMPASS_ICON_POS = (2331, 226)          # Reference center for the icon
BOSS_DOOR_POS = (2464, 1426)            # Boss door icon center on minimap (verified)

# Wave Number Region (Updated based on yellow boxes in minimap_info.png)
WAVE_REGION = (1960, 80, 2100, 120)     # (x1, y1, x2, y2)
ETHER_REGION = (1960, 190, 2150, 260)    # 拉宽区域以支持 1,000+ 的数字

# Inventory panel region (approx, 2560x1440)
INVENTORY_REGION = (1600, 120, 2550, 1380)

# Event Scanning ROI (Left 4/5 of the screen, expanded vertically)
EVENT_SCAN_ROI = (50, 20, 2000, 1420)

# Vision Parameters
MATCH_THRESHOLD = 0.40                  # Lowered to handle low-contrast icons
EVENT_MATCH_THRESHOLD = 0.80
CENTER_TOLERANCE = 1  # pixels
BOSS_DOOR_TOLERANCE = 1  # Reduced tolerance for precise boss door positioning
CHEST_TOLERANCE = 1  # New tolerance for chest

# Navigation Limits
MAX_STEPS = 50

# Event Priority List (High to Low)
DESIRED_EVENTS = [
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
