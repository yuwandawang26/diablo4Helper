"""Dark Diablo-4 inspired QSS stylesheet."""

STYLESHEET = """
/* ── Base ── */
QMainWindow, QDialog {
    background-color: #09090f;
}

QWidget {
    background-color: #09090f;
    color: #d4c4a8;
    font-family: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
}

/* ── Group Boxes ── */
QGroupBox {
    background-color: #111120;
    border: 1px solid #2a2040;
    border-radius: 6px;
    margin-top: 18px;
    padding: 8px 6px 6px 6px;
    font-weight: bold;
    font-size: 12px;
    color: #c9a227;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 6px;
    color: #c9a227;
}

/* ── Buttons (default) ── */
QPushButton {
    background-color: #1a1828;
    color: #c8baa0;
    border: 1px solid #352a48;
    border-radius: 5px;
    padding: 7px 18px;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #231e3a;
    border-color: #c9a227;
    color: #f0d070;
}
QPushButton:pressed {
    background-color: #2e2218;
    border-color: #c9a227;
}
QPushButton:disabled {
    background-color: #121220;
    color: #3a3a4a;
    border-color: #1e1e30;
}

/* ── Start button ── */
QPushButton#startBtn {
    background-color: #0f2e14;
    border: 1px solid #236b28;
    color: #4fc254;
    font-size: 14px;
    font-weight: bold;
    padding: 9px 28px;
    border-radius: 5px;
    min-width: 140px;
}
QPushButton#startBtn:hover {
    background-color: #163d1c;
    border-color: #4fc254;
    color: #90ee90;
}
QPushButton#startBtn[running=true] {
    background-color: #2e0e0e;
    border-color: #8b1a1a;
    color: #ff6060;
}
QPushButton#startBtn[running=true]:hover {
    background-color: #3e1414;
    border-color: #cc2020;
    color: #ff8080;
}

/* ── Restart button ── */
QPushButton#restartBtn {
    background-color: #0e1e2e;
    border: 1px solid #1e4060;
    color: #5090d0;
    font-size: 14px;
    font-weight: bold;
    padding: 9px 28px;
    border-radius: 5px;
    min-width: 140px;
}
QPushButton#restartBtn:hover {
    background-color: #152538;
    border-color: #5090d0;
    color: #80b8f8;
}

/* ── Small action buttons ── */
QPushButton#uploadBtn {
    background-color: #0e1e2e;
    border: 1px solid #1e3050;
    color: #5080c0;
    padding: 3px 10px;
    font-size: 12px;
    border-radius: 3px;
}
QPushButton#uploadBtn:hover {
    border-color: #5090d0;
    color: #80b8f8;
}
QPushButton#addSkillBtn {
    background-color: #0f2214;
    border: 1px solid #1e5028;
    color: #4fc254;
    padding: 4px 12px;
    border-radius: 3px;
    font-size: 12px;
}
QPushButton#addSkillBtn:hover {
    border-color: #4fc254;
    color: #80ee80;
}
QPushButton#removeSkillBtn {
    background-color: #2e0e0e;
    border: 1px solid #6b1a1a;
    color: #d06060;
    padding: 4px 12px;
    border-radius: 3px;
    font-size: 12px;
}
QPushButton#removeSkillBtn:hover {
    border-color: #cc2020;
    color: #ff8080;
}
QPushButton#overlayBtn {
    background-color: #1a1428;
    border: 1px solid #3a2a60;
    color: #9070d0;
    font-size: 13px;
    font-weight: bold;
    padding: 9px 20px;
    border-radius: 5px;
    min-width: 120px;
}
QPushButton#overlayBtn:hover {
    border-color: #9070d0;
    color: #b898f0;
}
QPushButton#overlayBtn[active=true] {
    background-color: #1e1040;
    border-color: #9070d0;
    color: #c8a8ff;
}

/* ── Table Widget ── */
QTableWidget {
    background-color: #0b0b18;
    alternate-background-color: #0f0f1e;
    color: #d4c4a8;
    gridline-color: #1e1e30;
    border: 1px solid #2a2040;
    border-radius: 4px;
    selection-background-color: #231e3a;
    selection-color: #f0d070;
}
QTableWidget::item {
    padding: 4px 8px;
    border: none;
}
QTableWidget::item:selected {
    background-color: #231e3a;
    color: #f0d070;
}
QHeaderView {
    background-color: #0b0b18;
}
QHeaderView::section {
    background-color: #111124;
    color: #c9a227;
    border: none;
    border-right: 1px solid #2a2040;
    border-bottom: 1px solid #2a2040;
    padding: 6px 8px;
    font-weight: bold;
    font-size: 12px;
}

/* ── Scroll Bars ── */
QScrollBar:vertical {
    background-color: #0a0a14;
    width: 8px;
    border: none;
    margin: 0;
}
QScrollBar::handle:vertical {
    background-color: #2e2448;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background-color: #c9a227;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background-color: #0a0a14;
    height: 8px;
    border: none;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background-color: #2e2448;
    border-radius: 4px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #c9a227;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── Input Fields ── */
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {
    background-color: #0d0d1c;
    color: #d4c4a8;
    border: 1px solid #2e2448;
    border-radius: 3px;
    padding: 4px 8px;
    selection-background-color: #231e3a;
    selection-color: #f0d070;
    min-height: 22px;
}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus {
    border-color: #c9a227;
    outline: none;
}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button {
    background-color: #1a1828;
    border: none;
    width: 18px;
}
QDoubleSpinBox::up-arrow, QSpinBox::up-arrow {
    image: none;
    width: 0;
}
QDoubleSpinBox::down-arrow, QSpinBox::down-arrow {
    image: none;
    width: 0;
}
QComboBox::drop-down {
    background-color: #1a1828;
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    background-color: #111124;
    color: #d4c4a8;
    border: 1px solid #2a2040;
    selection-background-color: #231e3a;
    selection-color: #f0d070;
}

/* ── CheckBox ── */
QCheckBox {
    color: #d4c4a8;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #2e2448;
    border-radius: 3px;
    background-color: #0d0d1c;
}
QCheckBox::indicator:checked {
    background-color: #c9a227;
    border-color: #c9a227;
}
QCheckBox::indicator:hover {
    border-color: #c9a227;
}

/* ── Text / Log Area ── */
QTextEdit, QPlainTextEdit {
    background-color: #060610;
    color: #78c878;
    border: 1px solid #1a2a1a;
    border-radius: 3px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
    selection-background-color: #143014;
}

/* ── Labels ── */
QLabel {
    background: transparent;
    color: #d4c4a8;
}
QLabel#titleLabel {
    font-size: 22px;
    font-weight: bold;
    color: #c9a227;
    letter-spacing: 2px;
}
QLabel#subtitleLabel {
    font-size: 11px;
    color: #6a5c3c;
    letter-spacing: 1px;
}
QLabel#stateLabel {
    font-size: 12px;
    font-weight: bold;
    color: #888888;
    padding: 3px 8px;
    border: 1px solid #2a2040;
    border-radius: 3px;
    background-color: #111120;
}
QLabel#statusDot {
    font-size: 18px;
}
QLabel#hintLabel {
    font-size: 11px;
    color: #5a5068;
}
QLabel#categoryLabel {
    font-size: 12px;
    font-weight: bold;
    color: #c9a227;
    padding: 4px 0px;
}
QLabel#templateName {
    font-size: 12px;
    color: #c8baa0;
}
QLabel#templateOk {
    color: #4caf50;
    font-size: 13px;
    font-weight: bold;
}
QLabel#templateMissing {
    color: #e05050;
    font-size: 13px;
    font-weight: bold;
}
QLabel#variantCount {
    color: #9070d0;
    font-size: 11px;
}

/* ── Tab Widget ── */
QTabWidget::pane {
    background-color: #0d0d1c;
    border: 1px solid #2a2040;
    border-radius: 4px;
    top: -1px;
}
QTabBar::tab {
    background-color: #111120;
    color: #6a6278;
    border: 1px solid #2a2040;
    border-bottom: none;
    padding: 7px 18px;
    margin-right: 2px;
    border-radius: 4px 4px 0 0;
    font-size: 12px;
}
QTabBar::tab:selected {
    background-color: #0d0d1c;
    color: #c9a227;
    border-bottom: 1px solid #0d0d1c;
}
QTabBar::tab:hover:!selected {
    background-color: #171630;
    color: #d4c4a8;
}

/* ── Splitter ── */
QSplitter::handle {
    background-color: #2a2040;
    margin: 2px;
}
QSplitter::handle:horizontal {
    width: 1px;
}
QSplitter::handle:vertical {
    height: 1px;
}

/* ── Frames / Separators ── */
QFrame[frameShape="4"] { color: #2a2040; }
QFrame[frameShape="5"] { color: #2a2040; }

/* ── Tooltip ── */
QToolTip {
    background-color: #1a1428;
    color: #d4c4a8;
    border: 1px solid #3a2a60;
    padding: 4px 8px;
    border-radius: 3px;
    font-size: 12px;
}
"""

