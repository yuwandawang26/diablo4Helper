"""User-editable bot preferences (separate from calibration.json).

Loaded once at startup and re-read on every call to load_settings() so
hot-reload is possible without restarting the bot.
"""
import json
import random
from pathlib import Path

SETTINGS_PATH = Path(__file__).parent.parent / "config" / "settings.json"

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_SETTINGS: dict = {
    # Which chest(s) to open in the boss room (ordered list).
    # Empty list → open nearest chest (original hover-scan behaviour).
    # Allowed values: "equipment" | "material" | "gold"
    # Opening order is always fixed: equipment → material → gold
    # regardless of list order supplied here.
    "chest_selection": [],

    # Maximum number of compass runs.  0 = unlimited.
    "max_runs": 0,

    # Movement key scheme.
    # "arrows" → Up / Down / Left / Right  (default, works without re-binding)
    # "wasd"   → W / A / S / D
    "move_keys": "arrows",

    # List of tribute-category strings that the bot should prefer.
    # Empty list → fall back to the static DESIRED_EVENTS priority ranking.
    # Allowed values: "混沌贡品" | "魔裔类" | "以太物质类" | "魂塔类"
    "tribute_categories": [],
}

# Maps logical direction → keyboard key for each scheme
MOVE_KEY_MAPS: dict[str, dict[str, str]] = {
    "arrows": {"up": "up",   "down": "down",  "left": "left",  "right": "right"},
    "wasd":   {"up": "w",    "down": "s",     "left": "a",     "right": "d"},
}


def resolve_direction(direction: str, move_keys: str = "arrows") -> str:
    """Return the actual keyboard key for *direction* under *move_keys* scheme."""
    return MOVE_KEY_MAPS.get(move_keys, MOVE_KEY_MAPS["arrows"]).get(
        direction, direction
    )

# Fixed opening order for multi-chest runs — never changes.
CHEST_OPEN_ORDER: list[str] = ["equipment", "material", "gold"]

# Hover-tooltip OCR keywords that identify each chest type.
# The bot ORs these together: if ANY keyword is found in the OCR text → match.
# Both CN and EN variants are included so the bot works regardless of game language.
CHEST_TYPE_KEYWORDS: dict[str, list[str]] = {
    "equipment": [
        "装备战利品", "装备宝箱", "强效装备",
        "Equipment Spoils", "Greater Equipment", "Equipment",
    ],
    "material": [
        "工艺材料", "材料战利品", "材料宝箱", "强效材料",
        "Crafting Spoils", "Greater Crafting", "Crafting", "Material",
    ],
    "gold": [
        "金币战利品", "金币宝箱", "强效金币",
        "Gold Spoils", "Greater Gold", "Gold Spoils",
    ],
}

CHEST_LABEL_CN: dict[str, str] = {
    "equipment": "装备箱",
    "material":  "材料箱",
    "gold":      "金币箱",
}


def identify_chest_type(ocr_text: str) -> str | None:
    """Return chest type key if *ocr_text* matches any known keyword, else None."""
    text_lower = ocr_text.lower()
    for chest_type, keywords in CHEST_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                return chest_type
    return None

# ── Tribute-category → event-name mapping ────────────────────────────────────
# Each category lists every matching event name (CN + EN) so the bot can
# compare against whatever name fuzzy_match_event returned.
TRIBUTE_CATEGORY_EVENTS: dict[str, list[str]] = {
    "混沌贡品": [
        "混沌供品",
        "Hellborne Offerings", "Chaos Offering",
    ],
    "魔裔类": [
        "蒙召魔裔", "伏击的魔裔", "贵族魔裔", "巨型凶魔",
        "涌动魔裔", "凶魔军团", "高贵魔潮", "高贵凶魔", "高贵魔裔",
        "尾行恶魔",
        "Summons of the Hellborne", "Hellborne Ambush", "Noble Hellborne",
        "Elite Fiends", "Surging Hellborne", "Fiend Hordes",
        "Noble Hellhorde", "Noble Fiend", "Stalking Devils",
    ],
    "以太物质类": [
        "以太地精", "肿胀物质", "集结物质", "充盈物质",
        "锚定物质", "凶恶物质", "迸燃物质",
        "Ether Goblins", "Swelling Aether", "Massing Aether",
        "Filling Aether", "Anchored Aether", "Vicious Aether", "Bursting Aether",
    ],
    "地狱火类": [
        "燃烧的火雨", "地狱火焰", "烈焰风暴", "炽热涌浪",
        "Burning Rain", "Hellfire Surge", "Blazing Storm", "Scorching Tide",
    ],
    "魂塔类": [
        "囤宝之塔", "珍贵之塔", "汲血尖塔", "饥饿尖塔", "崛起之塔",
        "Hoard of Wealth", "Precious Spire", "Bloodspire",
        "Hungry Spire", "Rising Spire",
    ],
}

