#!/usr/bin/env python3
"""
D4 坐标一键向导：扫描 → 自动测试 →（可选）自动查找指针链 → 写入 d4_offsets.json

启动（管理员）：
  python coord_wizard.py
  或双击 launch_coord_wizard.bat
"""
from __future__ import annotations

import ctypes
import json
import sys
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QProgressBar, QFrame, QSizeGrip,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QTextCursor

_TOOLS = Path(__file__).parent
OFFSETS_FILE = _TOOLS / "d4_offsets.json"

# 延迟导入重型模块，加快启动
def _import_workers():
    from mem_scanner_ui import ScanWorker
    from live_xyz import AutoTester, _load_targets
    from coord_pointer_chain import reverse_pointer_chain, get_module_base_size
    from d4reader import resolve_pointer_chain, _read_pointer, _get_pid, _get_module_base
    import ctypes as CT
    kernel32 = CT.windll.kernel32
    PROCESS_VM_READ = 0x0010
    PROCESS_QUERY_INFORMATION = 0x0400
    return (
        ScanWorker, AutoTester, _load_targets,
        reverse_pointer_chain, get_module_base_size,
        resolve_pointer_chain, _get_pid, _get_module_base,
        kernel32, PROCESS_VM_READ, PROCESS_QUERY_INFORMATION,
    )


LEVEL = {"info": "#a0c8e0", "ok": "#70ff70", "warn": "#f0c050", "err": "#ff6060"}


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class PointerChainWorker(QThread):
    """在后台线程中反向扫描指针链（可能较慢）。"""
    log      = pyqtSignal(str, str)
    progress = pyqtSignal(int)
    done     = pyqtSignal(bool, str, object)  # ok, msg, offsets_or_none

    def __init__(self, z_addr: int):
        super().__init__()
        self._z = z_addr

    def run(self):
        (
            _, _, _,
            reverse_pointer_chain, get_module_base_size,
            resolve_pointer_chain, _get_pid, _,
            kernel32, PR, PQI,
        ) = _import_workers()

        pid = _get_pid("Diablo IV.exe")
        if not pid:
            self.done.emit(False, "未找到游戏进程", None)
            return
        h = kernel32.OpenProcess(PR | PQI, False, pid)
        if not h:
            self.done.emit(False, f"OpenProcess 失败 {kernel32.GetLastError()}", None)
            return
        mb, ms = get_module_base_size(pid, "Diablo IV.exe")
        if not mb:
            kernel32.CloseHandle(h)
            self.done.emit(False, "无法获取模块基址", None)
            return

        def prog(pct, _n):
            self.progress.emit(int(pct))

        self.log.emit("info", f"目标 Z 地址: 0x{self._z:X}，正在反向扫描指针（可能 1～5 分钟）…")

        offs = reverse_pointer_chain(h, mb, ms, self._z, max_depth=8, progress_cb=prog)

        if not offs:
            kernel32.CloseHandle(h)
            self.done.emit(
                False,
                "自动指针链未找到（常见：中间有非零偏移）。请用 Cheat Engine 手动指针扫描。",
                None,
            )
            return

        resolved = resolve_pointer_chain(h, mb, offs)
        kernel32.CloseHandle(h)

        if resolved != self._z:
            self.done.emit(
                False,
                f"链校验失败: 解析得 0x{resolved:X} 期望 0x{self._z:X}",
                None,
            )
            return

        self.done.emit(True, "指针链已验证", offs)