# State color map  (state_name -> hex color)
STATE_COLORS = {
    "IDLE":                    "#888888",
    "NAVIGATING_TO_CENTER":    "#5090d0",
    "SCANNING_FOR_EVENTS":     "#50c0d0",
    "SELECTING_EVENT":         "#70d0a0",
    "WAITING_FOR_WAVE_START":  "#d0a030",
    "COMBAT":                  "#e05050",
    "LOOTING":                 "#e09050",
    "NAVIGATING_TO_BOSS":      "#d060c0",
    "SELECTING_BOSS_ENTRY":    "#d060c0",
    "NAVIGATING_TO_BOSS_DOOR": "#d060c0",
    "INTERACTING_WITH_BOSS_DOOR": "#d060c0",
    "BOSS_FIGHT":              "#ff4040",
    "NAVIGATING_TO_CHEST":     "#c9a227",
    "INTERACTING_WITH_CHEST":  "#c9a227",
    "RETURNING_TO_TOWN":       "#9070d0",
    "ACTIVATING_NEXT_COMPASS": "#9070d0",
    "TELEPORTING_TO_INSTANCE": "#9070d0",
    "ENTERING_INSTANCE":       "#9070d0",
    "FINISHED":                "#4caf50",
    "DEAD":                    "#ff2020",
}

STATE_LABELS_CN = {
    "IDLE":                       "空闲",
    "NAVIGATING_TO_CENTER":       "返回中心",
    "SCANNING_FOR_EVENTS":        "扫描事件",
    "SELECTING_EVENT":            "选择事件",
    "WAITING_FOR_WAVE_START":     "等待波次",
    "COMBAT":                     "战斗中",
    "LOOTING":                    "拾取中",
    "NAVIGATING_TO_BOSS":         "前往BOSS",
    "SELECTING_BOSS_ENTRY":       "选择BOSS",
    "NAVIGATING_TO_BOSS_DOOR":    "前往BOSS门",
    "INTERACTING_WITH_BOSS_DOOR": "开启BOSS门",
    "BOSS_FIGHT":                 "BOSS战",
    "NAVIGATING_TO_CHEST":        "前往宝箱",
    "INTERACTING_WITH_CHEST":     "开启宝箱",
    "RETURNING_TO_TOWN":          "回城中",
    "ACTIVATING_NEXT_COMPASS":    "激活罗盘",
    "TELEPORTING_TO_INSTANCE":    "传送副本",
    "ENTERING_INSTANCE":          "进入副本",
    "FINISHED":                   "已完成",
    "DEAD":                       "角色死亡",
}