# Tribute category icon → template name (user uploads these via the UI template tab)
# Order defines display order in the UI.
TRIBUTE_ICON_TEMPLATES: dict[str, str] = {
    "魔裔类":     "tribute_hellborne",   # 魔裔 icon
    "以太物质类": "tribute_ether",        # 以太凶魔 icon
    "地狱火类":   "tribute_hellfire",     # 地狱火 icon
    "混沌贡品":   "tribute_chaos",        # 混沌贡品 icon
    "魂塔类":     "tribute_soultower",    # 魂塔 icon
}

# Chest-type → template-name mapping (templates must be uploaded by the user)
CHEST_TEMPLATE_NAMES: dict[str, str] = {
    "equipment": "chest_equip",   # 装备箱
    "material":  "chest_material", # 材料箱
    "gold":      "chest_gold",    # 金币箱
}

# ── I/O helpers ───────────────────────────────────────────────────────────────

def load_settings() -> dict:
    """Load settings.json; missing keys are filled from DEFAULT_SETTINGS.

    Also handles the old ``chest_preference`` key (single string) that was used
    in earlier versions, converting it to the new ``chest_selection`` list.
    """
    try:
        if SETTINGS_PATH.exists():
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            result = {**DEFAULT_SETTINGS, **data}
            # Backward-compat: migrate old single-value key
            if "chest_preference" in result and "chest_selection" not in data:
                old = result.pop("chest_preference", "any")
                if old and old != "any":
                    result["chest_selection"] = [old]
                else:
                    result["chest_selection"] = []
            return result
    except Exception as e:
        print(f"[settings] 加载失败: {e}")
    return dict(DEFAULT_SETTINGS)


def save_settings(data: dict):
    SETTINGS_PATH.parent.mkdir(exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Selection logic ───────────────────────────────────────────────────────────

def pick_tribute(found_events: list[dict], settings: dict,
                 desired_events: list[str]) -> dict | None:
    """Choose the best tribute from *found_events* according to user settings.

    Algorithm
    ---------
    1. If any tribute_categories are enabled, collect all found events whose
       name belongs to at least one checked category (priority pool).
    2. If the priority pool is non-empty → pick the one with the best rank in
       *desired_events* (ties broken randomly).
    3. If the priority pool is empty (no checked-category match on screen) →
       fall back to the normal *desired_events* ranking across all found events.
    4. If *tribute_categories* is empty → use normal ranking (original behaviour).
    """
    if not found_events:
        return None

    categories = settings.get("tribute_categories", [])

    if categories:
        # Build a set of all event names that belong to a checked category
        wanted: set[str] = set()
        for cat in categories:
            wanted.update(TRIBUTE_CATEGORY_EVENTS.get(cat, []))

        # Support both OCR-found events (matched by name) and icon-found events
        # (matched by category field set during template detection).
        priority_pool = [
            ev for ev in found_events
            if ev["name"] in wanted
            or ev.get("category") in categories
        ]

        if priority_pool:
            # Among priority matches, pick highest-ranked; random among ties
            def _rank(ev):
                try:
                    return desired_events.index(ev["name"])
                except ValueError:
                    return 9999
            best_rank = min(_rank(ev) for ev in priority_pool)
            top = [ev for ev in priority_pool if _rank(ev) == best_rank]
            chosen = random.choice(top)
            print(
                f"[settings] 贡品优先池命中 {len(priority_pool)} 个: "
                f"{[e['name'] for e in priority_pool]} → 选择 {chosen['name']!r}"
            )
            return chosen

        # No priority match — fall through to normal ranking
        print(
            f"[settings] 贡品优先类别 {categories} 无匹配，"
            f"回落到默认优先列表"
        )

    # Normal ranking (original behaviour)
    def _rank_default(ev):
        try:
            return desired_events.index(ev["name"])
        except ValueError:
            return 9999

    found_events_sorted = sorted(found_events, key=_rank_default)
    return found_events_sorted[0]