class WizardWindow(QWidget):
    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(0.96)
        self.resize(520, 560)
        self._drag = None
        self._log_n = 0
        self._scan: QThread | None = None
        self._test: QThread | None = None
        self._chain: QThread | None = None
        self._build()

        geo = QApplication.primaryScreen().availableGeometry()
        self.move(geo.x() + 12, geo.y() + 12)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setStyleSheet(
            "QFrame{background:rgba(7,7,18,238);border:1px solid #2e2448;border-radius:8px;}"
        )
        inner = QVBoxLayout(card)
        inner.setContentsMargins(12, 10, 12, 10)

        title = QLabel("D4 坐标一键向导")
        title.setStyleSheet("color:#c9a227;font-size:15px;font-weight:bold;")
        inner.addWidget(title)

        hint = QLabel(
            "① 内存扫描  →  ② 自动移动验证  →  ③ 自动查找指针链（可选，较慢）\n"
            "完成后重启游戏仍可用坐标（③ 成功时）。需安装 keyboard，游戏在前台。"
        )
        hint.setStyleSheet("color:#5a5068;font-size:11px;")
        hint.setWordWrap(True)
        inner.addWidget(hint)

        self._prog = QProgressBar()
        self._prog.setRange(0, 100)
        self._prog.setValue(0)
        self._prog.setFixedHeight(6)
        self._prog.setTextVisible(False)
        inner.addWidget(self._prog)

        self._status = QLabel("就绪")
        self._status.setStyleSheet("color:#5090d0;font-weight:bold;")
        inner.addWidget(self._status)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet(
            "QTextEdit{background:rgba(4,4,12,220);color:#70c870;"
            "border:1px solid #1a2a1a;font-family:Consolas;font-size:11px;}"
        )
        inner.addWidget(self._log, 1)

        row = QHBoxLayout()
        self._btn_full = QPushButton("一键全自动")
        self._btn_full.setStyleSheet(
            "QPushButton{background:#0f2e14;border:1px solid #236b28;color:#4fc254;"
            "font-weight:bold;padding:8px 16px;border-radius:5px;}"
        )
        self._btn_full.clicked.connect(self._run_full)

        self._btn_chain = QPushButton("仅查找指针链")
        self._btn_chain.setStyleSheet(
            "QPushButton{background:#0e1e2e;border:1px solid #1e4060;color:#5090d0;"
            "font-weight:bold;padding:8px 16px;border-radius:5px;}"
        )
        self._btn_chain.clicked.connect(self._run_chain_only)

        b_close = QPushButton("关闭")
        b_close.clicked.connect(self.close)
        row.addWidget(self._btn_full)
        row.addWidget(self._btn_chain)
        row.addWidget(b_close)
        inner.addLayout(row)

        grip = QHBoxLayout()
        grip.addStretch()
        grip.addWidget(QSizeGrip(card))
        inner.addLayout(grip)

        lay.addWidget(card)

    def _append(self, level: str, msg: str):
        self._log_n += 1
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        c = LEVEL.get(level, "#a0c8e0")
        self._log.append(
            f'<span style="color:#556655;">[{self._log_n:03d} {ts}]</span> '
            f'<span style="color:{c};">{_esc(msg)}</span>'
        )
        cur = self._log.textCursor()
        cur.movePosition(QTextCursor.End)
        self._log.setTextCursor(cur)

    def _set_busy(self, busy: bool):
        self._btn_full.setEnabled(not busy)
        self._btn_chain.setEnabled(not busy)

    def _run_full(self):
        self._log.clear()
        self._log_n = 0
        self._prog.setValue(0)
        self._append("info", "开始：步骤 ① 内存快照扫描…")
        self._status.setText("① 扫描中…")
        self._set_busy(True)

        ScanWorker, *_ = _import_workers()
        self._scan = ScanWorker(skip_snapshot=False)
        self._scan.log.connect(self._append)
        self._scan.status.connect(self._status.setText)
        self._scan.progress.connect(lambda p, n: self._prog.setValue(min(100, p)))
        self._scan.done.connect(self._on_scan_done)
        self._scan.start()

    def _on_scan_done(self, ok: bool, msg: str):
        self._append("ok" if ok else "warn", msg)
        if not ok:
            self._status.setText("扫描失败")
            self._set_busy(False)
            return
        self._append("info", "步骤 ② 自动移动验证…")
        self._status.setText("② 自动测试中…")
        self._prog.setValue(0)

        _, AutoTester, load_targets, *_ = _import_workers()
        targets = load_targets()
        if not targets:
            self._append("err", "候选为空，无法自动测试")
            self._set_busy(False)
            return

        self._test = AutoTester(targets)
        self._test.log.connect(self._append)
        self._test.status.connect(self._status.setText)
        self._test.finished.connect(self._on_test_finished)
        self._test.start()

    def _on_test_finished(self):
        self._status.setText("② 完成")
        self._append("info", "步骤 ③ 自动查找指针链（可取消等待）…")
        self._start_pointer_chain_from_json()

    def _start_pointer_chain_from_json(self):
        if not OFFSETS_FILE.exists():
            self._append("err", "无 d4_offsets.json")
            self._set_busy(False)
            return
        data = json.loads(OFFSETS_FILE.read_text("utf-8"))
        cur = data.get("current", {})
        z_s = cur.get("player_z_addr") or cur.get("player_coord_addr_dynamic")
        if not z_s:
            self._append("warn", "无 player_z_addr，跳过指针链")
            self._set_busy(False)
            return
        z_addr = int(str(z_s), 16)

        self._chain = PointerChainWorker(z_addr)
        self._chain.log.connect(self._append)
        self._chain.progress.connect(self._prog.setValue)
        self._chain.done.connect(self._on_chain_done)
        self._chain.start()

    def _on_chain_done(self, ok: bool, msg: str, offs: object):
        self._append("ok" if ok else "warn", msg)
        if ok and offs:
            try:
                data = json.loads(OFFSETS_FILE.read_text("utf-8"))
                data.setdefault("pointer_chain", {})
                data["pointer_chain"]["module"] = "Diablo IV.exe"
                data["pointer_chain"]["offsets"] = [hex(o) for o in offs]
                data["pointer_chain"].setdefault(
                    "xyz_layout",
                    {
                        "bytes_x_from_z": -4,
                        "bytes_y_from_z": 4,
                        "bytes_z_from_z": 0,
                    },
                )
                OFFSETS_FILE.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                self._append("ok", "已写入 pointer_chain，重启游戏后可运行 python d4reader.py 验证")
            except Exception as e:
                self._append("err", f"保存失败: {e}")
        elif not ok:
            self._append(
                "warn",
                "可手动：CE 对 player_z_addr 做 Pointer scan，将链填入 d4_offsets.json → pointer_chain.offsets",
            )
        self._status.setText("全部完成" if ok else "已完成（指针链需手动）")
        self._prog.setValue(100)
        self._set_busy(False)

    def _run_chain_only(self):
        self._append("info", "仅执行指针链查找…")
        self._status.setText("③ 指针链…")
        self._set_busy(True)
        self._start_pointer_chain_from_json()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton and self._drag:
            self.move(e.globalPos() - self._drag)


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def main():
    if not _is_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, f'"{Path(__file__).resolve()}"', None, 1
        )
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei UI", 9))
    w = WizardWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
