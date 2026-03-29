"""Full-screen interactive region selector for screen calibration.

Usage
-----
    picker = RegionPickerWindow(
        title="选择小地图区域",
        initial_region=(2159, 91, 2523, 352),   # x1,y1,x2,y2  (optional)
    )
    picker.region_selected.connect(my_callback)   # emits (x1,y1,x2,y2)
    picker.cancelled.connect(lambda: ...)
    picker.show()

Flow
----
1. A screenshot of the entire desktop is captured the moment the window is shown.
2. A semi-transparent dark overlay is drawn over everything.
3. The selected rectangle is drawn "clear" (screenshot shows through at full brightness).
4. User can:
   - Drag inside the rect  → move
   - Drag a resize handle  → resize
   - Drag outside the rect → draw a new rect from scratch
   - Press Enter / double-click → confirm
   - Press Esc              → cancel
"""

from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtCore import Qt, QRect, QPoint, QRectF, pyqtSignal
from PyQt5.QtGui import (
    QPainter, QColor, QFont, QPen, QPixmap, QPainterPath,
    QBrush, QCursor,
)

# ── constants ─────────────────────────────────────────────────────────────────
_HR = 7        # handle circle radius  (px)
_MIN_SZ = 20   # minimum rect dimension (px)

# 8 handle positions as lambdas QRect → QPoint
_HANDLES: dict[str, callable] = {
    'nw': lambda r: r.topLeft(),
    'n':  lambda r: QPoint(r.center().x(), r.top()),
    'ne': lambda r: r.topRight(),
    'e':  lambda r: QPoint(r.right(), r.center().y()),
    'se': lambda r: r.bottomRight(),
    's':  lambda r: QPoint(r.center().x(), r.bottom()),
    'sw': lambda r: r.bottomLeft(),
    'w':  lambda r: QPoint(r.left(), r.center().y()),
}

_HANDLE_CURSORS: dict[str, Qt.CursorShape] = {
    'nw': Qt.SizeFDiagCursor,  'n': Qt.SizeVerCursor,
    'ne': Qt.SizeBDiagCursor,  'e': Qt.SizeHorCursor,
    'se': Qt.SizeFDiagCursor,  's': Qt.SizeVerCursor,
    'sw': Qt.SizeBDiagCursor,  'w': Qt.SizeHorCursor,
}

_COL_GOLD    = QColor(255, 200, 50)
_COL_OVERLAY = QColor(0, 0, 0, 145)
_COL_SHADOW  = QColor(0, 0, 0, 200)


