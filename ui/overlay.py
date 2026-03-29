"""Floating always-on-top overlay window for in-game status and logs.

Positioned at the top-left of the primary screen.
Toggle visibility with F4 (wired up by MainWindow).
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QPushButton, QSizeGrip, QFrame,
)
from PyQt5.QtCore import Qt, QPoint, pyqtSlot
from PyQt5.QtGui import QFont, QColor, QPalette, QTextCursor

from ui.styles import STATE_COLORS, STATE_LABELS_CN

MAX_LOG_LINES = 200
OVERLAY_WIDTH = 340
OVERLAY_HEIGHT = 460


class OverlayWindow(QWidget):
    """Semi-transparent, frameless, always-on-top status overlay."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(0.93)
        self.setMinimumWidth(280)
        self.setMinimumHeight(200)
        self.resize(OVERLAY_WIDTH, OVERLAY_HEIGHT)

        self._drag_pos: QPoint | None = None
        self._log_lines: list[str] = []

        self._build_ui()
        self._position_top_left()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Container card
        self._card = QFrame(self)
        self._card.setObjectName("overlayCard")
        self._card.setStyleSheet("""
            QFrame#overlayCard {
                background-color: rgba(7, 7, 18, 230);
                border: 1px solid #2e2448;
                border-radius: 8px;
            }
        """)

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(10, 8, 10, 8)
        card_layout.setSpacing(6)

        # ── Title bar ──
        title_bar = QHBoxLayout()
        title_bar.setSpacing(6)

        self._lbl_title = QLabel("⚔  D4 AUTO")
        self._lbl_title.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #c9a227; "
            "letter-spacing: 2px; background: transparent;"
        )

        self._btn_close = QPushButton("×")
        self._btn_close.setFixedSize(22, 22)
        self._btn_close.setStyleSheet("""
            QPushButton {
                background: transparent; border: none;
                color: #6a5060; font-size: 16px; font-weight: bold;
                border-radius: 11px; padding: 0;
            }
            QPushButton:hover { color: #ff6060; background: rgba(80,20,20,160); }
        """)
        self._btn_close.clicked.connect(self.hide)

        title_bar.addWidget(self._lbl_title)
        title_bar.addStretch()
        title_bar.addWidget(self._btn_close)
        card_layout.addLayout(title_bar)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("color: #2e2448; background: #2e2448; max-height: 1px;")
        card_layout.addWidget(div)

        # ── Pause banner (hidden when running normally) ──
        self._pause_banner = QLabel("")
        self._pause_banner.setAlignment(Qt.AlignCenter)
        self._pause_banner.setWordWrap(False)
        self._pause_banner.setStyleSheet("""
            QLabel {
                background: rgba(180, 60, 0, 190);
                color: #ffe080;
                font-size: 13px;
                font-weight: bold;
                border-radius: 4px;
                padding: 5px 10px;
                letter-spacing: 1px;
            }
        """)
        self._pause_banner.hide()
        card_layout.addWidget(self._pause_banner)

        # ── State row ──
        state_row = QHBoxLayout()
        state_row.setSpacing(6)
        state_lbl = QLabel("状态")
        state_lbl.setStyleSheet("color: #5a5068; font-size: 11px; background: transparent;")
        self._lbl_state = QLabel("IDLE")
        self._lbl_state.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #888; background: transparent;"
        )
        state_row.addWidget(state_lbl)
        state_row.addWidget(self._lbl_state)
        state_row.addStretch()
        # Combat badge
        self._lbl_combat = QLabel("⬜ 待机")
        self._lbl_combat.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #557755; background: transparent; "
            "padding: 1px 5px; border-radius: 3px;"
        )
        state_row.addWidget(self._lbl_combat)
        self._lbl_running = QLabel("●")
        self._lbl_running.setStyleSheet("font-size: 16px; color: #555; background: transparent;")
        state_row.addWidget(self._lbl_running)
        card_layout.addLayout(state_row)

        # ── Info row (compass / wave / ether) ──
        info_row = QHBoxLayout()
        info_row.setSpacing(10)

        def _info_pair(icon, value_attr):
            lbl_icon = QLabel(icon)
            lbl_icon.setStyleSheet("color: #6a5c3c; font-size: 11px; background: transparent;")
            lbl_val = QLabel("—")
            lbl_val.setStyleSheet("color: #c8baa0; font-size: 12px; background: transparent;")
            setattr(self, value_attr, lbl_val)
            info_row.addWidget(lbl_icon)
            info_row.addWidget(lbl_val)

        _info_pair("罗盘", "_lbl_compass")
        _info_pair("  波次", "_lbl_wave")
        _info_pair("  以太", "_lbl_ether")
        info_row.addStretch()
        card_layout.addLayout(info_row)

        # ── Run counter row ──
        run_row = QHBoxLayout()
        run_row.setSpacing(4)
        run_icon = QLabel("🔁")
        run_icon.setStyleSheet("font-size: 11px; background: transparent;")
        self._lbl_run_count = QLabel("第 0 次")
        self._lbl_run_count.setStyleSheet(
            "font-size: 11px; color: #f0c060; background: transparent; font-weight: bold;"
        )
        run_row.addWidget(run_icon)
        run_row.addWidget(self._lbl_run_count)
        run_row.addStretch()
        card_layout.addLayout(run_row)

        # ── Quest-tracker strip (always visible) ──
        quest_row = QHBoxLayout()
        quest_row.setSpacing(4)
        quest_icon = QLabel("📋")
        quest_icon.setStyleSheet("font-size: 11px; background: transparent;")
        self._lbl_quest = QLabel("—")
        self._lbl_quest.setStyleSheet(
            "font-size: 11px; color: #a0d0ff; background: transparent;"
        )
        self._lbl_quest.setWordWrap(True)
        quest_row.addWidget(quest_icon)
        quest_row.addWidget(self._lbl_quest, 1)
        card_layout.addLayout(quest_row)

        # ── Log area ──
        log_header = QLabel("📋 日志")
        log_header.setStyleSheet(
            "color: #5a5068; font-size: 11px; margin-top: 2px; background: transparent;"
        )
        card_layout.addWidget(log_header)

        self._log_edit = QTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setStyleSheet("""
            QTextEdit {
                background-color: rgba(4, 4, 12, 200);
                color: #70c870;
                border: 1px solid #1a2a1a;
                border-radius: 3px;
                font-family: Consolas, "Courier New", monospace;
                font-size: 11px;
                padding: 4px;
            }
        """)
        card_layout.addWidget(self._log_edit)

        # Size grip
        grip_row = QHBoxLayout()
        grip_row.addStretch()
        grip = QSizeGrip(self._card)
        grip.setStyleSheet("background: transparent;")
        grip_row.addWidget(grip)
        card_layout.addLayout(grip_row)

        outer.addWidget(self._card)

    def _position_top_left(self):
        from PyQt5.QtWidgets import QApplication
        desktop = QApplication.primaryScreen().availableGeometry()
        self.move(desktop.x() + 12, desktop.y() + 12)

    # ── Public slots ─────────────────────────────────────────────────────────

    @pyqtSlot(str, int, int, int, str)
    def update_state(self, state: str, compass: int, wave_curr: int,
                     wave_max: int, ether: str):
        color = STATE_COLORS.get(state, "#888888")
        label = STATE_LABELS_CN.get(state, state)
        self._lbl_state.setText(label)
        self._lbl_state.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {color}; background: transparent;"
        )
        self._lbl_running.setStyleSheet(
            f"font-size: 16px; color: {color}; background: transparent;"
        )
        self._lbl_compass.setText(f"#{compass}")
        self._lbl_wave.setText(f"{wave_curr}/{wave_max}")
        self._lbl_ether.setText(ether)
        # Combat badge
        if state == "COMBAT":
            self._lbl_combat.setText("⚔ 战斗中")
            self._lbl_combat.setStyleSheet(
                "font-size: 11px; font-weight: bold; color: #ff6060; background: transparent; "
                "padding: 1px 5px; border-radius: 3px;"
            )
        else:
            self._lbl_combat.setText("✅ 待机")
            self._lbl_combat.setStyleSheet(
                "font-size: 11px; font-weight: bold; color: #60c060; background: transparent; "
                "padding: 1px 5px; border-radius: 3px;"
            )

    @pyqtSlot(str)
    def update_quest(self, text: str):
        """Update the persistent quest-tracker label."""
        display = text if text else "—"
        self._lbl_quest.setText(display)

    @pyqtSlot(int, int)
    def update_run_count(self, current: int, max_runs: int):
        """Update the run-counter label."""
        if max_runs > 0:
            self._lbl_run_count.setText(f"第 {current}/{max_runs} 次")
        else:
            self._lbl_run_count.setText(f"第 {current} 次（不限）")

    @pyqtSlot(str)
    def append_log(self, line: str):
        self._log_lines.append(line)
        if len(self._log_lines) > MAX_LOG_LINES:
            self._log_lines = self._log_lines[-MAX_LOG_LINES:]

        self._log_edit.append(
            f'<span style="color:#556655;">[{len(self._log_lines):03d}]</span> '
            f'<span style="color:#70c870;">{_html_escape(line)}</span>'
        )
        # Auto-scroll to bottom
        cursor = self._log_edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._log_edit.setTextCursor(cursor)

    def set_running(self, running: bool):
        """Called when the bot thread actually starts running."""
        self._pause_banner.hide()
        color = "#4caf50" if running else "#555"
        self._lbl_running.setStyleSheet(
            f"font-size: 16px; color: {color}; background: transparent;"
        )

    def set_stopping(self):
        """Called immediately when stop is requested — thread may still be finishing."""
        self._pause_banner.setText("⏳  正在停止…  请稍候")
        self._pause_banner.setStyleSheet("""
            QLabel {
                background: rgba(140, 90, 0, 200);
                color: #ffe080;
                font-size: 13px;
                font-weight: bold;
                border-radius: 4px;
                padding: 5px 10px;
                letter-spacing: 1px;
            }
        """)
        self._pause_banner.show()
        self._lbl_running.setStyleSheet(
            "font-size: 16px; color: #c09020; background: transparent;"
        )

    def set_paused(self):
        """Called when the bot thread has fully stopped."""
        self._pause_banner.setText("⏸  已暂停  —  按 F1 或点击开始继续")
        self._pause_banner.setStyleSheet("""
            QLabel {
                background: rgba(60, 20, 20, 220);
                color: #ff8080;
                font-size: 13px;
                font-weight: bold;
                border-radius: 4px;
                padding: 5px 10px;
                letter-spacing: 1px;
            }
        """)
        self._pause_banner.show()
        self._lbl_running.setStyleSheet(
            "font-size: 16px; color: #555; background: transparent;"
        )

    def clear_log(self):
        self._log_lines.clear()
        self._log_edit.clear()

    # ── Drag to move ─────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


# ── helpers ───────────────────────────────────────────────────────────────────

def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )
