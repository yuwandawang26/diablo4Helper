"""Main control window for D4 Auto.

Layout
------
  ┌─────────────────────────────────────────────────────────────────┐
  │  ⚔ D4 AUTO   [状态]  [●运行中]                  [语言 CN/EN] [×] │
  ├───────────────────────┬─────────────────────────────────────────┤
  │  ⚔ 技能配置            │  [Templates | Log] tabs                 │
  │  table: key/interval  │                                         │
  │  [+] [-] [保存]        │                                         │
  ├───────────────────────┴─────────────────────────────────────────┤
  │   [▶ 开始 F1]   [↺ 重启 F3]   [🪟 浮窗 F4]    提示文字          │
  └─────────────────────────────────────────────────────────────────┘
"""

import json
import shutil
from pathlib import Path
from datetime import datetime

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QDoubleSpinBox, QSpinBox, QCheckBox, QTabWidget, QTextEdit, QScrollArea,
    QFileDialog, QMessageBox, QComboBox, QFrame, QSizePolicy,
    QAbstractItemView, QLineEdit, QFormLayout, QGroupBox, QRadioButton,
)
from PyQt5.QtCore import Qt, pyqtSlot, pyqtSignal, QTimer, QSize
from PyQt5.QtGui import QFont, QTextCursor, QIcon, QPixmap, QColor

from ui.styles import STYLESHEET, STATE_COLORS, STATE_LABELS_CN
from ui.overlay import OverlayWindow
from ui.bot_thread import BotThread
from ui.region_picker import RegionPickerWindow
from core.settings_manager import (
    load_settings, save_settings,
    TRIBUTE_CATEGORY_EVENTS, CHEST_TEMPLATE_NAMES,
)

# ── Config paths ──────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent.parent
ASSETS_DIR = _HERE / "assets"
SKILLS_PATH = _HERE / "config" / "skills.json"
CALIBRATION_PATH = _HERE / "config" / "calibration.json"

# ── Template catalogue ────────────────────────────────────────────────────────
# All templates support multi-variant: stem_v2.png, stem_v3.png…
# The vision system tries ALL variants and picks the highest-confidence match.
# Entry: (display_name, filename, description)
TEMPLATE_CATALOGUE = [
    # --- 小地图导航 ---
    ("小地图 · 普通事件",  "minimap_bonehand.png",    "小地图骷髅手图标 · 不同亮度/背景下有差异"),
    ("小地图 · 混沌事件",  "minimap_extrahand.png",   "混沌供品事件图标 · 可上传多个版本"),
    ("小地图 · BOSS区域",  "minimap_bosshand.png",    "BOSS入口区域图标 · 可上传多个版本"),
    # --- 罗盘 ---
    ("罗盘图标",           "icon_compass.png",        "背包中的罗盘图标 · 强烈建议上传多变种"),
    ("罗盘传送门",         "icon_compassdoor.png",    "传送门/副本入口图标"),
    ("弹窗 · 使用钥匙",   "modal_usekey.png",        "使用罗盘弹窗 · 游戏更新后建议重新截图"),
    ("弹窗 · 传送确认",   "modal_tp_compass.png",    "传送副本弹窗 · 游戏更新后建议重新截图"),
    ("副本起始标记",       "icon_start.png",          "进入副本后的起点图标"),
    # --- BOSS门 ---
    ("BOSS门图标",         "icon_bossdoor.png",       "BOSS房门图标 · 高亮/普通两态建议各上传"),
    ("BOSS门（合并）",     "icon_bossdoor_merge.png", "BOSS门合并后的图标 · 可上传多个角度"),
    # --- 宝箱 ---
    ("血井（宝箱参照）",   "icon_health.png",         "宝箱前玩家参照 · 血井图标 · 多变种提升定位精度"),
    ("宝箱悬停提示",       "tip_bosschest.png",       "宝箱悬停提示 · 不同状态下外观有差异"),
    ("Boss宝箱 · 装备箱",  "chest_equip.png",         "装备战利品宝箱外观 · 上传后在「通用设置」可指定优先开此类型"),
    ("Boss宝箱 · 材料箱",  "chest_material.png",      "材料/工艺战利品宝箱外观 · 上传后在「通用设置」可指定优先开此类型"),
    ("Boss宝箱 · 金币箱",  "chest_gold.png",          "金币战利品宝箱外观 · 上传后在「通用设置」可指定优先开此类型"),
    ("背包钥匙栏图标",     "icon_key.png",            "背包界面钥匙分类图标"),
    ("背包键标签",         "backpack_key.png",        "背包键标签备用图标"),
    # --- 副本检测 ---
    ("副本 HUD 图标",      "hud_instance.png",        "右上角副本波次框截图（仅在罗盘副本内可见）· 上传后脚本启动时优先用此图标判断是否已在副本中，不上传则回退到 OCR"),
    # --- 死亡 ---
    ("死亡弹窗",           "modal_death.png",         "死亡界面截图（含复活按钮）· 上传后用模板匹配检测，更快更准；不上传则回退到 OCR 文字识别"),
    # --- 拾取 ---
    ("恢复卷轴标签",       "tip_huifu.png",           "恢复卷轴 tooltip · 不同物品有色差"),
    ("太古装备标签",       "icon_taigu_tag.png",      "太古品质装备标签 · 不同部位有差异"),
    ("混沌事件（全屏）",   "hundun_event.png",        "全屏混沌事件模板 · 可上传多种出现状态"),
    # --- 贡品类别图标（用于快速模板匹配，替代OCR）---
    ("贡品图标 · 魔裔",   "tribute_hellborne.png",   "魔裔类贡品图标 · 上传后优先使用模板匹配选贡品，比OCR更快更准"),
    ("贡品图标 · 以太",   "tribute_ether.png",       "以太物质类贡品图标 · 上传后启用图标识别"),
    ("贡品图标 · 地狱火", "tribute_hellfire.png",    "地狱火类贡品图标 · 上传后启用图标识别"),
    ("贡品图标 · 混沌",   "tribute_chaos.png",       "混沌贡品图标 · 上传后启用图标识别"),
    ("贡品图标 · 魂塔",   "tribute_soultower.png",   "魂塔类贡品图标 · 上传后启用图标识别"),
]

MAX_LOG_LINES = 1000


# ── Key capture widget ────────────────────────────────────────────────────────

class KeyCaptureEdit(QLineEdit):
    """Single-key capture: click once to enter capture mode, press a key."""

    _CAPTURE_STYLE = (
        "background-color: #1a1000; border: 1px solid #c9a227; "
        "color: #f0d070; padding: 3px 6px; border-radius: 3px; font-size: 12px;"
    )
    _NORMAL_STYLE = (
        "background-color: #0d0d1c; border: 1px solid #2e2448; "
        "color: #d4c4a8; padding: 3px 6px; border-radius: 3px; font-size: 12px;"
    )

    def __init__(self, key_text="", parent=None):
        super().__init__(parent)
        self._capturing = False
        self.setText(key_text)
        self.setReadOnly(True)
        self.setFixedWidth(52)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(self._NORMAL_STYLE)
        self.setToolTip("点击后按下要绑定的按键")

    def mousePressEvent(self, event):
        self._capturing = True
        self.setStyleSheet(self._CAPTURE_STYLE)
        self.setText("…")
        self.setFocus()

    def keyPressEvent(self, event):
        if not self._capturing:
            return
        key = event.text()
        if not key:
            # Handle special keys
            mapping = {
                Qt.Key_F1: "f1", Qt.Key_F2: "f2", Qt.Key_F3: "f3",
                Qt.Key_F4: "f4", Qt.Key_F5: "f5", Qt.Key_F6: "f6",
                Qt.Key_F7: "f7", Qt.Key_F8: "f8", Qt.Key_F9: "f9",
                Qt.Key_F10: "f10", Qt.Key_F11: "f11", Qt.Key_F12: "f12",
                Qt.Key_Space: "space", Qt.Key_Return: "enter",
                Qt.Key_Escape: None,
            }
            result = mapping.get(event.key())
            if result is None:
                # Escape → cancel capture
                self._capturing = False
                self.setStyleSheet(self._NORMAL_STYLE)
                return
            if result:
                key = result
        self.setText(key.lower())
        self._capturing = False
        self.setStyleSheet(self._NORMAL_STYLE)


# ── Scroll-insensitive spinboxes ──────────────────────────────────────────────
# Only respond to mouse wheel when the widget has explicit keyboard focus
# (i.e. the user clicked into it).  This prevents accidental value changes
# while scrolling through the calibration tab.

class _NoScrollSpin(QSpinBox):
    """SpinBox that never changes value on mouse-wheel scroll."""
    def wheelEvent(self, event):
        event.ignore()

class _NoScrollDSpin(QDoubleSpinBox):
    """DoubleSpinBox that never changes value on mouse-wheel scroll."""
    def wheelEvent(self, event):
        event.ignore()


# ── Template row widget ───────────────────────────────────────────────────────