class RegionPickerWindow(QWidget):
    """Full-screen screenshot-based interactive region picker."""

    region_selected = pyqtSignal(int, int, int, int)  # x1, y1, x2, y2
    cancelled = pyqtSignal()

    def __init__(self, title: str = "选择区域",
                 initial_region: tuple = None, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setMouseTracking(True)

        self._title = title
        self._screenshot: QPixmap | None = None

        # Drag state
        self._drag_mode: str | None = None     # 'move' | 'draw' | handle-name
        self._drag_origin: QPoint | None = None
        self._sel_at_drag: QRect | None = None

        # Cover full primary screen
        screen_geo = QApplication.primaryScreen().geometry()
        self.setGeometry(screen_geo)

        # Initial selection rectangle
        if initial_region:
            x1, y1, x2, y2 = initial_region
            self._sel = QRect(x1, y1, x2 - x1, y2 - y1).normalized()
        else:
            cx, cy = screen_geo.width() // 2, screen_geo.height() // 2
            self._sel = QRect(cx - 180, cy - 120, 360, 240)

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def showEvent(self, event):
        # Grab desktop AFTER we are shown (our own window appears transparent until
        # the first paint, so the grab will show the game beneath us).
        self._screenshot = QApplication.primaryScreen().grabWindow(0)
        self.update()
        super().showEvent(event)

    # ── painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        if self._screenshot is None:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        sel = self._sel.normalized()

        # 1 · Full screenshot as background
        p.drawPixmap(0, 0, self._screenshot)

        # 2 · Dark semi-transparent overlay everywhere
        p.fillRect(0, 0, w, h, _COL_OVERLAY)

        # 3 · "Hole" — redraw screenshot inside selection without the overlay
        clip = QPainterPath()
        clip.addRect(QRectF(sel))
        p.setClipPath(clip)
        p.drawPixmap(0, 0, self._screenshot)
        p.setClipping(False)

        # 4 · Selection border (dashed gold line)
        pen = QPen(_COL_GOLD, 2, Qt.DashLine)
        pen.setDashPattern([6, 3])
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(sel)

        # 5 · Resize handles (filled gold circles)
        p.setPen(QPen(QColor(30, 20, 0), 1))
        p.setBrush(QBrush(_COL_GOLD))
        for pos_fn in _HANDLES.values():
            pt = pos_fn(sel)
            p.drawEllipse(pt, _HR, _HR)

        # 6 · Coordinate readout inside the selection
        coords = (f"({sel.x()}, {sel.y()})  →  ({sel.right()}, {sel.bottom()})"
                  f"     {sel.width()} × {sel.height()} px")
        coord_font = QFont("Consolas", 11, QFont.Bold)
        p.setFont(coord_font)
        tx, ty = sel.x() + 8, sel.y() + 22
        p.setPen(_COL_SHADOW)
        p.drawText(tx + 1, ty + 1, coords)
        p.setPen(_COL_GOLD)
        p.drawText(tx, ty, coords)

        # 7 · Top instruction bar
        p.fillRect(0, 0, w, 50, QColor(0, 0, 0, 170))
        title_font = QFont("Microsoft YaHei UI", 13, QFont.Bold)
        p.setFont(title_font)
        p.setPen(_COL_GOLD)
        p.drawText(14, 32, f"⚔  {self._title}")

        hint_font = QFont("Microsoft YaHei UI", 10)
        p.setFont(hint_font)
        p.setPen(QColor(190, 190, 190))
        hint = "拖拽中心移动  |  拖拽圆点调整大小  |  在外部拖拽重画  |  Enter / 双击 确认  |  Esc 取消"
        p.drawText(w // 2 - 340, 32, hint)

    # ── mouse interactions ────────────────────────────────────────────────────

    def _handle_at(self, pos: QPoint) -> str | None:
        sel = self._sel.normalized()
        for name, pos_fn in _HANDLES.items():
            hp = pos_fn(sel)
            if abs(pos.x() - hp.x()) <= _HR + 4 and abs(pos.y() - hp.y()) <= _HR + 4:
                return name
        return None

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        pos = event.pos()
        handle = self._handle_at(pos)
        if handle:
            self._drag_mode = handle
        elif self._sel.normalized().contains(pos):
            self._drag_mode = 'move'
        else:
            self._drag_mode = 'draw'
        self._drag_origin = pos
        self._sel_at_drag = QRect(self._sel.normalized())

    def mouseMoveEvent(self, event):
        pos = event.pos()

        if not (event.buttons() & Qt.LeftButton):
            # Hover: update cursor only
            handle = self._handle_at(pos)
            if handle:
                self.setCursor(_HANDLE_CURSORS[handle])
            elif self._sel.normalized().contains(pos):
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(Qt.CrossCursor)
            return

        if self._drag_mode is None or self._drag_origin is None:
            return

        dx = pos.x() - self._drag_origin.x()
        dy = pos.y() - self._drag_origin.y()
        r = QRect(self._sel_at_drag)

        if self._drag_mode == 'move':
            r.translate(dx, dy)
            self._sel = r
        elif self._drag_mode == 'draw':
            x1 = min(self._drag_origin.x(), pos.x())
            y1 = min(self._drag_origin.y(), pos.y())
            x2 = max(self._drag_origin.x(), pos.x())
            y2 = max(self._drag_origin.y(), pos.y())
            self._sel = QRect(x1, y1, x2 - x1, y2 - y1)
        else:
            self._sel = _apply_handle_drag(r, self._drag_mode, dx, dy)

        self.update()

    def mouseReleaseEvent(self, _event):
        self._drag_mode = None
        self._sel = _clamp(self._sel.normalized(), _MIN_SZ)
        self.update()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._confirm()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._confirm()
        elif event.key() == Qt.Key_Escape:
            self.cancelled.emit()
            self.close()

    # ── confirm ───────────────────────────────────────────────────────────────

    def _confirm(self):
        r = self._sel.normalized()
        self.region_selected.emit(r.x(), r.y(), r.right(), r.bottom())
        self.close()


# ── helpers ───────────────────────────────────────────────────────────────────

def _apply_handle_drag(r: QRect, handle: str, dx: int, dy: int) -> QRect:
    x1, y1, x2, y2 = r.left(), r.top(), r.right(), r.bottom()
    if 'n' in handle: y1 = min(y1 + dy, y2 - _MIN_SZ)
    if 's' in handle: y2 = max(y2 + dy, y1 + _MIN_SZ)
    if 'w' in handle: x1 = min(x1 + dx, x2 - _MIN_SZ)
    if 'e' in handle: x2 = max(x2 + dx, x1 + _MIN_SZ)
    return QRect(x1, y1, x2 - x1, y2 - y1)


def _clamp(r: QRect, min_sz: int) -> QRect:
    return QRect(r.x(), r.y(),
                 max(r.width(), min_sz),
                 max(r.height(), min_sz))
