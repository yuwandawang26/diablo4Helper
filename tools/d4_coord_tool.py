#!/usr/bin/env python3
"""
D4 坐标工具（唯一入口）
  ① 全局扫描  ② 自动移动验证  ③ 自动指针链（可选） ④ 实时显示 XYZ（锁定配置后）

管理员运行：python d4_coord_tool.py
或双击 launch_d4_tool.bat
"""
from __future__ import annotations

import ctypes
import json
import sys
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QProgressBar, QFrame, QSizeGrip, QTabWidget,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QTextCursor

_TOOLS = Path(__file__).parent
OFFSETS_FILE = _TOOLS / "d4_offsets.json"

# ── 复用现有实现（不删旧文件，仅作库）────────────────────────────────────────
from mem_scanner_ui import ScanWorker
from live_xyz import AutoTester, _load_targets
from coord_wizard import PointerChainWorker

try:
    from d4reader import D4Reader
except Exception:
    D4Reader = None  # type: ignore

LEVEL = {"info": "#a0c8e0", "ok": "#70ff70", "warn": "#f0c050", "err": "#ff6060"}


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


class CoordToolWindow(QWidget):
    """单窗口：多标签 + 顶部一键流程 + 实时坐标区"""

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(0.97)
        self.resize(560, 640)
        self._drag = None
        self._log_n = 0

        self._scan: QThread | None = None
        self._test: QThread | None = None
        self._chain: QThread | None = None
        self._reader = None
        self._pipe_running = False

        self._build_ui()
        geo = QApplication.primaryScreen().availableGeometry()
        self.move(geo.x() + 10, geo.y() + 10)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setStyleSheet(
            "QFrame{background:rgba(8,8,20,240);border:1px solid #2e2448;border-radius:10px;}"
        )
        root = QVBoxLayout(card)
        root.setContentsMargins(12, 10, 12, 10)

        # 标题 + 一键
        top = QHBoxLayout()
        title = QLabel("D4 坐标工具")
        title.setStyleSheet("color:#c9a227;font-size:16px;font-weight:bold;letter-spacing:2px;")
        self._btn_pipe = QPushButton("一键：扫描 → 验证 → 指针链")
        self._btn_pipe.setStyleSheet(
            "QPushButton{background:#1a3d1a;border:1px solid #3a8c3a;color:#7fdf7f;"
            "font-weight:bold;padding:8px 14px;border-radius:6px;}"
            "QPushButton:hover{background:#224822;border-color:#5fcf5f;}"
            "QPushButton:disabled{background:#222;color:#555;border-color:#333;}"
        )
        self._btn_pipe.clicked.connect(self._run_pipeline)
        self._btn_stop = QPushButton("停止")
        self._btn_stop.setStyleSheet(
            "QPushButton{background:#3d1a1a;border:1px solid #8c3a3a;color:#ff9090;padding:8px 12px;}"
        )
        self._btn_stop.clicked.connect(self._stop_all)
        bx = QLabel("×")
        bx.setStyleSheet("color:#666;font-size:18px;font-weight:bold;padding:4px;")
        bx.mousePressEvent = lambda e: self.close()
        top.addWidget(title)
        top.addStretch()
        top.addWidget(self._btn_pipe)
        top.addWidget(self._btn_stop)
        top.addWidget(bx)
        root.addLayout(top)

        sub = QLabel("游戏需运行；扫描前站开阔处。锁定后切到「实时监控」可看走动数值。")
        sub.setStyleSheet("color:#5a6078;font-size:11px;")
        sub.setWordWrap(True)
        root.addWidget(sub)

        # 实时坐标大字（始终可见）
        coord_box = QFrame()
        coord_box.setStyleSheet(
            "QFrame{background:rgba(6,18,12,200);border:1px solid #1a3a28;border-radius:8px;padding:8px;}"
        )
        cb = QVBoxLayout(coord_box)
        self._lbl_coord_title = QLabel("实时坐标（配置有效时自动刷新）")
        self._lbl_coord_title.setStyleSheet("color:#5a8a6a;font-size:11px;")
        row = QHBoxLayout()
        self._lbl_x = QLabel("X —")
        self._lbl_z = QLabel("Z —")
        self._lbl_y = QLabel("Y —")
        for w in (self._lbl_x, self._lbl_z, self._lbl_y):
            w.setStyleSheet(
                "color:#7fef9a;font-size:22px;font-weight:bold;font-family:Consolas;"
            )
        row.addWidget(QLabel("X")); row.addWidget(self._lbl_x)
        row.addSpacing(16)
        row.addWidget(QLabel("Z")); row.addWidget(self._lbl_z)
        row.addSpacing(16)
        row.addWidget(QLabel("Y(高)")); row.addWidget(self._lbl_y)
        row.addStretch()
        cb.addWidget(self._lbl_coord_title)
        cb.addLayout(row)
        self._lbl_mon_status = QLabel("未连接 / 无配置")
        self._lbl_mon_status.setStyleSheet("color:#888;font-size:10px;")
        cb.addWidget(self._lbl_mon_status)
        root.addWidget(coord_box)

        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._tick_monitor)
        self._timer.start()

        # 标签页
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            "QTabWidget::pane{border:1px solid #2a2040;border-radius:6px;}"
            "QTabBar::tab{padding:8px 14px;color:#888;}"
            "QTabBar::tab:selected{color:#c9a227;font-weight:bold;}"
        )
        root.addWidget(self._tabs, 1)

        # Tab 扫描
        t_scan = QWidget()
        ts = QVBoxLayout(t_scan)
        self._prog_scan = QProgressBar()
        self._prog_scan.setRange(0, 100)
        self._prog_scan.setFixedHeight(6)
        self._st_scan = QLabel("就绪")
        self._st_scan.setStyleSheet("color:#5090d0;")
        row_s = QHBoxLayout()
        self._btn_scan_full = QPushButton("完整扫描")
        self._btn_scan_resume = QPushButton("继续筛选（已有快照）")
        self._btn_scan_full.clicked.connect(lambda: self._start_scan(False))
        self._btn_scan_resume.clicked.connect(lambda: self._start_scan(True))
        row_s.addWidget(self._btn_scan_full)
        row_s.addWidget(self._btn_scan_resume)
        ts.addLayout(row_s)
        ts.addWidget(self._st_scan)
        ts.addWidget(self._prog_scan)
        self._log_scan = QTextEdit()
        self._log_scan.setReadOnly(True)
        self._log_scan.setStyleSheet(
            "QTextEdit{background:#050510;color:#70c870;font-family:Consolas;font-size:11px;}"
        )
        ts.addWidget(self._log_scan)
        self._tabs.addTab(t_scan, "① 扫描")

        # Tab 验证
        t_test = QWidget()
        tt = QVBoxLayout(t_test)
        self._btn_test = QPushButton("自动移动验证（需 keyboard）")
        self._btn_test.clicked.connect(self._start_test)
        tt.addWidget(self._btn_test)
        self._log_test = QTextEdit()
        self._log_test.setReadOnly(True)
        self._log_test.setStyleSheet(self._log_scan.styleSheet())
        tt.addWidget(self._log_test)
        self._tabs.addTab(t_test, "② 验证")

        # Tab 指针链
        t_chain = QWidget()
        tc = QVBoxLayout(t_chain)
        self._btn_chain = QPushButton("自动查找指针链（较慢）")
        self._btn_chain.clicked.connect(self._start_chain)
        self._prog_chain = QProgressBar()
        self._prog_chain.setRange(0, 100)
        self._prog_chain.setFixedHeight(5)
        tc.addWidget(self._btn_chain)
        tc.addWidget(self._prog_chain)
        self._log_chain = QTextEdit()
        self._log_chain.setReadOnly(True)
        self._log_chain.setStyleSheet(self._log_scan.styleSheet())
        tc.addWidget(self._log_chain)
        self._tabs.addTab(t_chain, "③ 指针链")

        # Tab 说明
        t_help = QWidget()
        th = QVBoxLayout(t_help)
        help_lbl = QLabel(
            "流程说明：\n\n"
            "1）「一键」或先 ① 再 ②：得到本局 dynamic 地址（已写入 d4_offsets.json）。\n"
            "2）③ 尝试自动指针链；失败则用 Cheat Engine 扫指针，把 offsets 填进 JSON。\n"
            "3）上方大字为实时 XYZ；重开游戏后若只有 pointer_chain 仍有效。\n\n"
            "本工具整合原 mem_scanner_ui / live_xyz / coord_wizard，旧脚本仍可作库调用。"
        )
        help_lbl.setStyleSheet("color:#a8a0c0;font-size:12px;")
        help_lbl.setWordWrap(True)
        th.addWidget(help_lbl)
        self._tabs.addTab(t_help, "说明")

        grip = QHBoxLayout()
        grip.addStretch()
        grip.addWidget(QSizeGrip(card))
        root.addLayout(grip)

        outer.addWidget(card)

    def _append(self, tab: str, level: str, msg: str):
        self._log_n += 1
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        c = LEVEL.get(level, "#a0c8e0")
        line = (
            f'<span style="color:#445;">[{self._log_n:03d} {ts}]</span> '
            f'<span style="color:{c};">{_esc(msg)}</span>'
        )
        log = {"scan": self._log_scan, "test": self._log_test, "chain": self._log_chain}.get(tab)
        if log:
            log.append(line)
            cur = log.textCursor()
            cur.movePosition(QTextCursor.End)
            log.setTextCursor(cur)

    def _start_scan(self, skip: bool):
        self._append("scan", "info", "开始扫描…" + ("（跳过快照）" if skip else ""))
        self._st_scan.setText("扫描中…")
        self._scan = ScanWorker(skip_snapshot=skip)
        self._scan.log.connect(lambda lev, m: self._append("scan", lev, m))
        self._scan.status.connect(self._st_scan.setText)
        self._scan.progress.connect(lambda p, n: self._prog_scan.setValue(min(100, p)))
        self._scan.done.connect(self._on_scan_done)
        self._scan.start()

    def _on_scan_done(self, ok: bool, msg: str):
        self._append("scan", "ok" if ok else "warn", msg)
        self._st_scan.setText("扫描结束")

    def _start_test(self):
        targets = _load_targets()
        if not targets:
            self._append("test", "err", "无候选，请先完成扫描")
            return
        self._append("test", "info", f"加载 {len(targets)} 个候选，开始自动验证…")
        self._test = AutoTester(targets)
        self._test.log.connect(lambda lev, m: self._append("test", lev, m))
        self._test.status.connect(lambda s: None)
        self._test.finished.connect(self._reload_reader)
        self._test.finished.connect(lambda: self._append("test", "ok", "验证线程结束"))
        self._test.start()

    def _start_chain(self):
        if not OFFSETS_FILE.exists():
            self._append("chain", "err", "无 d4_offsets.json")
            return
        data = json.loads(OFFSETS_FILE.read_text("utf-8"))
        cur = data.get("current", {})
        z_s = cur.get("player_z_addr") or cur.get("player_coord_addr_dynamic")
        if not z_s:
            self._append("chain", "err", "无 player_z_addr，请先运行验证")
            return
        z_addr = int(str(z_s), 16)
        self._chain = PointerChainWorker(z_addr)
        self._chain.log.connect(lambda lev, m: self._append("chain", lev, m))
        self._chain.progress.connect(self._prog_chain.setValue)

        def _done(ok, msg, offs):
            self._append("chain", "ok" if ok else "warn", msg)
            if ok and offs:
                data = json.loads(OFFSETS_FILE.read_text("utf-8"))
                data.setdefault("pointer_chain", {})
                data["pointer_chain"]["module"] = "Diablo IV.exe"
                data["pointer_chain"]["offsets"] = [hex(o) for o in offs]
                data["pointer_chain"].setdefault(
                    "xyz_layout",
                    {"bytes_x_from_z": -4, "bytes_y_from_z": 4, "bytes_z_from_z": 0},
                )
                OFFSETS_FILE.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                self._append("chain", "ok", "已写入 pointer_chain")
            self._reload_reader()

        self._chain.done.connect(_done)
        self._chain.start()

    def _stop_all(self):
        if self._scan:
            self._scan.stop()
        if self._test:
            self._test.stop()
        if self._chain:
            self._chain.stop()

    def _run_pipeline(self):
        self._pipe_running = True
        self._btn_pipe.setEnabled(False)
        self._append("scan", "info", "【一键】步骤 ① 扫描…")
        self._tabs.setCurrentIndex(0)
        self._scan = ScanWorker(skip_snapshot=False)
        self._scan.log.connect(lambda lev, m: self._append("scan", lev, m))
        self._scan.status.connect(self._st_scan.setText)
        self._scan.progress.connect(lambda p, n: self._prog_scan.setValue(min(100, p)))

        def on_scan_done(ok, msg):
            self._append("scan", "ok" if ok else "warn", msg)
            if not ok or not self._pipe_running:
                self._pipe_done()
                return
            self._append("test", "info", "【一键】步骤 ② 验证…")
            self._tabs.setCurrentIndex(1)
            targets = _load_targets()
            if not targets:
                self._append("test", "err", "无候选，中止")
                self._pipe_done()
                return
            self._test = AutoTester(targets)
            self._test.log.connect(lambda lev, m: self._append("test", lev, m))

            def on_test_fin():
                self._reload_reader()
                if not self._pipe_running:
                    return
                self._append("chain", "info", "【一键】步骤 ③ 指针链…")
                self._tabs.setCurrentIndex(2)
                if not OFFSETS_FILE.exists():
                    self._pipe_done()
                    return
                data = json.loads(OFFSETS_FILE.read_text("utf-8"))
                cur = data.get("current", {})
                z_s = cur.get("player_z_addr") or cur.get("player_coord_addr_dynamic")
                if not z_s:
                    self._append("chain", "warn", "无 Z 地址，跳过指针链")
                    self._pipe_done()
                    self._reload_reader()
                    return
                z_addr = int(str(z_s), 16)
                self._chain = PointerChainWorker(z_addr)
                self._chain.log.connect(lambda lev, m: self._append("chain", lev, m))
                self._chain.progress.connect(self._prog_chain.setValue)

                def on_chain_done(ok, msg, offs):
                    if offs:
                        data = json.loads(OFFSETS_FILE.read_text("utf-8"))
                        data.setdefault("pointer_chain", {})
                        data["pointer_chain"]["module"] = "Diablo IV.exe"
                        data["pointer_chain"]["offsets"] = [hex(o) for o in offs]
                        data["pointer_chain"].setdefault(
                            "xyz_layout",
                            {"bytes_x_from_z": -4, "bytes_y_from_z": 4, "bytes_z_from_z": 0},
                        )
                        OFFSETS_FILE.write_text(
                            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
                        )
                    self._pipe_done()
                    self._reload_reader()

                self._chain.done.connect(on_chain_done)
                self._chain.start()

            self._test.finished.connect(on_test_fin)
            self._test.start()

        self._scan.done.connect(on_scan_done)
        self._scan.start()

    def _pipe_done(self):
        self._pipe_running = False
        self._btn_pipe.setEnabled(True)

    def _reload_reader(self):
        try:
            if self._reader:
                try:
                    self._reader.close()
                except Exception:
                    pass
                self._reader = None
            if D4Reader is None:
                return
            self._reader = D4Reader(OFFSETS_FILE)
            self._lbl_mon_status.setText(
                f"模式: {self._reader._mode}  |  已连接"
            )
        except Exception as e:
            self._reader = None
            self._lbl_mon_status.setText(f"读取器: {e}")

    def _tick_monitor(self):
        if self._reader is None:
            try:
                if D4Reader and OFFSETS_FILE.exists():
                    data = json.loads(OFFSETS_FILE.read_text("utf-8"))
                    cur = data.get("current", {})
                    pc = data.get("pointer_chain") or {}
                    if (cur.get("player_z_addr") or cur.get("player_coord_addr_dynamic")
                            or (pc.get("offsets") and len(pc["offsets"]) > 0)):
                        self._reload_reader()
            except Exception:
                pass
        if self._reader is None:
            self._lbl_x.setText("—")
            self._lbl_z.setText("—")
            self._lbl_y.setText("—")
            return
        try:
            c = self._reader.get_world_coords()
            if c:
                x, y, z = c
                self._lbl_x.setText(f"{x:.3f}")
                self._lbl_z.setText(f"{z:.3f}")
                self._lbl_y.setText(f"{y:.3f}")
            else:
                self._lbl_x.setText("?")
                self._lbl_z.setText("?")
                self._lbl_y.setText("?")
        except Exception:
            self._lbl_mon_status.setText("读取失败，将重试加载配置")
            self._reader = None

    def closeEvent(self, e):
        self._timer.stop()
        if self._reader:
            try:
                self._reader.close()
            except Exception:
                pass
        super().closeEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton and self._drag:
            self.move(e.globalPos() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None


def main():
    if not _is_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, f'"{Path(__file__).resolve()}"', None, 1
        )
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei UI", 9))
    w = CoordToolWindow()
    w.show()
    w._reload_reader()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