class TemplateRow(QWidget):
    """One row in the template list.

    Every template supports multi-variant uploads (max 10 total).
    - Primary file: <stem>.png  (e.g. icon_compass.png)
    - Extra variants: <stem>_v2.png, <stem>_v3.png, …  up to _v10.png

    Header row is always visible. Click the expand button (▶ N变种) to reveal
    a collapsible panel listing all variants with individual delete buttons.

    Two ways to add variants:
    - 📤 上传文件: traditional file-picker dialog
    - 📷 框选截图: hide app, take live screenshot, drag a region, save as variant
    """

    MAX_VARIANTS = 10

    def __init__(self, display_name: str, filename: str, description: str,
                 parent=None):
        super().__init__(parent)
        self._filename  = filename
        self._stem      = Path(filename).stem
        self._disp_name = display_name
        self._expanded  = False
        self._overlay_visible_before = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header row ───────────────────────────────────────────────────────
        header_widget = QWidget()
        header_widget.setObjectName("templateRowHeader")
        header = QHBoxLayout(header_widget)
        header.setContentsMargins(4, 3, 4, 3)
        header.setSpacing(6)

        self._status_lbl = QLabel("?")
        self._status_lbl.setFixedWidth(20)
        self._status_lbl.setAlignment(Qt.AlignCenter)
        header.addWidget(self._status_lbl)

        self._thumb = QLabel()
        self._thumb.setFixedSize(28, 28)
        self._thumb.setAlignment(Qt.AlignCenter)
        self._thumb.setStyleSheet(
            "background:#0a0a14; border:1px solid #2a2040; border-radius:2px;"
        )
        header.addWidget(self._thumb)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        name_lbl = QLabel(display_name)
        name_lbl.setObjectName("templateName")
        desc_lbl = QLabel(description)
        desc_lbl.setStyleSheet("color:#5a5468; font-size:11px; background:transparent;")
        text_col.addWidget(name_lbl)
        text_col.addWidget(desc_lbl)
        header.addLayout(text_col, stretch=1)

        self._variant_lbl = QLabel("")
        self._variant_lbl.setMinimumWidth(68)
        self._variant_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header.addWidget(self._variant_lbl)

        self._capture_btn = QPushButton("📷 框选截图")
        self._capture_btn.setObjectName("uploadBtn")
        self._capture_btn.setFixedWidth(90)
        self._capture_btn.setToolTip(
            "隐藏界面 → 截取当前游戏画面 → 拖动金框选择区域 → Enter 确认\n"
            f"自动保存为新变种（最多 {self.MAX_VARIANTS} 个）"
        )
        self._capture_btn.clicked.connect(self._capture_from_screen)
        header.addWidget(self._capture_btn)

        self._upload_btn = QPushButton("📤 上传")
        self._upload_btn.setObjectName("uploadBtn")
        self._upload_btn.setFixedWidth(72)
        self._upload_btn.setToolTip("选择本地图片文件上传为模板或追加为新变种")
        self._upload_btn.clicked.connect(self._upload)
        header.addWidget(self._upload_btn)

        # Expand / collapse toggle button
        self._expand_btn = QPushButton("▶")
        self._expand_btn.setFixedWidth(28)
        self._expand_btn.setToolTip("展开/折叠变种列表")
        self._expand_btn.setStyleSheet(
            "QPushButton { background:transparent; border:none; color:#5a5068; "
            "font-size:13px; font-weight:bold; padding:0; }"
            "QPushButton:hover { color:#c9a227; }"
        )
        self._expand_btn.clicked.connect(self._toggle_expand)
        header.addWidget(self._expand_btn)

        outer.addWidget(header_widget)

        # ── Variant panel (collapsible) ──────────────────────────────────────
        self._variant_panel = QFrame()
        self._variant_panel.setStyleSheet(
            "QFrame { background: rgba(6,6,16,200); "
            "border: 1px solid #1a1830; border-radius: 3px; }"
        )
        self._variant_panel_layout = QVBoxLayout(self._variant_panel)
        self._variant_panel_layout.setContentsMargins(8, 6, 8, 6)
        self._variant_panel_layout.setSpacing(4)
        self._variant_panel.hide()
        outer.addWidget(self._variant_panel)

        self.refresh()

    # ── helpers ──────────────────────────────────────────────────────────────

    def _all_existing(self) -> list:
        primary = ASSETS_DIR / self._filename
        candidates = [primary] + sorted(ASSETS_DIR.glob(f"{self._stem}_v*.png"))
        return [p for p in candidates if p.exists()]

    def _next_dest_name(self) -> str:
        primary = ASSETS_DIR / self._filename
        if not primary.exists():
            return self._filename
        existing_variants = sorted(ASSETS_DIR.glob(f"{self._stem}_v*.png"))
        next_idx = len(existing_variants) + 2
        return f"{self._stem}_v{next_idx}.png"

    # ── refresh ──────────────────────────────────────────────────────────────

    def refresh(self):
        existing = self._all_existing()
        count = len(existing)
        at_max = count >= self.MAX_VARIANTS

        if count == 0:
            self._status_lbl.setText("✗")
            self._status_lbl.setStyleSheet("color:#e05050; font-weight:bold;")
            self._variant_lbl.setText("未上传")
            self._variant_lbl.setStyleSheet(
                "color:#5a3a3a; font-size:11px; background:transparent;"
            )
            self._expand_btn.hide()
        else:
            self._status_lbl.setText("✓")
            self._status_lbl.setStyleSheet("color:#4caf50; font-weight:bold;")
            label = f"{count}/{self.MAX_VARIANTS} 变种" if count > 1 else "1 个"
            color = "#ff6060" if at_max else ("#9070d0" if count > 1 else "#5a7a5a")
            self._variant_lbl.setText(label + (" ★" if at_max else (" ✦" if count > 1 else "")))
            self._variant_lbl.setStyleSheet(
                f"color:{color}; font-size:11px; font-weight:bold; background:transparent;"
            )
            self._load_thumb(existing[0])
            self._expand_btn.show()

        for btn in (self._capture_btn, self._upload_btn):
            btn.setEnabled(not at_max)
            if at_max:
                btn.setToolTip(f"已达到上限 {self.MAX_VARIANTS} 个变种，如需替换请先删除旧变种")

        # Rebuild variant panel if currently visible
        if self._expanded:
            self._build_variant_panel(existing)

    def _load_thumb(self, path: Path):
        try:
            pix = QPixmap(str(path))
            if not pix.isNull():
                self._thumb.setPixmap(
                    pix.scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
        except Exception:
            pass

    # ── expand / collapse ────────────────────────────────────────────────────

    def _toggle_expand(self):
        self._expanded = not self._expanded
        self._expand_btn.setText("▼" if self._expanded else "▶")
        if self._expanded:
            self._build_variant_panel(self._all_existing())
            self._variant_panel.show()
        else:
            self._variant_panel.hide()
        # Notify parent scroll area to resize
        self.updateGeometry()
        if self.parentWidget():
            self.parentWidget().adjustSize()

    def _build_variant_panel(self, existing: list):
        """Rebuild the variant list inside the collapsible panel."""
        # Clear previous contents
        while self._variant_panel_layout.count():
            item = self._variant_panel_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not existing:
            lbl = QLabel("（暂无变种文件）")
            lbl.setStyleSheet("color:#5a5468; font-size:11px; background:transparent;")
            self._variant_panel_layout.addWidget(lbl)
            return

        header_lbl = QLabel(f"变种文件列表  ({len(existing)}/{self.MAX_VARIANTS})")
        header_lbl.setStyleSheet(
            "color:#7a7090; font-size:11px; background:transparent; margin-bottom:2px;"
        )
        self._variant_panel_layout.addWidget(header_lbl)

        for idx, path in enumerate(existing):
            row = QHBoxLayout()
            row.setSpacing(6)

            # Thumbnail
            thumb = QLabel()
            thumb.setFixedSize(36, 36)
            thumb.setAlignment(Qt.AlignCenter)
            thumb.setStyleSheet(
                "background:#0a0a14; border:1px solid #2a2040; border-radius:2px;"
            )
            try:
                pix = QPixmap(str(path))
                if not pix.isNull():
                    thumb.setPixmap(
                        pix.scaled(34, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    )
            except Exception:
                pass
            row.addWidget(thumb)

            # Filename + size
            try:
                kb = path.stat().st_size // 1024
                size_str = f"  {kb} KB"
            except Exception:
                size_str = ""
            label_text = ("主文件" if idx == 0 else f"变种 {idx+1}") + f"  {path.name}{size_str}"
            file_lbl = QLabel(label_text)
            file_lbl.setStyleSheet("color:#a090c0; font-size:11px; background:transparent;")
            row.addWidget(file_lbl, stretch=1)

            # Delete button
            del_btn = QPushButton("🗑 删除")
            del_btn.setFixedWidth(70)
            del_btn.setStyleSheet(
                "QPushButton { background:#2a0a0a; border:1px solid #5a2020; "
                "color:#d06060; border-radius:3px; font-size:11px; padding:3px 6px; }"
                "QPushButton:hover { background:#3a1010; color:#ff8080; }"
            )
            _p = path  # capture in closure
            del_btn.clicked.connect(lambda _=False, p=_p: self._delete_variant(p))
            row.addWidget(del_btn)

            row_widget = QWidget()
            row_widget.setLayout(row)
            self._variant_panel_layout.addWidget(row_widget)

    def _delete_variant(self, path: Path):
        existing = self._all_existing()
        is_primary = (path == ASSETS_DIR / self._filename)

        if is_primary and len(existing) > 1:
            # Promote first variant to primary
            msg = (
                f"正在删除主文件 {path.name}。\n\n"
                f"检测到 {len(existing)-1} 个变种文件。\n"
                "删除后将把第一个变种自动提升为主文件。\n\n"
                "确认删除？"
            )
        else:
            msg = f"确认删除文件：\n{path.name}\n\n此操作不可撤销。"

        reply = QMessageBox.question(
            self, "确认删除", msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            path.unlink()

            if is_primary:
                # Remaining variants after deletion
                remaining = sorted(ASSETS_DIR.glob(f"{self._stem}_v*.png"))
                if remaining:
                    # Promote: rename stem_v2.png → stem.png
                    first = remaining[0]
                    first.rename(ASSETS_DIR / self._filename)
                    # Re-index remaining v3, v4… → v2, v3…
                    rest = sorted(ASSETS_DIR.glob(f"{self._stem}_v*.png"))
                    for i, vpath in enumerate(rest, start=2):
                        new_name = ASSETS_DIR / f"{self._stem}_v{i}.png"
                        if vpath != new_name:
                            vpath.rename(new_name)
            # else: just deleted a variant; re-index remaining variants
            else:
                variants = sorted(ASSETS_DIR.glob(f"{self._stem}_v*.png"))
                for i, vpath in enumerate(variants, start=2):
                    new_name = ASSETS_DIR / f"{self._stem}_v{i}.png"
                    if vpath != new_name:
                        vpath.rename(new_name)

            self.refresh()
        except Exception as e:
            QMessageBox.warning(self, "删除失败", str(e))

    # ── file upload ───────────────────────────────────────────────────────────

    def _upload(self):
        dest_name = self._next_dest_name()
        title = (f"上传主模板 — {dest_name}"
                 if not (ASSETS_DIR / self._filename).exists()
                 else f"上传额外变种 — {dest_name}")

        src, _ = QFileDialog.getOpenFileName(
            self, title, str(Path.home()),
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.tiff)"
        )
        if not src:
            return

        ASSETS_DIR.mkdir(exist_ok=True)
        dest = ASSETS_DIR / dest_name
        try:
            shutil.copy2(src, dest)
            self.refresh()
            QMessageBox.information(
                self, "上传成功",
                f"已保存：assets/{dest_name}\n\n"
                "下次启动脚本时该变种将自动参与识别匹配。"
            )
        except Exception as e:
            QMessageBox.warning(self, "上传失败", str(e))

    # ── screen capture ────────────────────────────────────────────────────────

    def _capture_from_screen(self):
        if len(self._all_existing()) >= self.MAX_VARIANTS:
            return
        top = self.window()
        self._overlay_visible_before = getattr(top, '_overlay', None) and top._overlay.isVisible()
        if self._overlay_visible_before:
            top._overlay.hide()
        top.hide()
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(450, self._open_capture_picker)

    def _open_capture_picker(self):
        from ui.region_picker import RegionPickerWindow
        self._picker = RegionPickerWindow(
            title=f"框选「{self._disp_name}」区域  ·  Enter 或 双击 确认  ·  Esc 取消",
        )
        self._picker.region_selected.connect(self._on_capture_region)
        self._picker.cancelled.connect(self._restore_window)
        self._picker.show()

    @pyqtSlot(int, int, int, int)
    def _on_capture_region(self, x1, y1, x2, y2):
        try:
            screenshot: QPixmap = self._picker._screenshot
            if screenshot is None or screenshot.isNull():
                raise RuntimeError("截图为空")
            img = screenshot.toImage()
            from PyQt5.QtCore import QRect
            cropped = img.copy(QRect(x1, y1, x2 - x1, y2 - y1))
            if cropped.isNull() or cropped.width() < 4 or cropped.height() < 4:
                raise RuntimeError("选区太小，请重新框选")
            ASSETS_DIR.mkdir(exist_ok=True)
            dest_name = self._next_dest_name()
            dest = ASSETS_DIR / dest_name
            if not cropped.save(str(dest)):
                raise RuntimeError(f"保存失败: {dest}")
            self._restore_window()
            self.refresh()
            QMessageBox.information(
                self.window(), "截图保存成功",
                f"已保存为：assets/{dest_name}\n"
                f"区域：({x1},{y1}) → ({x2},{y2})  {x2-x1}×{y2-y1}px\n\n"
                "下次启动脚本时将自动参与识别匹配。"
            )
        except Exception as e:
            self._restore_window()
            QMessageBox.warning(self.window(), "保存失败", str(e))

    def _restore_window(self):
        top = self.window()
        top.show()
        if self._overlay_visible_before:
            try:
                top._overlay.show()
            except Exception:
                pass


# ── Main Window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    # Thread-safe hotkey signals — emitted from keyboard lib's thread,
    # received in Qt main thread via auto QueuedConnection.
    _sig_f1 = pyqtSignal()
    _sig_f3 = pyqtSignal()
    _sig_f4 = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("D4 Auto — 暗黑破坏神4 自动脚本")
        self.setMinimumSize(960, 620)
        self.resize(1100, 680)
        self.setStyleSheet(STYLESHEET)
        self._set_icon()

        self._bot_thread: BotThread | None = None
        self._lang = "cn"
        self._log_lines: list[str] = []
        self._overlay = OverlayWindow()

        # Connect hotkey signals to slots (auto QueuedConnection cross-thread)
        self._sig_f1.connect(self.toggle_bot)
        self._sig_f3.connect(self.restart_bot)
        self._sig_f4.connect(self.toggle_overlay)

        self._build_ui()
        self._setup_hotkeys()
        self._refresh_templates()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        root.addLayout(self._make_title_bar())
        root.addLayout(self._make_thin_sep())
        root.addWidget(self._make_body_splitter(), stretch=1)
        root.addLayout(self._make_thin_sep())
        root.addLayout(self._make_control_bar())

    def _make_title_bar(self):
        bar = QHBoxLayout()
        bar.setSpacing(10)

        lbl_title = QLabel("⚔  D4 AUTO")
        lbl_title.setObjectName("titleLabel")
        bar.addWidget(lbl_title)

        lbl_sub = QLabel("暗黑破坏神4 · 自动脚本")
        lbl_sub.setObjectName("subtitleLabel")
        bar.addWidget(lbl_sub)

        bar.addStretch()

        # Running indicator
        self._lbl_dot = QLabel("●")
        self._lbl_dot.setStyleSheet(
            "font-size:18px; color:#3a3a4a; background:transparent;"
        )
        bar.addWidget(self._lbl_dot)

        self._lbl_state = QLabel("空闲")
        self._lbl_state.setObjectName("stateLabel")
        bar.addWidget(self._lbl_state)

        # Language selector
        lang_lbl = QLabel("语言")
        lang_lbl.setStyleSheet("color:#5a5468; font-size:12px; background:transparent;")
        bar.addWidget(lang_lbl)

        self._lang_combo = QComboBox()
        self._lang_combo.addItems(["中文 (cn)", "English (en)"])
        self._lang_combo.setFixedWidth(110)
        self._lang_combo.currentIndexChanged.connect(self._on_lang_changed)
        bar.addWidget(self._lang_combo)

        return bar

    def _make_thin_sep(self):
        layout = QHBoxLayout()
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color:#2a2040; background:#2a2040; max-height:1px;")
        layout.addWidget(line)
        return layout

    def _make_body_splitter(self):
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)

        # ── Left panel: skill editor ──
        left = QWidget()
        left.setMinimumWidth(280)
        left.setMaximumWidth(380)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(6)
        left_layout.addWidget(self._make_skill_panel())
        splitter.addWidget(left)
        self._left_panel = left          # keep reference for show/hide

        # ── Right panel: templates + logs tabs ──
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._make_right_tabs())
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        return splitter

    # ── Skill Editor ──────────────────────────────────────────────────────────

    def _make_skill_panel(self):
        from PyQt5.QtWidgets import QGroupBox
        group = QGroupBox("⚔  技能配置")
        layout = QVBoxLayout(group)
        layout.setSpacing(6)

        hint = QLabel("点击「按键」列格子后按下目标键")
        hint.setObjectName("hintLabel")
        layout.addWidget(hint)

        self._skill_table = QTableWidget(0, 4)
        self._skill_table.setHorizontalHeaderLabels(["#", "按键", "间隔(s)", "启用"])
        self._skill_table.verticalHeader().setVisible(False)
        self._skill_table.setAlternatingRowColors(True)
        self._skill_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._skill_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hdr = self._skill_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed)
        self._skill_table.setColumnWidth(0, 32)
        self._skill_table.setColumnWidth(1, 60)
        self._skill_table.setColumnWidth(3, 48)
        self._skill_table.setMinimumHeight(160)
        layout.addWidget(self._skill_table)

        self._load_skills_to_table()

        # Buttons row
        btn_row = QHBoxLayout()
        btn_add = QPushButton("＋ 添加")
        btn_add.setObjectName("addSkillBtn")
        btn_add.clicked.connect(self._add_skill_row)
        btn_del = QPushButton("－ 删除")
        btn_del.setObjectName("removeSkillBtn")
        btn_del.clicked.connect(self._remove_skill_row)
        btn_save = QPushButton("💾 保存")
        btn_save.clicked.connect(self._save_skills)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

        return group

    def _load_skills_to_table(self):
        try:
            with open(SKILLS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            skills = data.get("skills", [])
        except Exception:
            skills = [
                {"id": 0, "key": "2", "interval": 0.25, "enabled": True},
                {"id": 1, "key": "3", "interval": 0.25, "enabled": True},
                {"id": 2, "key": "4", "interval": 0.25, "enabled": True},
            ]
        self._skill_table.setRowCount(0)
        for skill in skills:
            self._append_skill_row(
                skill.get("key", ""),
                skill.get("interval", 0.25),
                skill.get("enabled", True),
            )

    def _append_skill_row(self, key: str, interval: float, enabled: bool):
        row = self._skill_table.rowCount()
        self._skill_table.insertRow(row)

        # # column
        num_item = QTableWidgetItem(str(row + 1))
        num_item.setTextAlignment(Qt.AlignCenter)
        num_item.setFlags(Qt.ItemIsEnabled)
        self._skill_table.setItem(row, 0, num_item)

        # Key capture
        key_edit = KeyCaptureEdit(key)
        key_edit.setFixedHeight(28)
        self._skill_table.setCellWidget(row, 1, key_edit)

        # Interval spinner
        spin = _NoScrollDSpin()
        spin.setRange(0.01, 30.0)
        spin.setSingleStep(0.05)
        spin.setDecimals(2)
        spin.setValue(interval)
        spin.setFixedHeight(28)
        spin.setToolTip("释放间隔（秒）— 每个技能独立计算")
        self._skill_table.setCellWidget(row, 2, spin)

        # Enable checkbox (centered via widget wrapper)
        chk_wrapper = QWidget()
        chk_layout = QHBoxLayout(chk_wrapper)
        chk_layout.setContentsMargins(0, 0, 0, 0)
        chk_layout.setAlignment(Qt.AlignCenter)
        chk = QCheckBox()
        chk.setChecked(enabled)
        chk_layout.addWidget(chk)
        self._skill_table.setCellWidget(row, 3, chk_wrapper)

        self._skill_table.setRowHeight(row, 34)

    def _add_skill_row(self):
        self._append_skill_row("", 0.25, True)

    def _remove_skill_row(self):
        rows = sorted({idx.row() for idx in self._skill_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self._skill_table.removeRow(row)
        self._renumber_rows()

    def _renumber_rows(self):
        for r in range(self._skill_table.rowCount()):
            item = self._skill_table.item(r, 0)
            if item:
                item.setText(str(r + 1))

    def _save_skills(self):
        skills = []
        for row in range(self._skill_table.rowCount()):
            key_w = self._skill_table.cellWidget(row, 1)
            spin_w = self._skill_table.cellWidget(row, 2)
            chk_wrapper = self._skill_table.cellWidget(row, 3)
            if not all([key_w, spin_w, chk_wrapper]):
                continue
            chk = chk_wrapper.findChild(QCheckBox)
            skills.append({
                "id": row,
                "key": key_w.text() if key_w.text() not in ("", "…") else "",
                "interval": round(spin_w.value(), 3),
                "enabled": chk.isChecked() if chk else True,
            })

        SKILLS_PATH.parent.mkdir(exist_ok=True)
        with open(SKILLS_PATH, "w", encoding="utf-8") as f:
            json.dump({"skills": skills}, f, ensure_ascii=False, indent=2)

        # Hot-reload if bot is running
        if self._bot_thread and self._bot_thread.isRunning():
            self._bot_thread.reload_skills()

        self._log("[UI] 技能配置已保存" + (" 并热更新至运行中的脚本" if (self._bot_thread and self._bot_thread.isRunning()) else ""))

    # ── Right tabs ────────────────────────────────────────────────────────────

    def _make_right_tabs(self):
        tabs = QTabWidget()
        tabs.addTab(self._make_template_tab(), "🖼  图片模板")
        tabs.addTab(self._make_calibration_tab(), "🎯  屏幕校准")
        tabs.addTab(self._make_settings_tab(), "⚙  通用设置")
        tabs.addTab(self._make_log_tab(), "📋  运行日志")
        return tabs

    def _make_template_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        self._template_layout = QVBoxLayout(container)
        self._template_layout.setContentsMargins(6, 6, 6, 6)
        self._template_layout.setSpacing(4)
        self._template_rows: list[TemplateRow] = []

        hint = QLabel(
            "✦ 点击「上传」选择本地图片 · 罗盘图标支持上传多个变种提升识别率"
        )
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        self._template_layout.addWidget(hint)

        # Group templates by category
        categories = {
            "小地图导航": [],
            "罗盘 / 传送": [],
            "BOSS 大门": [],
            "宝箱 / 拾取": [],
        }
        cat_map = {
            "minimap_bonehand.png":    "小地图导航",
            "minimap_extrahand.png":   "小地图导航",
            "minimap_bosshand.png":    "小地图导航",
            "icon_compass.png":        "罗盘 / 传送",
            "icon_compassdoor.png":    "罗盘 / 传送",
            "modal_usekey.png":        "罗盘 / 传送",
            "modal_tp_compass.png":    "罗盘 / 传送",
            "icon_start.png":          "罗盘 / 传送",
            "icon_bossdoor.png":       "BOSS 大门",
            "icon_bossdoor_merge.png": "BOSS 大门",
            "icon_health.png":         "宝箱 / 拾取",
            "tip_bosschest.png":       "宝箱 / 拾取",
            "icon_key.png":            "宝箱 / 拾取",
            "backpack_key.png":        "宝箱 / 拾取",
            "tip_huifu.png":           "宝箱 / 拾取",
            "icon_taigu_tag.png":      "宝箱 / 拾取",
            "hundun_event.png":        "宝箱 / 拾取",
        }
        for display_name, filename, description in TEMPLATE_CATALOGUE:
            cat = cat_map.get(filename, "其他")
            categories.setdefault(cat, []).append((display_name, filename, description))

        for cat_name, entries in categories.items():
            if not entries:
                continue
            cat_lbl = QLabel(f"▸  {cat_name}")
            cat_lbl.setObjectName("categoryLabel")
            self._template_layout.addWidget(cat_lbl)

            for display_name, filename, description in entries:
                row_widget = TemplateRow(display_name, filename, description)
                row_widget.setStyleSheet(
                    "background-color: #0e0e1c; border-radius:4px;"
                    " border: 1px solid #1e1e30;"
                )
                self._template_layout.addWidget(row_widget)
                self._template_rows.append(row_widget)

            spacer = QFrame()
            spacer.setFrameShape(QFrame.HLine)
            spacer.setStyleSheet("color:#1e1e2e; background:#1e1e2e; max-height:1px;")
            self._template_layout.addWidget(spacer)

        self._template_layout.addStretch()
        scroll.setWidget(container)
        return scroll

    # ── Calibration tab (visual region picker + auto nav-offset calibration) ──

    def _make_calibration_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        cal = self._load_calibration_dict()

        # ─ 1. Minimap Region ─────────────────────────────────────────────────
        mm_group = QGroupBox("①  小地图区域 (MINIMAP_REGION)")
        mm_vbox = QVBoxLayout(mm_group)
        mm_vbox.setSpacing(8)
        mm_desc = QLabel(
            "框住屏幕右上角整个小地图矩形。\n"
            "点击「📷 可视化选择」→ 当前游戏截图全屏出现 → 拖动/缩放金色框 → Enter 确认。"
        )
        mm_desc.setWordWrap(True)
        mm_desc.setStyleSheet("color:#7a7090;font-size:11px;background:transparent;")
        mm_vbox.addWidget(mm_desc)
        mm_btn = QPushButton("📷  可视化选择小地图区域")
        mm_btn.setStyleSheet(
            "background:#1a2a3a;border:1px solid #3a6080;color:#60c0ff;"
            "padding:8px 16px;border-radius:4px;font-size:13px;"
        )
        mm_btn.clicked.connect(self._pick_minimap)
        mm_vbox.addWidget(mm_btn)
        mr = cal.get("minimap_region", [2159, 91, 2523, 352])
        self._cal_mm = [self._cal_spin(mr[i], 0, 9999) for i in range(4)]
        coord_row = QHBoxLayout()
        for label, spin in zip(["X1 左", "Y1 上", "X2 右", "Y2 下"], self._cal_mm):
            col = QVBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("color:#5a5468;font-size:11px;background:transparent;")
            lbl.setAlignment(Qt.AlignCenter)
            col.addWidget(lbl)
            col.addWidget(spin)
            coord_row.addLayout(col)
        mm_vbox.addLayout(coord_row)
        self._lbl_player_pos = QLabel("")
        self._lbl_player_pos.setStyleSheet(
            "color:#9070d0;font-size:11px;background:transparent;"
        )
        mm_vbox.addWidget(self._lbl_player_pos)
        self._update_player_pos_label()
        for s in self._cal_mm:
            s.valueChanged.connect(self._update_player_pos_label)
        layout.addWidget(mm_group)

        # ─ 1b. Instance HUD Region ───────────────────────────────────────────
        hud_group = QGroupBox("①b  副本 HUD 检测区域 (INSTANCE_HUD_REGION)")
        hud_vbox = QVBoxLayout(hud_group)
        hud_vbox.setSpacing(8)
        hud_desc = QLabel(
            "右上角副本波次图标出现的区域（仅在罗盘内可见）。\n"
            "用于启动时判断角色是否已在副本中，跳过开背包点钥匙的流程。\n"
            "点击「📷 可视化选择」框住该图标区域；同时记得在图片模板 Tab 上传「副本 HUD 图标」截图。"
        )
        hud_desc.setWordWrap(True)
        hud_desc.setStyleSheet("color:#7a7090;font-size:11px;background:transparent;")
        hud_vbox.addWidget(hud_desc)
        hud_btn = QPushButton("📷  可视化选择副本 HUD 区域")
        hud_btn.setStyleSheet(
            "background:#1a2a3a;border:1px solid #3a6080;color:#60c0ff;"
            "padding:8px 16px;border-radius:4px;font-size:13px;"
        )
        hud_btn.clicked.connect(self._pick_hud_region)
        hud_vbox.addWidget(hud_btn)
        hr = cal.get("instance_hud_region", [1680, 20, 2150, 140])
        self._cal_hud = [self._cal_spin(hr[i], 0, 9999) for i in range(4)]
        hud_coord_row = QHBoxLayout()
        for label, spin in zip(["X1 左", "Y1 上", "X2 右", "Y2 下"], self._cal_hud):
            col = QVBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("color:#5a5468;font-size:11px;background:transparent;")
            lbl.setAlignment(Qt.AlignCenter)
            col.addWidget(lbl)
            col.addWidget(spin)
            hud_coord_row.addLayout(col)
        hud_vbox.addLayout(hud_coord_row)
        layout.addWidget(hud_group)

        # ─ 2. Nav Centre Offset ──────────────────────────────────────────────
        nc_group = QGroupBox("②  导航中心偏移 (NAV_CENTER_DX / DY)")
        nc_vbox = QVBoxLayout(nc_group)
        nc_vbox.setSpacing(8)
        nc_desc = QLabel(
            "控制机器人认为「自己在副本中心」时停止的偏移量。\n\n"
            "最简单校准方法:\n"
            "  1. 进入游戏，手动操作角色走到事件选择界面正中心\n"
            "  2. 回到此界面，点击下方按钮\n"
            "  3. 脚本自动截图小地图、定位事件图标、计算偏移\n\n"
            "若机器人总停在偏北位置 → 手动把 Y 偏移调大（正值=往南）。"
        )
        nc_desc.setWordWrap(True)
        nc_desc.setStyleSheet("color:#7a7090;font-size:11px;background:transparent;")
        nc_vbox.addWidget(nc_desc)
        nc_btn = QPushButton("🎯  以当前游戏位置标记导航中心  (角色须站在正中央)")
        nc_btn.setStyleSheet(
            "background:#1a2e18;border:1px solid #3a7030;color:#70d060;"
            "padding:8px 16px;border-radius:4px;font-size:13px;"
        )
        nc_btn.clicked.connect(self._mark_nav_center)
        nc_vbox.addWidget(nc_btn)
        nc_row = QHBoxLayout()
        nc_row.setSpacing(20)
        self._cal_dx = self._cal_dspin(cal.get("nav_center_dx", 0), -300, 300)
        self._cal_dy = self._cal_dspin(cal.get("nav_center_dy", 0), -300, 300)
        for lbl_text, spin in [
            ("X 偏移  (正=东 / 负=西)", self._cal_dx),
            ("Y 偏移  (正=南 / 负=北)", self._cal_dy),
        ]:
            col = QVBoxLayout()
            lbl = QLabel(lbl_text)
            lbl.setStyleSheet("color:#5a5468;font-size:11px;background:transparent;")
            col.addWidget(lbl)
            col.addWidget(spin)
            nc_row.addLayout(col)
        nc_row.addStretch()
        nc_vbox.addLayout(nc_row)
        layout.addWidget(nc_group)

        # ─ 2b. Chest approach offset ─────────────────────────────────────────
        ch_group = QGroupBox("②b  宝箱区域基准点 (CHEST_NAV_DX / DY)")
        ch_vbox = QVBoxLayout(ch_group)
        ch_vbox.setSpacing(8)
        ch_desc = QLabel(
            "Bot进入宝箱区域后，会先导航到这个「基准点」（3个箱子之间的空地），\n"
            "然后再从基准点出发去开每个选定的箱子；开完一个箱子后也会先回到这里，\n"
            "再出发去下一个箱子。\n\n"
            "建议将基准点校准到3个宝箱中间或正前方的空地位置。\n\n"
            "校准方法:\n"
            "  1. 进入游戏，手动走到3个宝箱中间或正前方\n"
            "  2. 回到此界面，点击下方按钮\n"
            "  3. 脚本自动截图小地图、定位血泉图标、计算偏移"
        )
        ch_desc.setWordWrap(True)
        ch_desc.setStyleSheet("color:#7a7090;font-size:11px;background:transparent;")
        ch_vbox.addWidget(ch_desc)
        ch_btn = QPushButton("📍  以当前游戏位置标记宝箱区域基准点  (站在3箱子中间)")
        ch_btn.setStyleSheet(
            "background:#1a2030;border:1px solid #3a5080;color:#60a0e0;"
            "padding:8px 16px;border-radius:4px;font-size:13px;"
        )
        ch_btn.clicked.connect(self._mark_chest_pos)
        ch_vbox.addWidget(ch_btn)
        ch_row = QHBoxLayout()
        ch_row.setSpacing(20)
        self._cal_chest_dx = self._cal_dspin(cal.get("chest_nav_dx", 12.0), -400, 400)
        self._cal_chest_dy = self._cal_dspin(cal.get("chest_nav_dy", 111.0), -400, 400)
        for lbl_text, spin in [
            ("DX  (正=东 / 负=西)", self._cal_chest_dx),
            ("DY  (正=南 / 负=北)", self._cal_chest_dy),
        ]:
            col = QVBoxLayout()
            lbl = QLabel(lbl_text)
            lbl.setStyleSheet("color:#5a5468;font-size:11px;background:transparent;")
            col.addWidget(lbl)
            col.addWidget(spin)
            ch_row.addLayout(col)
        ch_row.addStretch()
        ch_vbox.addLayout(ch_row)
        layout.addWidget(ch_group)

        # ─ 2c. Boss-door approach offset ──────────────────────────────────────
        bd_group = QGroupBox("②c  Boss房门接近偏移 (BOSS_DOOR_NAV_DX / DY)")
        bd_vbox = QVBoxLayout(bd_group)
        bd_vbox.setSpacing(8)
        bd_desc = QLabel(
            "控制机器人导航到Boss房门时的停止位置。\n"
            "当bossdoor图标位于小地图玩家点的 (DX, DY) 偏移处时，认为「已到达Boss门前」。\n\n"
            "校准方法:\n"
            "  1. 进入游戏，手动走到Boss房门可以交互的位置\n"
            "  2. 回到此界面，点击下方按钮"
        )
        bd_desc.setWordWrap(True)
        bd_desc.setStyleSheet("color:#7a7090;font-size:11px;background:transparent;")
        bd_vbox.addWidget(bd_desc)
        bd_btn = QPushButton("🚪  以当前游戏位置标记Boss门接近点  (角色须站在Boss门前)")
        bd_btn.setStyleSheet(
            "background:#2a1a10;border:1px solid #805030;color:#e08050;"
            "padding:8px 16px;border-radius:4px;font-size:13px;"
        )
        bd_btn.clicked.connect(self._mark_boss_door_pos)
        bd_vbox.addWidget(bd_btn)
        bd_row = QHBoxLayout()
        bd_row.setSpacing(20)
        self._cal_bd_dx = self._cal_dspin(cal.get("boss_door_nav_dx", -3.0), -400, 400)
        self._cal_bd_dy = self._cal_dspin(cal.get("boss_door_nav_dy", -6.0), -400, 400)
        for lbl_text, spin in [
            ("DX  (正=东 / 负=西)", self._cal_bd_dx),
            ("DY  (正=南 / 负=北)", self._cal_bd_dy),
        ]:
            col = QVBoxLayout()
            lbl = QLabel(lbl_text)
            lbl.setStyleSheet("color:#5a5468;font-size:11px;background:transparent;")
            col.addWidget(lbl)
            col.addWidget(spin)
            bd_row.addLayout(col)
        bd_row.addStretch()
        bd_vbox.addLayout(bd_row)
        layout.addWidget(bd_group)

        # ─ 2d-f. Per-type Boss chest calibration ─────────────────────────────
        chest_type_desc = QLabel(
            "Boss房中共有3种战利品宝箱，位置各不相同。\n"
            "为每种宝箱单独校准：① 小地图导航偏移（走到哪里停下）\n"
            "  ② 屏幕扫描范围（在屏幕哪个区域寻找该宝箱的图标）。\n"
            "校准步骤：进入游戏站到对应宝箱前 → 点「标记」按钮 → 用📷框选宝箱出现的屏幕区域。\n"
            "模板图片在【图片模板】页面上传（上传宝箱外观截图，非悬停提示）。"
        )
        chest_type_desc.setWordWrap(True)
        chest_type_desc.setStyleSheet(
            "color:#7a7090;font-size:11px;background:transparent;"
            "padding:4px 0;"
        )
        layout.addWidget(chest_type_desc)

        def _chest_type_group(label, color_bg, color_border, color_txt,
                              dx_attr, dy_attr, scan_attr,
                              dx_default, dy_default, scan_default,
                              cal_key_dx, cal_key_dy, cal_key_scan,
                              mark_slot):
            grp = QGroupBox(label)
            grp.setStyleSheet(
                f"QGroupBox{{font-weight:bold;color:{color_txt};"
                f"border:1px solid {color_border};border-radius:5px;margin-top:8px;}}"
                "QGroupBox::title{subcontrol-origin:margin;left:10px;}"
            )
            vbox = QVBoxLayout(grp)
            vbox.setSpacing(6)
            vbox.setContentsMargins(8, 14, 8, 8)

            # ── Nav offset row ───────────────────────────────────────────────
            nav_lbl = QLabel("小地图导航偏移（角色应站在该宝箱前校准）")
            nav_lbl.setStyleSheet("color:#5a5468;font-size:11px;background:transparent;")
            vbox.addWidget(nav_lbl)

            mark_btn = QPushButton("📦  标记当前游戏位置为此宝箱的接近点")
            mark_btn.setStyleSheet(
                f"background:{color_bg};border:1px solid {color_border};"
                f"color:{color_txt};padding:6px 14px;border-radius:4px;font-size:12px;"
            )
            mark_btn.clicked.connect(mark_slot)
            vbox.addWidget(mark_btn)

            dx_spin = self._cal_dspin(cal.get(cal_key_dx, dx_default), -400, 400)
            dy_spin = self._cal_dspin(cal.get(cal_key_dy, dy_default), -400, 400)
            setattr(self, dx_attr, dx_spin)
            setattr(self, dy_attr, dy_spin)
            nav_row = QHBoxLayout()
            nav_row.setSpacing(16)
            for lbl_txt, sp in [("DX（正=东）", dx_spin), ("DY（正=南）", dy_spin)]:
                col = QVBoxLayout()
                col.addWidget(QLabel(lbl_txt))
                col.addWidget(sp)
                col.itemAt(0).widget().setStyleSheet(
                    "color:#5a5468;font-size:10px;background:transparent;"
                )
                nav_row.addLayout(col)
            nav_row.addStretch()
            vbox.addLayout(nav_row)

            # ── Scan region row ──────────────────────────────────────────────
            scan_lbl = QLabel("屏幕扫描区域（宝箱图标出现在屏幕哪个矩形范围内）")
            scan_lbl.setStyleSheet(
                "color:#5a5468;font-size:11px;background:transparent;margin-top:4px;"
            )
            vbox.addWidget(scan_lbl)

            vals = cal.get(cal_key_scan, list(scan_default))
            spins = [self._cal_spin(vals[i], 0, 9999) for i in range(4)]
            setattr(self, scan_attr, spins)
            scan_row = QHBoxLayout()
            scan_row.setSpacing(6)
            for lbl_txt, sp in zip(["X1", "Y1", "X2", "Y2"], spins):
                col = QVBoxLayout()
                lbl = QLabel(lbl_txt)
                lbl.setStyleSheet(
                    "color:#5a5468;font-size:10px;background:transparent;"
                )
                lbl.setAlignment(Qt.AlignCenter)
                col.addWidget(lbl)
                col.addWidget(sp)
                scan_row.addLayout(col)
            pick_btn = QPushButton("📷")
            pick_btn.setFixedWidth(38)
            pick_btn.setToolTip(f"可视化选择 {label} 的扫描范围")
            pick_btn.setStyleSheet(
                "background:#1a2a3a;border:1px solid #3a6080;color:#60c0ff;"
                "padding:4px;border-radius:4px;font-size:13px;"
            )
            _sa = scan_attr
            _pt = f"{label} 扫描区域"
            pick_btn.clicked.connect(
                lambda _=False, sa=_sa, pt=_pt: self._pick_region(pt, sa)
            )
            scan_row.addWidget(pick_btn)
            vbox.addLayout(scan_row)

            layout.addWidget(grp)

        _chest_type_group(
            label="②d  装备箱 (chest_equip)",
            color_bg="#1a1030", color_border="#6040a0", color_txt="#c080ff",
            dx_attr="_cal_equip_dx",   dy_attr="_cal_equip_dy",
            scan_attr="_cal_equip_scan",
            dx_default=12.0, dy_default=111.0,
            scan_default=[900, 200, 1660, 900],
            cal_key_dx="equip_chest_nav_dx", cal_key_dy="equip_chest_nav_dy",
            cal_key_scan="equip_chest_scan_region",
            mark_slot=lambda: self._mark_chest_type_pos(
                self._cal_equip_dx, self._cal_equip_dy, "装备箱"
            ),
        )
        _chest_type_group(
            label="②e  材料箱 (chest_material)",
            color_bg="#101a10", color_border="#3a8040", color_txt="#60c060",
            dx_attr="_cal_material_dx", dy_attr="_cal_material_dy",
            scan_attr="_cal_material_scan",
            dx_default=12.0, dy_default=111.0,
            scan_default=[900, 200, 1660, 900],
            cal_key_dx="material_chest_nav_dx", cal_key_dy="material_chest_nav_dy",
            cal_key_scan="material_chest_scan_region",
            mark_slot=lambda: self._mark_chest_type_pos(
                self._cal_material_dx, self._cal_material_dy, "材料箱"
            ),
        )
        _chest_type_group(
            label="②f  金币箱 (chest_gold)",
            color_bg="#1a1800", color_border="#806020", color_txt="#d0a020",
            dx_attr="_cal_gold_dx",    dy_attr="_cal_gold_dy",
            scan_attr="_cal_gold_scan",
            dx_default=12.0, dy_default=111.0,
            scan_default=[900, 200, 1660, 900],
            cal_key_dx="gold_chest_nav_dx", cal_key_dy="gold_chest_nav_dy",
            cal_key_scan="gold_chest_scan_region",
            mark_slot=lambda: self._mark_chest_type_pos(
                self._cal_gold_dx, self._cal_gold_dy, "金币箱"
            ),
        )

        # ─ 3. Detection Scan Regions ─────────────────────────────────────────
        dr_group = QGroupBox("③  检测区域校准（高级）")
        dr_vbox = QVBoxLayout(dr_group)
        dr_vbox.setSpacing(8)
        dr_desc = QLabel(
            "以下区域决定各功能在屏幕哪个范围内寻找目标。\n"
            "默认值按 2560×1440 设置，其他分辨率可在此调整。\n"
            "每个区域均可点击「📷」进行可视化选择。"
        )
        dr_desc.setWordWrap(True)
        dr_desc.setStyleSheet("color:#7a7090;font-size:11px;background:transparent;")
        dr_vbox.addWidget(dr_desc)

        def _region_row(label, key, default, pick_title, pick_attr):
            """Build a compact region row: label + 4 spinboxes + picker button."""
            row_box = QGroupBox(label)
            row_box.setStyleSheet(
                "QGroupBox { font-size:11px; color:#7a7090; "
                "border:1px solid #2a2040; border-radius:4px; margin-top:6px; padding:4px; }"
                "QGroupBox::title { subcontrol-origin:margin; left:8px; }"
            )
            row_vbox = QVBoxLayout(row_box)
            row_vbox.setSpacing(4)
            vals = cal.get(key, list(default))
            spins = [self._cal_spin(vals[i], 0, 9999) for i in range(4)]
            setattr(self, pick_attr, spins)
            coord_h = QHBoxLayout()
            for lbl_txt, sp in zip(["X1", "Y1", "X2", "Y2"], spins):
                col = QVBoxLayout()
                lbl = QLabel(lbl_txt)
                lbl.setStyleSheet("color:#5a5468;font-size:10px;background:transparent;")
                lbl.setAlignment(Qt.AlignCenter)
                col.addWidget(lbl)
                col.addWidget(sp)
                coord_h.addLayout(col)
            pick_btn = QPushButton("📷")
            pick_btn.setFixedWidth(38)
            pick_btn.setToolTip(f"可视化选择: {label}")
            pick_btn.setStyleSheet(
                "background:#1a2a3a;border:1px solid #3a6080;color:#60c0ff;"
                "padding:4px;border-radius:4px;font-size:13px;"
            )
            # capture pick_attr in closure
            _pa = pick_attr
            _pt = pick_title
            pick_btn.clicked.connect(lambda _=False, pa=_pa, pt=_pt: self._pick_region(pt, pa))
            coord_h.addWidget(pick_btn)
            row_vbox.addLayout(coord_h)
            dr_vbox.addWidget(row_box)

        _region_row("死亡检测区域  (DEATH_SCAN_REGION)",
                    "death_scan_region", [640, 792, 1920, 1296],
                    "死亡检测区域  ·  框住「在存档点重生」按钮出现的区域",
                    "_cal_death")
        _region_row("弹窗扫描区域  (MODAL_SCAN_REGION)",
                    "modal_scan_region", [400, 600, 2160, 1200],
                    "弹窗扫描区域  ·  框住「接受/Accept」按钮可能出现的区域",
                    "_cal_modal")
        _region_row("波次识别区域  (WAVE_REGION)",
                    "wave_region", [1960, 80, 2100, 120],
                    "波次识别区域  ·  框住右上角「波次 x/10」文字区域",
                    "_cal_wave")
        _region_row("以太识别区域  (ETHER_REGION)",
                    "ether_region", [1960, 190, 2150, 260],
                    "以太识别区域  ·  框住屏幕上以太数量的数字区域",
                    "_cal_ether")
        _region_row("事件扫描区域  (EVENT_SCAN_ROI)",
                    "event_scan_roi", [50, 20, 2000, 1420],
                    "事件扫描区域  ·  框住事件名称文字可能出现的整个范围",
                    "_cal_event")
        _region_row("背包扫描区域  (INVENTORY_REGION)",
                    "inventory_region", [1600, 120, 2550, 1380],
                    "背包扫描区域  ·  框住打开背包后物品列表的区域",
                    "_cal_inv")
        _region_row("任务状态栏区域  (QUEST_TRACKER_REGION)\n"
                    "  覆盖屏幕右侧的任务目标文字区域（小地图下方、游戏面板右侧）\n"
                    "  若OCR读出乱码数字，说明框住了波次/计时器，需向下移动Y1/Y2",
                    "quest_tracker_region", [1850, 420, 2540, 810],
                    "贡品任务栏区域  ·  框住右侧任务目标「选择炼狱供奉」文字出现的条带",
                    "_cal_quest")
        _region_row("议会大门交互区域  (BOSS_DOOR_SCAN_REGION)\n"
                    "  框住「议会大门 / Council Gate」交互提示文字可能出现的屏幕区域\n"
                    "  机器人在此区域内扫描可交互的大门文字，找到后点击进入Boss战",
                    "boss_door_scan_region", [0, 100, 2560, 900],
                    "议会大门扫描区域  ·  框住Boss房门交互提示出现的范围",
                    "_cal_boss_door_scan")

        layout.addWidget(dr_group)

        # ─ 4. Match Threshold ────────────────────────────────────────────────
        mt_group = QGroupBox("④  模板匹配阈值 (MATCH_THRESHOLD)")
        mt_vbox = QVBoxLayout(mt_group)
        mt_hint = QLabel(
            "0.40 为默认值。调低(如0.30)提高召回率但易误识别；"
            "调高(如0.55)更严格但可能漏检。通常不需要修改。"
        )
        mt_hint.setWordWrap(True)
        mt_hint.setStyleSheet("color:#7a7090;font-size:11px;background:transparent;")
        mt_vbox.addWidget(mt_hint)
        mt_row = QHBoxLayout()
        mt_lbl = QLabel("阈值")
        mt_lbl.setStyleSheet("color:#5a5468;font-size:11px;background:transparent;")
        self._cal_thresh = self._cal_dspin(
            cal.get("match_threshold", 0.40), 0.10, 0.99, step=0.01, decimals=2
        )
        mt_row.addWidget(mt_lbl)
        mt_row.addWidget(self._cal_thresh)
        mt_row.addStretch()
        mt_vbox.addLayout(mt_row)
        layout.addWidget(mt_group)

        # ─ Save / Reset ───────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_save = QPushButton("💾  保存校准")
        btn_save.setStyleSheet(
            "background:#1a2e18;border:1px solid #3a7030;color:#70d060;"
            "padding:8px 20px;border-radius:4px;font-size:13px;font-weight:bold;"
        )
        btn_save.clicked.connect(self._save_calibration)
        btn_reset = QPushButton("↺  恢复默认")
        btn_reset.setStyleSheet(
            "background:#1e1828;border:1px solid #352a48;color:#9070d0;"
            "padding:8px 20px;border-radius:4px;font-size:13px;"
        )
        btn_reset.clicked.connect(self._reset_calibration)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_reset)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addStretch()
        scroll.setWidget(w)
        return scroll

    # ── Calibration helpers ───────────────────────────────────────────────────

    def _update_player_pos_label(self):
        x1, y1, x2, y2 = [s.value() for s in self._cal_mm]
        self._lbl_player_pos.setText(
            f"→ PLAYER_POS 自动计算为中心点: ({(x1+x2)//2}, {(y1+y2)//2})"
        )

    def _pick_minimap(self):
        cal = self._load_calibration_dict()
        initial = tuple(cal.get("minimap_region", [2159, 91, 2523, 352]))
        self._start_picker(
            "选择小地图区域  ·  框住右上角整个小地图  ·  Enter 或 双击 确认",
            initial, self._on_minimap_picked,
        )

    def _pick_hud_region(self):
        cal = self._load_calibration_dict()
        initial = tuple(cal.get("instance_hud_region", [1680, 20, 2150, 140]))
        self._start_picker(
            "选择副本 HUD 区域  ·  框住右上角波次图标区域  ·  Enter 或 双击 确认",
            initial, self._on_hud_region_picked,
        )

    def _pick_region(self, title: str, spin_attr: str):
        """Generic region picker for any 4-spinbox attribute."""
        spins = getattr(self, spin_attr, None)
        if spins is None:
            return
        initial = tuple(s.value() for s in spins)
        self._pending_pick_attr = spin_attr
        self._start_picker(title + "  ·  Enter 或 双击 确认",
                           initial, self._on_generic_region_picked)

    @pyqtSlot(int, int, int, int)
    def _on_generic_region_picked(self, x1, y1, x2, y2):
        attr = getattr(self, '_pending_pick_attr', None)
        if attr:
            spins = getattr(self, attr, [])
            for i, v in enumerate([x1, y1, x2, y2]):
                spins[i].setValue(v)
            self._log(f"[校准] {attr} 已更新: ({x1},{y1})-({x2},{y2})")
        self._restore_after_picker()

    def _start_picker(self, title, initial, callback):
        self.hide()
        self._overlay_was_visible = self._overlay.isVisible()
        if self._overlay_was_visible:
            self._overlay.hide()
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(450, lambda: self._open_picker(title, initial, callback))

    def _open_picker(self, title, initial, callback):
        self._picker = RegionPickerWindow(title=title, initial_region=initial)
        self._picker.region_selected.connect(callback)
        self._picker.cancelled.connect(self._restore_after_picker)
        self._picker.show()

    @pyqtSlot(int, int, int, int)
    def _on_minimap_picked(self, x1, y1, x2, y2):
        for i, v in enumerate([x1, y1, x2, y2]):
            self._cal_mm[i].setValue(v)
        self._log(f"[校准] 小地图区域已更新: ({x1},{y1})-({x2},{y2})")
        self._restore_after_picker()

    @pyqtSlot(int, int, int, int)
    def _on_hud_region_picked(self, x1, y1, x2, y2):
        for i, v in enumerate([x1, y1, x2, y2]):
            self._cal_hud[i].setValue(v)
        self._log(f"[校准] 副本HUD区域已更新: ({x1},{y1})-({x2},{y2})")
        self._restore_after_picker()

    def _restore_after_picker(self):
        self.show()
        if getattr(self, "_overlay_was_visible", False):
            self._overlay.show()

    def _mark_nav_center(self):
        import cv2
        import numpy as np
        import pyautogui
        x1, y1, x2, y2 = [s.value() for s in self._cal_mm]
        px, py = (x1 + x2) // 2, (y1 + y2) // 2
        try:
            shot = pyautogui.screenshot(region=(x1, y1, x2 - x1, y2 - y1))
            bgr = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        except Exception as e:
            QMessageBox.warning(self, "截图失败", str(e))
            return
        best = None
        for path in [ASSETS_DIR / "minimap_bonehand.png", ASSETS_DIR / "minimap_extrahand.png"]:
            if not path.exists():
                continue
            tmpl = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if tmpl is None:
                continue
            if tmpl.shape[0] > 20 and tmpl.shape[1] > 20:
                tmpl = tmpl[4:-4, 4:-4]
            if tmpl.shape[0] > gray.shape[0] or tmpl.shape[1] > gray.shape[1]:
                continue
            res = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
            _, sc, _, loc = cv2.minMaxLoc(res)
            if sc >= 0.30:
                th, tw = tmpl.shape[:2]
                best = (x1 + loc[0] + tw // 2, y1 + loc[1] + th // 2, sc, path.stem)
                break
        if best is None:
            QMessageBox.warning(
                self, "未找到事件图标",
                "在小地图中未检测到事件图标 (bonehand/extrahand)。\n\n"
                "请确认:\n"
                "  ① 角色现在站在副本事件选择界面正中心\n"
                "  ② minimap_bonehand.png 或 minimap_extrahand.png 已上传\n"
                "  ③ 小地图区域已正确框选",
            )
            return
        ix, iy, sc, name = best
        dx, dy = ix - px, iy - py
        reply = QMessageBox.question(
            self, "确认导航偏移",
            f"找到 {name}  (置信度 {sc:.2f})\n"
            f"图标位置: ({ix}, {iy})   参考中心: ({px}, {py})\n\n"
            f"计算偏移:  DX = {dx},  DY = {dy}\n\n"
            "将此偏移保存为导航中心停止位置？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._cal_dx.setValue(float(dx))
            self._cal_dy.setValue(float(dy))
            self._log(f"[校准] 导航偏移已更新: DX={dx} DY={dy}  (记得点保存)")

    def _mark_chest_type_pos(self, dx_spin, dy_spin, chest_label: str):
        """Capture minimap and compute offset for a specific chest type."""
        self._mark_approach_offset(
            template_stems=["icon_health"],
            dx_spin=dx_spin,
            dy_spin=dy_spin,
            dialog_title=f"确认 {chest_label} 接近偏移",
            not_found_msg=(
                f"在小地图中未检测到血泉图标 (icon_health)。\n\n"
                f"请确认:\n"
                f"  ① 角色现在站在 {chest_label} 前（能看到开启提示）\n"
                f"  ② 小地图区域已正确框选\n"
                f"  ③ 血泉图标在小地图中可见"
            ),
        )

    def _mark_chest_pos(self):
        """Capture minimap, find chest_marker (blood-well icon), compute offset."""
        import cv2
        import numpy as np
        import pyautogui
        self._mark_approach_offset(
            template_stems=["icon_health"],
            dx_spin=self._cal_chest_dx,
            dy_spin=self._cal_chest_dy,
            dialog_title="确认宝箱接近偏移",
            not_found_msg=(
                "在小地图中未检测到血泉图标 (icon_health)。\n\n"
                "请确认:\n"
                "  ① 角色现在站在Boss战后宝箱前（能看到开启提示）\n"
                "  ② 小地图区域已正确框选\n"
                "  ③ 血泉图标在小地图中可见"
            ),
        )

    def _mark_boss_door_pos(self):
        """Capture minimap, find bossdoor icon, compute offset."""
        import cv2
        import numpy as np
        import pyautogui
        self._mark_approach_offset(
            template_stems=["icon_bossdoor", "minimap_bossdoor"],
            dx_spin=self._cal_bd_dx,
            dy_spin=self._cal_bd_dy,
            dialog_title="确认Boss门接近偏移",
            not_found_msg=(
                "在小地图中未检测到Boss门图标。\n\n"
                "请确认:\n"
                "  ① 角色现在站在Boss房门前（能看到开启门的提示）\n"
                "  ② 小地图区域已正确框选\n"
                "  ③ Boss门图标 (icon_bossdoor.png) 已上传"
            ),
        )

    def _mark_approach_offset(self, template_stems, dx_spin, dy_spin,
                               dialog_title, not_found_msg):
        """Generic helper: screenshot minimap, find icon, write offset to spinboxes."""
        import cv2
        import numpy as np
        import pyautogui
        x1, y1, x2, y2 = [s.value() for s in self._cal_mm]
        px, py = (x1 + x2) // 2, (y1 + y2) // 2
        try:
            shot = pyautogui.screenshot(region=(x1, y1, x2 - x1, y2 - y1))
            bgr = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        except Exception as e:
            QMessageBox.warning(self, "截图失败", str(e))
            return
        best = None
        for stem in template_stems:
            for suffix in ["", "_v2", "_v3"]:
                path = ASSETS_DIR / f"{stem}{suffix}.png"
                if not path.exists():
                    continue
                tmpl = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
                if tmpl is None:
                    continue
                if tmpl.shape[0] > 20 and tmpl.shape[1] > 20:
                    tmpl = tmpl[4:-4, 4:-4]
                if tmpl.shape[0] > gray.shape[0] or tmpl.shape[1] > gray.shape[1]:
                    continue
                res = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
                _, sc, _, loc = cv2.minMaxLoc(res)
                if sc >= 0.25:
                    th, tw = tmpl.shape[:2]
                    cand = (x1 + loc[0] + tw // 2, y1 + loc[1] + th // 2, sc, path.stem)
                    if best is None or sc > best[2]:
                        best = cand
        if best is None:
            QMessageBox.warning(self, "未找到图标", not_found_msg)
            return
        ix, iy, sc, name = best
        dx, dy = ix - px, iy - py
        reply = QMessageBox.question(
            self, dialog_title,
            f"找到 {name}  (置信度 {sc:.2f})\n"
            f"图标位置: ({ix}, {iy})   小地图中心: ({px}, {py})\n\n"
            f"计算偏移:  DX = {dx},  DY = {dy}\n\n"
            "将此偏移保存？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            dx_spin.setValue(float(dx))
            dy_spin.setValue(float(dy))
            self._log(f"[校准] 接近偏移已更新: DX={dx} DY={dy}  (记得点保存)")

    @staticmethod
    def _cal_spin(value, lo, hi):
        s = _NoScrollSpin()
        s.setRange(lo, hi)
        s.setValue(int(value))
        s.setFixedHeight(28)
        return s

    @staticmethod
    def _cal_dspin(value, lo, hi, step=1.0, decimals=1):
        s = _NoScrollDSpin()
        s.setRange(lo, hi)
        s.setSingleStep(step)
        s.setDecimals(decimals)
        s.setValue(float(value))
        s.setFixedHeight(28)
        return s

    def _load_calibration_dict(self):
        try:
            if CALIBRATION_PATH.exists():
                with open(CALIBRATION_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_calibration(self):
        x1, y1, x2, y2 = [s.value() for s in self._cal_mm]
        px, py = (x1 + x2) // 2, (y1 + y2) // 2
        hud = [s.value() for s in self._cal_hud]
        data = {
            "minimap_region":      [x1, y1, x2, y2],
            "player_pos":          [px, py],
            "instance_hud_region": hud,
            "nav_center_dx":       round(self._cal_dx.value(), 1),
            "nav_center_dy":       round(self._cal_dy.value(), 1),
            "chest_nav_dx":        round(self._cal_chest_dx.value(), 1),
            "chest_nav_dy":        round(self._cal_chest_dy.value(), 1),
            "boss_door_nav_dx":    round(self._cal_bd_dx.value(), 1),
            "boss_door_nav_dy":    round(self._cal_bd_dy.value(), 1),
            # Per-type chest nav offsets
            "equip_chest_nav_dx":      round(self._cal_equip_dx.value(), 1),
            "equip_chest_nav_dy":      round(self._cal_equip_dy.value(), 1),
            "equip_chest_scan_region": [s.value() for s in self._cal_equip_scan],
            "material_chest_nav_dx":   round(self._cal_material_dx.value(), 1),
            "material_chest_nav_dy":   round(self._cal_material_dy.value(), 1),
            "material_chest_scan_region": [s.value() for s in self._cal_material_scan],
            "gold_chest_nav_dx":       round(self._cal_gold_dx.value(), 1),
            "gold_chest_nav_dy":       round(self._cal_gold_dy.value(), 1),
            "gold_chest_scan_region":  [s.value() for s in self._cal_gold_scan],
            "match_threshold":     round(self._cal_thresh.value(), 3),
            "death_scan_region":   [s.value() for s in self._cal_death],
            "modal_scan_region":   [s.value() for s in self._cal_modal],
            "wave_region":         [s.value() for s in self._cal_wave],
            "ether_region":        [s.value() for s in self._cal_ether],
            "event_scan_roi":      [s.value() for s in self._cal_event],
            "inventory_region":    [s.value() for s in self._cal_inv],
            "quest_tracker_region": [s.value() for s in self._cal_quest],
            "boss_door_scan_region": [s.value() for s in self._cal_boss_door_scan],
        }
        CALIBRATION_PATH.parent.mkdir(exist_ok=True)
        with open(CALIBRATION_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self._log(
            f"[校准] 已保存 minimap={data['minimap_region']} "
            f"hud={hud} "
            f"player={data['player_pos']} "
            f"offset=({data['nav_center_dx']},{data['nav_center_dy']})"
        )
        QMessageBox.information(
            self, "保存成功",
            f"已写入 config/calibration.json\n\n"
            f"小地图: ({x1},{y1})-({x2},{y2})\n"
            f"副本HUD: {hud}\n"
            f"玩家中心: ({px},{py})\n"
            f"导航偏移: DX={data['nav_center_dx']} DY={data['nav_center_dy']}\n\n"
            "重启脚本后生效。",
        )

    def _reset_calibration(self):
        for i, v in enumerate([2159, 91, 2523, 352]):
            self._cal_mm[i].setValue(v)
        for i, v in enumerate([1680, 20, 2150, 140]):
            self._cal_hud[i].setValue(v)
        self._cal_dx.setValue(0.0)
        self._cal_dy.setValue(0.0)
        self._cal_thresh.setValue(0.40)
        for attr, default in [
            ("_cal_death", [640, 792, 1920, 1296]),
            ("_cal_modal", [400, 600, 2160, 1200]),
            ("_cal_wave",  [1960, 80, 2100, 120]),
            ("_cal_ether", [1960, 190, 2150, 260]),
            ("_cal_event", [50, 20, 2000, 1420]),
            ("_cal_inv",   [1600, 120, 2550, 1380]),
        ]:
            spins = getattr(self, attr, [])
            for i, v in enumerate(default):
                spins[i].setValue(v)
        self._log("[校准] 已恢复默认值（未保存）")

    # ── General Settings tab ──────────────────────────────────────────────────

    def _make_settings_tab(self):
        """⚙ 通用设置 — chest selection + runs + tribute priority."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(12)

        cfg = load_settings()

        _grp_style = (
            "QGroupBox{font-weight:bold;color:#c6b0d8;"
            "border:1px solid #4a3f5c;border-radius:5px;margin-top:8px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:10px;}"
        )
        _hint_style = "color:#9688a6;font-size:11px;background:transparent;"
        _cb_style    = "color:#d0c8db;background:transparent;"

        # ── Section 0: Movement keys ─────────────────────────────────────────
        grp_move = QGroupBox("🎮  移动键位方案")
        grp_move.setStyleSheet(_grp_style)
        move_layout = QVBoxLayout(grp_move)
        move_layout.setSpacing(4)
        move_layout.setContentsMargins(8, 16, 8, 8)

        move_hint = QLabel(
            "选择角色移动使用的键位方案（导航、巡逻均使用此设置）。\n"
            "保存后立即生效，无需重启。"
        )
        move_hint.setWordWrap(True)
        move_hint.setStyleSheet(_hint_style)
        move_layout.addWidget(move_hint)

        self._rb_arrows = QRadioButton("⬆⬇⬅➡  方向键  (Up / Down / Left / Right)")
        self._rb_wasd   = QRadioButton("⌨  WASD  (W / A / S / D)")
        for rb in (self._rb_arrows, self._rb_wasd):
            rb.setStyleSheet(_cb_style)
        saved_scheme = cfg.get("move_keys", "arrows")
        self._rb_wasd.setChecked(saved_scheme == "wasd")
        self._rb_arrows.setChecked(saved_scheme != "wasd")
        move_layout.addWidget(self._rb_arrows)
        move_layout.addWidget(self._rb_wasd)
        root.addWidget(grp_move)

        # ── Section 1: Run count ──────────────────────────────────────────────
        grp_run = QGroupBox("🔁  运行次数")
        grp_run.setStyleSheet(_grp_style)
        run_layout = QVBoxLayout(grp_run)
        run_layout.setSpacing(6)
        run_layout.setContentsMargins(8, 16, 8, 8)

        run_hint = QLabel(
            "设置 Bot 自动运行罗盘的总次数。\n"
            "0 = 不限次数（持续运行直到手动停止）。\n"
            "运行次数实时显示在左侧状态栏和悬浮框中。"
        )
        run_hint.setWordWrap(True)
        run_hint.setStyleSheet(_hint_style)
        run_layout.addWidget(run_hint)

        run_row = QHBoxLayout()
        run_row.setSpacing(8)
        run_lbl = QLabel("运行次数（0=不限）：")
        run_lbl.setStyleSheet("color:#c6b0d8;background:transparent;")
        run_row.addWidget(run_lbl)
        self._spin_max_runs = _NoScrollSpin()
        self._spin_max_runs.setRange(0, 9999)
        self._spin_max_runs.setValue(int(cfg.get("max_runs", 0)))
        self._spin_max_runs.setFixedWidth(80)
        self._spin_max_runs.setFixedHeight(28)
        run_row.addWidget(self._spin_max_runs)
        run_row.addStretch()
        run_layout.addLayout(run_row)
        root.addWidget(grp_run)

        # ── Section 2: Chest selection (multi-select) ─────────────────────────
        grp_chest = QGroupBox("🗃  宝箱选择（可多选，按装备→材料→金币顺序依次开）")
        grp_chest.setStyleSheet(_grp_style)
        chest_layout = QVBoxLayout(grp_chest)
        chest_layout.setSpacing(4)
        chest_layout.setContentsMargins(8, 16, 8, 8)

        chest_hint = QLabel(
            "勾选要开的宝箱类型（可多选）。\n"
            "开启顺序固定：装备箱（先开，费400以太）→ 材料箱 → 金币箱。\n"
            "全不勾选 = 默认开材料箱。\n"
            "每种箱子最多重试 5 次，失败则跳过继续下一个。\n"
            "每次开箱前后都会经过【屏幕校准②b】中的基准点。\n"
            "需先在【屏幕校准②d-f】校准各宝箱导航偏移，\n"
            "可选在【图片模板】上传各宝箱外观截图（上传后检测更快）。"
        )
        chest_hint.setWordWrap(True)
        chest_hint.setStyleSheet(_hint_style)
        chest_layout.addWidget(chest_hint)

        chest_options = [
            ("equipment", "⚔  装备箱  (chest_equip)"),
            ("material",  "🧪  材料箱  (chest_material)"),
            ("gold",      "💰  金币箱  (chest_gold)"),
        ]
        self._chest_checks: dict[str, QCheckBox] = {}
        saved_sel = set(cfg.get("chest_selection", []))
        for key, label in chest_options:
            cb = QCheckBox(label)
            cb.setStyleSheet(_cb_style)
            cb.setChecked(key in saved_sel)
            chest_layout.addWidget(cb)
            self._chest_checks[key] = cb

        root.addWidget(grp_chest)

        # ── Section 3: Tribute priority ───────────────────────────────────────
        grp_tribute = QGroupBox("🎯  贡品优先类别（可多选）")
        grp_tribute.setStyleSheet(_grp_style)
        trib_layout = QVBoxLayout(grp_tribute)
        trib_layout.setSpacing(4)
        trib_layout.setContentsMargins(8, 16, 8, 8)

        trib_hint = QLabel(
            "勾选希望优先选择的贡品类别。\n"
            "当检测到的贡品中有勾选类别的选项时，优先随机选取其中一个；\n"
            "无匹配（或全不勾选）时，按原始默认优先级选取。"
        )
        trib_hint.setWordWrap(True)
        trib_hint.setStyleSheet(_hint_style)
        trib_layout.addWidget(trib_hint)

        tribute_options = [
            ("混沌贡品",   "🌀  混沌贡品"),
            ("魔裔类",     "👹  魔裔类（含凶魔、魔裔类供品）"),
            ("以太物质类", "💎  以太物质类（以太地精、各类物质）"),
            ("地狱火类",   "🔥  地狱火类"),
            ("魂塔类",     "🗼  魂塔类（各类尖塔）"),
        ]
        self._tribute_checks: dict[str, QCheckBox] = {}
        saved_cats = set(cfg.get("tribute_categories", []))
        for key, label in tribute_options:
            cb = QCheckBox(label)
            cb.setStyleSheet(_cb_style)
            cb.setChecked(key in saved_cats)
            trib_layout.addWidget(cb)
            self._tribute_checks[key] = cb

        root.addWidget(grp_tribute)

        # ── Save button ───────────────────────────────────────────────────────
        btn_save = QPushButton("💾  保存通用设置")
        btn_save.setFixedHeight(34)
        btn_save.clicked.connect(self._save_general_settings)
        root.addWidget(btn_save)

        root.addStretch()
        scroll.setWidget(container)
        return scroll

    def _save_general_settings(self):
        """Persist all general settings to settings.json."""
        move_keys = "wasd" if self._rb_wasd.isChecked() else "arrows"
        chest_sel = [
            key for key, cb in self._chest_checks.items() if cb.isChecked()
        ]
        tribute_cats = [
            key for key, cb in self._tribute_checks.items() if cb.isChecked()
        ]
        max_runs = self._spin_max_runs.value()

        data = {
            "move_keys":          move_keys,
            "chest_selection":    chest_sel,
            "max_runs":           max_runs,
            "tribute_categories": tribute_cats,
        }
        save_settings(data)

        chest_desc = (
            "、".join({"equipment": "装备箱", "material": "材料箱", "gold": "金币箱"}[k]
                      for k in chest_sel) if chest_sel else "默认（材料箱）"
        )
        move_desc = "WASD" if move_keys == "wasd" else "方向键"
        QMessageBox.information(
            self, "保存成功",
            f"移动键位: {move_desc}\n"
            f"运行次数: {'不限' if max_runs == 0 else max_runs}\n"
            f"宝箱选择: {chest_desc}\n"
            f"贡品优先类别: {', '.join(tribute_cats) if tribute_cats else '（默认顺序）'}"
        )

    def _make_log_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Toolbar
        toolbar = QHBoxLayout()
        lbl = QLabel("实时日志 — 最近 1000 条")
        lbl.setStyleSheet("color:#5a5468; font-size:11px; background:transparent;")
        toolbar.addWidget(lbl)
        toolbar.addStretch()
        btn_clear = QPushButton("🗑 清除")
        btn_clear.setFixedWidth(80)
        btn_clear.clicked.connect(self._clear_log)
        toolbar.addWidget(btn_clear)
        btn_copy = QPushButton("📋 复制")
        btn_copy.setFixedWidth(80)
        btn_copy.clicked.connect(self._copy_log)
        toolbar.addWidget(btn_copy)
        layout.addLayout(toolbar)

        self._log_edit = QTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setFont(QFont("Consolas", 11))
        layout.addWidget(self._log_edit)

        return w

    # ── Control bar ───────────────────────────────────────────────────────────

    def _make_control_bar(self):
        bar = QHBoxLayout()
        bar.setSpacing(10)

        self._btn_start = QPushButton("▶  开始  F1")
        self._btn_start.setObjectName("startBtn")
        self._btn_start.setProperty("running", False)
        self._btn_start.clicked.connect(self.toggle_bot)
        bar.addWidget(self._btn_start)

        self._btn_restart = QPushButton("↺  重启  F3")
        self._btn_restart.setObjectName("restartBtn")
        self._btn_restart.clicked.connect(self.restart_bot)
        bar.addWidget(self._btn_restart)

        self._btn_overlay = QPushButton("🪟  浮窗  F4")
        self._btn_overlay.setObjectName("overlayBtn")
        self._btn_overlay.setProperty("active", False)
        self._btn_overlay.clicked.connect(self.toggle_overlay)
        bar.addWidget(self._btn_overlay)

        bar.addStretch()

        self._lbl_hint = QLabel("按 F1 开始脚本 · F3 重启 · F4 切换浮窗")
        self._lbl_hint.setObjectName("hintLabel")
        bar.addWidget(self._lbl_hint)

        return bar

    # ── Hotkeys ───────────────────────────────────────────────────────────────

    def _setup_hotkeys(self):
        """Register global hotkeys using pyqtSignal for thread-safe dispatch."""
        try:
            import keyboard
            # Use signal.emit directly — PyQt5 handles cross-thread delivery
            keyboard.add_hotkey("f1", self._sig_f1.emit)
            keyboard.add_hotkey("f3", self._sig_f3.emit)
            keyboard.add_hotkey("f4", self._sig_f4.emit)
            self._log("[UI] 全局热键已注册: F1=开始/暂停  F3=重启  F4=浮窗")
        except Exception as e:
            self._log(f"[警告] 全局热键注册失败: {e}")

    # ── Bot control ───────────────────────────────────────────────────────────

    @pyqtSlot()
    def toggle_bot(self):
        if self._bot_thread and self._bot_thread.isRunning():
            self.stop_bot()
        else:
            self.start_bot()

    @pyqtSlot()
    def restart_bot(self):
        if self._bot_thread and self._bot_thread.isRunning():
            self._log("[UI] 重启脚本…")
            self._bot_thread.stop()
            self._bot_thread.finished_signal.connect(self.start_bot)
        else:
            self.start_bot()

    def start_bot(self):
        if self._bot_thread and self._bot_thread.isRunning():
            return

        lang = "en" if self._lang_combo.currentIndex() == 1 else "cn"
        self._log(f"[UI] 启动脚本 (语言={lang})…")
        self._overlay.clear_log()

        self._bot_thread = BotThread(lang=lang, parent=self)
        self._bot_thread.log_signal.connect(self._on_bot_log)
        self._bot_thread.state_signal.connect(self._on_bot_state)
        self._bot_thread.quest_signal.connect(self._overlay.update_quest)
        self._bot_thread.run_count_signal.connect(self._overlay.update_run_count)
        self._bot_thread.finished_signal.connect(self._on_bot_finished)
        self._bot_thread.start()

        self._set_running_ui(True)

    def stop_bot(self):
        if self._bot_thread and self._bot_thread.isRunning():
            self._log("[UI] 停止脚本中…（当前操作执行完毕后生效）")
            self._bot_thread.stop()
            # Immediately show "stopping" state — bot may still be finishing an action
            self._overlay.set_stopping()
            self._btn_start.setText("⏳  停止中…")
            self._btn_start.setEnabled(False)

    @pyqtSlot()
    def _on_bot_finished(self):
        self._set_running_ui(False)
        self._overlay.set_paused()
        self._log("[UI] 脚本已停止")

    def _set_running_ui(self, running: bool):
        self._btn_start.setEnabled(True)
        self._btn_start.setProperty("running", running)
        self._btn_start.setText("⏸  暂停  F1" if running else "▶  开始  F1")
        self._btn_start.style().unpolish(self._btn_start)
        self._btn_start.style().polish(self._btn_start)

        self._lbl_dot.setStyleSheet(
            f"font-size:18px; background:transparent; "
            f"color:{'#4caf50' if running else '#3a3a4a'};"
        )
        if running:
            self._overlay.set_running(True)

        # Hide the entire window while running; restore when paused/stopped.
        if running:
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    # ── Overlay ───────────────────────────────────────────────────────────────

    @pyqtSlot()
    def toggle_overlay(self):
        if self._overlay.isVisible():
            self._overlay.hide()
            self._btn_overlay.setProperty("active", False)
        else:
            self._overlay.show()
            self._overlay.raise_()
            self._btn_overlay.setProperty("active", True)
        self._btn_overlay.style().unpolish(self._btn_overlay)
        self._btn_overlay.style().polish(self._btn_overlay)

    # ── Log handling ──────────────────────────────────────────────────────────

    @pyqtSlot(str)
    def _on_bot_log(self, line: str):
        self._log(line)
        self._overlay.append_log(line)

    @pyqtSlot(str, int, int, int, str)
    def _on_bot_state(self, state: str, compass: int, wave_curr: int,
                      wave_max: int, ether: str):
        label = STATE_LABELS_CN.get(state, state)
        color = STATE_COLORS.get(state, "#888888")
        self._lbl_state.setText(label)
        self._lbl_state.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{color}; "
            f"padding:3px 8px; border:1px solid #2a2040; "
            f"border-radius:3px; background-color:#111120;"
        )
        self._overlay.update_state(state, compass, wave_curr, wave_max, ether)

    def _log(self, line: str):
        ts = datetime.now().strftime("%H:%M:%S")
        full = f"[{ts}] {line}"
        self._log_lines.append(full)
        if len(self._log_lines) > MAX_LOG_LINES:
            self._log_lines = self._log_lines[-MAX_LOG_LINES:]

        # Color-code lines
        if "[ERROR]" in line or "错误" in line:
            color = "#e05050"
        elif "✅" in line or "成功" in line or "完成" in line:
            color = "#4caf50"
        elif "[UI]" in line:
            color = "#9070d0"
        elif "⚠" in line or "警告" in line or "[警告]" in line:
            color = "#e0a030"
        else:
            color = "#78c878"

        html = (
            f'<span style="color:#3a5a3a;">[{ts}]</span> '
            f'<span style="color:{color};">{_html_escape(line)}</span>'
        )
        self._log_edit.append(html)
        cursor = self._log_edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._log_edit.setTextCursor(cursor)

    def _clear_log(self):
        self._log_lines.clear()
        self._log_edit.clear()
        self._overlay.clear_log()

    def _copy_log(self):
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText("\n".join(self._log_lines))
        self._log("[UI] 日志已复制到剪贴板")

    # ── Template refresh ──────────────────────────────────────────────────────

    def _refresh_templates(self):
        for row in self._template_rows:
            row.refresh()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _on_lang_changed(self, _idx):
        pass  # Language is read when bot starts

    def _set_icon(self):
        icon_path = ASSETS_DIR / "icon_compass.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def closeEvent(self, event):
        self.stop_bot()
        self._overlay.hide()
        try:
            import keyboard
            keyboard.unhook_all()
        except Exception:
            pass
        event.accept()


def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )
