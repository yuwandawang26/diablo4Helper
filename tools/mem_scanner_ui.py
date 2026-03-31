#!/usr/bin/env python3
"""
D4 坐标扫描器 UI v1.0
带左上角浮窗，全自动扫描流程，无需任何手动输入。

启动方式（需管理员权限）：
  双击 launch_scanner.bat   ← 推荐
  或管理员 PowerShell → python mem_scanner_ui.py
"""

import sys
import ctypes
import ctypes.wintypes
import struct
import math
import time
import random
import json
import shutil
from pathlib import Path
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton, QProgressBar,
    QFrame, QSizeGrip,
)
from PyQt5.QtCore import (
    Qt, QPoint, QThread, pyqtSignal, QTimer,
)
from PyQt5.QtGui import QFont, QTextCursor, QColor

# ─── 路径 ─────────────────────────────────────────────────────────────────────

_TOOLS_DIR   = Path(__file__).parent
_PROJECT_DIR = _TOOLS_DIR.parent
SNAP_FILE    = _TOOLS_DIR / "d4_snapshot.bin"
CAND_FILE    = _TOOLS_DIR / "d4_candidates.bin"
ENTRY_SIZE   = 12   # uint64 addr + float32 + 4pad

# ─── 坐标值域过滤（最关键的优化）────────────────────────────────────────────
# D4 世界坐标通常在 ±150000 范围内，且绝对值大于几个单位
# 颜色(0-1)、法线(0-1)、UV、物理系数等全部被排除
COORD_MIN = 1.0       # 绝对值下限（排除接近0的噪声）
COORD_MAX = 200000.0  # 绝对值上限（排除超大无意义值）

# numpy 加速（可选，有则用）
try:
    import numpy as np
    _HAS_NP = True
except ImportError:
    _HAS_NP = False

# ─── Windows API ──────────────────────────────────────────────────────────────

kernel32 = ctypes.windll.kernel32
psapi    = ctypes.windll.psapi

PROCESS_VM_READ           = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT  = 0x1000
MEM_PRIVATE = 0x20000
READABLE    = {0x02, 0x04, 0x20, 0x40}
MAX_REGION_MB = 64
CHUNK = 0x40000  # 256 KB

# ─── 键盘 ─────────────────────────────────────────────────────────────────────

try:
    import keyboard as _kb
    _HAS_KB = True
except ImportError:
    _HAS_KB = False

def _get_move_keys() -> dict[str, str]:
    cfg = _PROJECT_DIR / "config" / "settings.json"
    try:
        scheme = json.loads(cfg.read_text('utf-8')).get("move_keys", "arrows")
    except Exception:
        scheme = "arrows"
    if scheme == "wasd":
        return {"up": "w", "down": "s", "left": "a", "right": "d"}
    return {"up": "up", "down": "down", "left": "left", "right": "right"}

def _send_move(direction: str, duration: float):
    if not _HAS_KB:
        return
    key = _get_move_keys().get(direction, direction)
    _kb.press(key)
    time.sleep(max(0.0, duration))
    _kb.release(key)
    time.sleep(0.12)

# ─── 内存结构 ─────────────────────────────────────────────────────────────────

class MBI(ctypes.Structure):
    _fields_ = [
        ("BaseAddress",       ctypes.c_ulonglong),
        ("AllocationBase",    ctypes.c_ulonglong),
        ("AllocationProtect", ctypes.wintypes.DWORD),
        ("_pad1",             ctypes.wintypes.DWORD),
        ("RegionSize",        ctypes.c_ulonglong),
        ("State",             ctypes.wintypes.DWORD),
        ("Protect",           ctypes.wintypes.DWORD),
        ("Type",              ctypes.wintypes.DWORD),
        ("_pad2",             ctypes.wintypes.DWORD),
    ]

# ─── 内存工具函数 ─────────────────────────────────────────────────────────────

MAX_PROCS = 1024

def _find_pid(name: str = "Diablo IV.exe") -> int | None:
    buf = (ctypes.wintypes.DWORD * MAX_PROCS)()
    needed = ctypes.wintypes.DWORD(0)
    psapi.EnumProcesses(buf, ctypes.sizeof(buf), ctypes.byref(needed))
    count = needed.value // ctypes.sizeof(ctypes.wintypes.DWORD)
    nbuf = ctypes.create_unicode_buffer(260)
    for pid in list(buf[:count]):
        if pid == 0:
            continue
        h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not h:
            continue
        psapi.GetModuleBaseNameW(h, None, nbuf, 260)
        n = nbuf.value
        kernel32.CloseHandle(h)
        if n.lower() == name.lower():
            return pid
    return None

def _open(pid: int) -> int:
    h = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        raise PermissionError(f"OpenProcess 失败 (err={kernel32.GetLastError()}) — 需管理员权限")
    return h

def _read_bytes(h: int, addr: int, size: int) -> bytes | None:
    buf = ctypes.create_string_buffer(size)
    n   = ctypes.c_size_t(0)
    ok  = kernel32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(n))
    return buf.raw[:n.value] if (ok and n.value > 0) else None

def _read_float(h: int, addr: int) -> float | None:
    d = _read_bytes(h, addr, 4)
    if not d or len(d) < 4:
        return None
    v = struct.unpack('<f', d)[0]
    return None if (math.isnan(v) or math.isinf(v)) else v

def _get_heap_regions(h: int) -> list[tuple[int, int]]:
    regions = []
    addr = 0
    mbi  = MBI()
    max_b = MAX_REGION_MB * 1024 * 1024
    while addr < 0x7FFFFFFFFFFF:
        if not kernel32.VirtualQueryEx(h, ctypes.c_void_p(addr),
                                       ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        if (mbi.State == MEM_COMMIT and mbi.Protect in READABLE
                and mbi.Type == MEM_PRIVATE
                and 0 < mbi.RegionSize <= max_b):
            regions.append((mbi.BaseAddress, mbi.RegionSize))
        nxt = mbi.BaseAddress + mbi.RegionSize
        if nxt <= addr:
            break
        addr = nxt
    return regions

def _candidate_count() -> int:
    f = CAND_FILE if CAND_FILE.exists() else SNAP_FILE
    return f.stat().st_size // ENTRY_SIZE if (f and f.exists()) else 0

# ─── 扫描工作线程 ─────────────────────────────────────────────────────────────

class ScanWorker(QThread):
    log      = pyqtSignal(str, str)   # (level, message)  level: info/warn/ok/err
    status   = pyqtSignal(str)        # phase description
    progress = pyqtSignal(int, int)   # (current_pct, candidate_count)
    found    = pyqtSignal(int, float, float, float)  # (addr, x, y, z)
    done     = pyqtSignal(bool, str)  # (success, message)

    MOVE_SECS   = 1.5
    MAX_ROUNDS  = 10
    TARGET_CAND = 15
    COUNTDOWN   = 5

    def __init__(self, skip_snapshot: bool = False):
        super().__init__()
        self._stop_flag    = False
        self._handle       = None
        self._regions      = []
        self._skip_snapshot = skip_snapshot

    def stop(self):
        self._stop_flag = True

    # ── 内部日志 ──────────────────────────────────────────────────────────────

    def _log(self, msg: str, level: str = "info"):
        self.log.emit(level, msg)

    def _check_stop(self) -> bool:
        return self._stop_flag

    # ── 快照扫描（带值域过滤，大幅减少候选数）────────────────────────────────

    def _snapshot(self) -> int:
        for f in [SNAP_FILE, CAND_FILE]:
            if f.exists():
                f.unlink()
        total   = sum(s for _, s in self._regions)
        scanned = 0
        count   = 0

        with open(SNAP_FILE, 'wb') as fout:
            for base, size in self._regions:
                if self._check_stop():
                    break
                for off in range(0, size, CHUNK):
                    chunk_sz = min(CHUNK, size - off)
                    data = _read_bytes(self._handle, base + off, chunk_sz)
                    if not data:
                        continue

                    n_floats = len(data) // 4
                    if n_floats < 3:
                        continue

                    if _HAS_NP:
                        arr = np.frombuffer(data[:n_floats * 4], dtype='<f4')
                        av  = np.abs(arr)
                        ok  = np.isfinite(arr) & (av >= COORD_MIN) & (av <= COORD_MAX)
                        # 三元组：自身 + 前一个 + 后一个都在范围内
                        triplet = ok.copy()
                        triplet[1:]  &= ok[:-1]   # 前邻
                        triplet[:-1] &= ok[1:]    # 后邻
                        for idx in np.where(triplet)[0]:
                            fout.write(struct.pack('<Qf',
                                base + off + int(idx) * 4,
                                float(arr[idx])))
                            count += 1
                    else:
                        vals = struct.unpack_from(f'<{n_floats}f', data)
                        for i in range(1, n_floats - 1):
                            v = vals[i]
                            if not math.isfinite(v):
                                continue
                            if abs(v) < COORD_MIN or abs(v) > COORD_MAX:
                                continue
                            pv, nv = vals[i - 1], vals[i + 1]
                            if not math.isfinite(pv) or abs(pv) < COORD_MIN or abs(pv) > COORD_MAX:
                                continue
                            if not math.isfinite(nv) or abs(nv) < COORD_MIN or abs(nv) > COORD_MAX:
                                continue
                            fout.write(struct.pack('<Qf', base + off + i * 4, v))
                            count += 1

                scanned += size
                pct = int(scanned / total * 100)
                self.progress.emit(pct, count)

        shutil.copy(SNAP_FILE, CAND_FILE)
        return count

    # ── 候选筛选（流式分块 + 页批量读取，全程 RAM < 30MB）─────────────────

    def _rescan(self, mode: str) -> int:
        """
        流式分块 + 页批量读取：
          每批 200k 条目 ≈ 2.4 MB，处理完立即写出。
          同一 4KB 页内的候选只做一次 ReadProcessMemory。
          无 numpy 依赖，避免 dtype 不匹配问题。
        """
        if not CAND_FILE.exists():
            return 0

        total_entries = CAND_FILE.stat().st_size // ENTRY_SIZE
        if total_entries == 0:
            return 0

        BATCH = 200_000   # 每批条目数，2.4 MB
        PAGE  = 4096

        tmp  = CAND_FILE.with_suffix('.tmp')
        kept = 0

        try:
            with open(CAND_FILE, 'rb') as fin, open(tmp, 'wb') as fout:
                processed = 0
                while not self._check_stop():
                    raw = fin.read(ENTRY_SIZE * BATCH)
                    if not raw:
                        break

                    batch_n = len(raw) // ENTRY_SIZE

                    # 解包 + 排序（只对这一小批排序，O(n log n) 很快）
                    pairs = []
                    for j in range(0, batch_n * ENTRY_SIZE, ENTRY_SIZE):
                        addr, val = struct.unpack_from('<Qf', raw, j)
                        pairs.append((addr, val))
                    pairs.sort()   # 按地址升序，便于页聚合

                    # 按 4KB 页聚合读取
                    i = 0
                    nb = len(pairs)
                    while i < nb:
                        pg_base = pairs[i][0] & ~(PAGE - 1)
                        pg_end  = pg_base + PAGE
                        j = i
                        while j < nb and pairs[j][0] < pg_end:
                            j += 1

                        pg = _read_bytes(self._handle, pg_base, PAGE)
                        if pg and len(pg) == PAGE:
                            for k in range(i, j):
                                addr, old_v = pairs[k]
                                off = addr - pg_base
                                if off + 4 > PAGE:
                                    continue
                                cur = struct.unpack_from('<f', pg, off)[0]
                                if not math.isfinite(cur):
                                    continue
                                keep = False
                                if   mode == 'changed'   : keep = abs(cur - old_v) > 0.001
                                elif mode == 'increased' : keep = cur > old_v + 0.001
                                elif mode == 'decreased' : keep = cur < old_v - 0.001
                                elif mode == 'unchanged' : keep = abs(cur - old_v) <= 0.001
                                if keep:
                                    fout.write(struct.pack('<Qf', addr, cur))
                                    kept += 1
                        i = j

                    processed += batch_n
                    pct = int(processed / max(total_entries, 1) * 100)
                    self.progress.emit(pct, kept)

        except Exception as e:
            self._log(f"筛选异常: {e}", "err")
            if tmp.exists():
                tmp.unlink()
            return kept  # 返回已处理的部分结果

        # 只有成功完成才替换候选文件
        if not self._check_stop() and kept > 0:
            tmp.replace(CAND_FILE)
            shutil.copy(CAND_FILE, SNAP_FILE)
        elif kept == 0:
            # 归零保护：不替换，保留上一次候选
            self._log("筛选结果为0，保留上一次候选文件不变", "warn")
            if tmp.exists():
                tmp.unlink()
        else:
            # 中途停止
            if tmp.exists():
                tmp.unlink()

        return kept

    # ── 候选分析：找 XYZ 三元组 ──────────────────────────────────────────────

    def _analyze_candidates(self) -> list[tuple[int, float, float, float]]:
        """
        从候选地址中找连续的 XYZ 三元组。
        判断标准：连续3个float，互相差值在 [-50000, 50000] 且绝对值在 [1, 100000]。
        """
        src = CAND_FILE if CAND_FILE.exists() else SNAP_FILE
        if not src or not src.exists():
            return []

        cnt = src.stat().st_size // ENTRY_SIZE
        addrs = []
        with open(src, 'rb') as f:
            for _ in range(min(cnt, 200)):  # 最多检查前200个
                raw = f.read(ENTRY_SIZE)
                if not raw or len(raw) < 8:
                    break
                addr = struct.unpack('<Q', raw[:8])[0]
                addrs.append(addr)

        results = []
        for addr in addrs:
            data = _read_bytes(self._handle, addr, 12)
            if not data or len(data) < 12:
                continue
            x, y, z = struct.unpack('<fff', data)
            if any(math.isnan(v) or math.isinf(v) for v in (x, y, z)):
                continue
            # 游戏世界坐标通常在 ±100000 范围内，高度 Y 比较小
            if not (0.1 < abs(x) < 100000):
                continue
            if not (0.1 < abs(z) < 100000):
                continue
            results.append((addr, x, y, z))

        return results

    # ── 主流程 ────────────────────────────────────────────────────────────────

    def run(self):
        self._stop_flag = False

        # ── 找进程 ────────────────────────────────────────────────────────────
        self.status.emit("正在查找游戏进程...")
        pid = _find_pid("Diablo IV.exe")
        if not pid:
            self.done.emit(False, "未找到 Diablo IV.exe，请先启动游戏")
            return
        self._log(f"找到 Diablo IV.exe  PID={pid}", "ok")

        try:
            self._handle = _open(pid)
        except PermissionError as e:
            self.done.emit(False, str(e))
            return
        self._log("已附加进程（只读模式）", "ok")

        # ── 枚举私有堆 ────────────────────────────────────────────────────────
        self.status.emit("枚举私有堆内存区域...")
        self._regions = _get_heap_regions(self._handle)
        total_mb = sum(s for _, s in self._regions) / 1024 / 1024
        self._log(f"私有堆: {len(self._regions)} 个区域 / {total_mb:.1f} MB", "info")

        if not _HAS_KB:
            self._log("警告：keyboard 库未安装，自动移动不可用", "warn")
            self._log("请运行: pip install keyboard", "warn")

        # ── 倒计时 ────────────────────────────────────────────────────────────
        self.status.emit(f"请切换到游戏窗口（{self.COUNTDOWN}秒后开始）")
        for i in range(self.COUNTDOWN, 0, -1):
            if self._check_stop():
                self.done.emit(False, "已取消")
                return
            self.status.emit(f"倒计时 {i}s — 请切换到游戏窗口，角色站在开阔地带")
            time.sleep(1)

        # ── 快照 ──────────────────────────────────────────────────────────────
        if self._skip_snapshot and CAND_FILE.exists() and CAND_FILE.stat().st_size > 0:
            n = CAND_FILE.stat().st_size // ENTRY_SIZE
            self._log(f"跳过快照，使用已有候选文件: {n:,} 个地址", "ok")
            # 确保 snapshot 和 candidates 同步
            if not SNAP_FILE.exists() or SNAP_FILE.stat().st_size != CAND_FILE.stat().st_size:
                shutil.copy(CAND_FILE, SNAP_FILE)
        else:
            self.status.emit("建立内存快照（请保持角色静止）...")
            self._log("开始快照扫描...", "info")
            n = self._snapshot()
            if self._check_stop():
                self.done.emit(False, "已取消")
                return
            self._log(f"快照完成，记录 {n:,} 个浮点地址", "ok")

        # ── 循环：移动 + 筛选 ─────────────────────────────────────────────────
        for rnd in range(self.MAX_ROUNDS):
            if self._check_stop():
                break
            cur_cnt = _candidate_count()
            self._log(f"── 轮次 {rnd+1}/{self.MAX_ROUNDS}  候选: {cur_cnt:,}", "info")

            if cur_cnt <= self.TARGET_CAND and rnd > 0:
                self._log(f"候选已降至 {cur_cnt}，达到目标！", "ok")
                break

            # 向右走
            move_s = self.MOVE_SECS + random.uniform(-0.2, 0.2)
            self.status.emit(f"轮次{rnd+1} — 向右移动 {move_s:.1f}s...")
            self._log(f"向右移动 {move_s:.1f}s", "info")
            _send_move("right", move_s)

            if self._check_stop():
                break
            time.sleep(0.3)

            self.status.emit(f"轮次{rnd+1} — 筛选增大的值...")
            kept = self._rescan('increased')
            self._log(f"筛选→增大  保留: {kept:,}", "ok" if kept < cur_cnt else "warn")
            self.progress.emit(100, kept)

            if kept == 0:
                self._log("候选归零！尝试改换方向...", "warn")
                shutil.copy(SNAP_FILE, CAND_FILE)
                _send_move("up", move_s)
                time.sleep(0.3)
                kept = self._rescan('changed')
                self._log(f"改方向后保留: {kept:,}", "warn")
                if kept == 0:
                    self._log("仍然归零，重新建立快照...", "warn")
                    self.status.emit("重新快照（请保持静止）...")
                    time.sleep(1)
                    n = self._snapshot()
                    self._log(f"重新快照: {n:,} 个", "info")
                    continue

            if _candidate_count() <= self.TARGET_CAND:
                break

            # 向左走（稍大距离）
            move_s2 = self.MOVE_SECS * 2 + random.uniform(-0.2, 0.2)
            self.status.emit(f"轮次{rnd+1} — 向左移动 {move_s2:.1f}s...")
            self._log(f"向左移动 {move_s2:.1f}s", "info")
            _send_move("left", move_s2)

            if self._check_stop():
                break
            time.sleep(0.3)

            self.status.emit(f"轮次{rnd+1} — 筛选减小的值...")
            kept = self._rescan('decreased')
            self._log(f"筛选→减小  保留: {kept:,}", "ok" if kept < cur_cnt else "warn")
            self.progress.emit(100, kept)

            if kept == 0:
                self._log("候选归零，重置候选文件...", "warn")
                if SNAP_FILE.exists():
                    shutil.copy(SNAP_FILE, CAND_FILE)
                continue

            # 走回右边（平衡位移）
            _send_move("right", self.MOVE_SECS)
            time.sleep(0.2)

        if self._check_stop():
            self.done.emit(False, "已手动停止")
            kernel32.CloseHandle(self._handle)
            return

        # ── 分析最终候选 ─────────────────────────────────────────────────────
        final_cnt = _candidate_count()
        self._log(f"扫描结束，最终候选: {final_cnt}", "ok")
        self.status.emit(f"分析候选地址（共 {final_cnt} 个）...")

        results = self._analyze_candidates()
        if results:
            self._log(f"找到 {len(results)} 个可能的坐标地址", "ok")
            for addr, x, y, z in results[:5]:
                self._log(f"  0x{addr:016X}  X={x:.2f}  Y={y:.2f}  Z={z:.2f}", "ok")
                self.found.emit(addr, x, y, z)
        else:
            self._log(f"未找到明显的 XYZ 三元组（候选={final_cnt}）", "warn")
            # 显示原始候选
            src = CAND_FILE if CAND_FILE.exists() else SNAP_FILE
            if src and src.exists():
                with open(src, 'rb') as f:
                    for _ in range(min(final_cnt, 10)):
                        raw = f.read(ENTRY_SIZE)
                        if not raw or len(raw) < 12:
                            break
                        addr, val = struct.unpack('<Qf', raw[:12])
                        cur = _read_float(self._handle, addr)
                        cur_s = f"{cur:.4f}" if cur is not None else "?"
                        self._log(f"  候选: 0x{addr:016X}  旧={val:.4f}  当前={cur_s}", "info")

        kernel32.CloseHandle(self._handle)
        self._handle = None

        if final_cnt == 0:
            self.done.emit(False, "未找到候选地址，建议调整移动幅度后重试")
        elif results:
            self.done.emit(True, f"找到 {len(results)} 个坐标地址候选")
        else:
            self.done.emit(False, f"候选 {final_cnt} 个，但未识别到 XYZ 三元组，请检查候选列表")


# ─── UI 浮窗 ──────────────────────────────────────────────────────────────────

LEVEL_COLORS = {
    "info": "#a0c8e0",
    "ok":   "#70e870",
    "warn": "#f0c050",
    "err":  "#ff6060",
}

def _html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class ScannerOverlay(QWidget):
    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(0.95)
        self.resize(380, 560)
        self._drag_pos = None
        self._worker: ScanWorker | None = None
        self._log_count = 0
        self._build_ui()
        self._position_top_left()
        self._set_idle()

    # ── UI 构建 ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._card = QFrame(self)
        self._card.setObjectName("card")
        self._card.setStyleSheet("""
            QFrame#card {
                background-color: rgba(7, 7, 18, 235);
                border: 1px solid #2e2448;
                border-radius: 8px;
            }
        """)
        lay = QVBoxLayout(self._card)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(5)

        # ── 标题栏 ────────────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        lbl_title = QLabel("D4 坐标扫描器")
        lbl_title.setStyleSheet(
            "font-size:14px; font-weight:bold; color:#c9a227; letter-spacing:2px;"
        )
        self._btn_close = QPushButton("×")
        self._btn_close.setFixedSize(22, 22)
        self._btn_close.setStyleSheet("""
            QPushButton { background:transparent; border:none; color:#6a5060;
                          font-size:16px; font-weight:bold; border-radius:11px; }
            QPushButton:hover { color:#ff6060; background:rgba(80,20,20,160); }
        """)
        self._btn_close.clicked.connect(self._on_close)
        title_row.addWidget(lbl_title)
        title_row.addStretch()
        title_row.addWidget(self._btn_close)
        lay.addLayout(title_row)

        # 分隔线
        div = QFrame(); div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("color:#2e2448; background:#2e2448; max-height:1px;")
        lay.addWidget(div)

        # ── 状态行 ────────────────────────────────────────────────────────────
        st_row = QHBoxLayout()
        lbl_st_icon = QLabel("状态")
        lbl_st_icon.setStyleSheet("color:#5a5068; font-size:11px;")
        self._lbl_status = QLabel("空闲")
        self._lbl_status.setStyleSheet("font-size:12px; font-weight:bold; color:#888;")
        self._lbl_status.setWordWrap(True)
        self._dot = QLabel("●")
        self._dot.setStyleSheet("font-size:15px; color:#555;")
        st_row.addWidget(lbl_st_icon)
        st_row.addWidget(self._lbl_status, 1)
        st_row.addWidget(self._dot)
        lay.addLayout(st_row)

        # ── 候选计数 ──────────────────────────────────────────────────────────
        cand_row = QHBoxLayout()
        lbl_cand_icon = QLabel("候选地址")
        lbl_cand_icon.setStyleSheet("color:#5a5068; font-size:11px;")
        self._lbl_cand = QLabel("—")
        self._lbl_cand.setStyleSheet("font-size:13px; font-weight:bold; color:#c9a227;")
        cand_row.addWidget(lbl_cand_icon)
        cand_row.addWidget(self._lbl_cand)
        cand_row.addStretch()
        lay.addLayout(cand_row)

        # ── 进度条 ────────────────────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet("""
            QProgressBar { background:#111130; border:none; border-radius:3px; }
            QProgressBar::chunk { background:#c9a227; border-radius:3px; }
        """)
        lay.addWidget(self._progress)

        # ── 找到的坐标 ────────────────────────────────────────────────────────
        coord_row = QHBoxLayout()
        lbl_coord_icon = QLabel("坐标")
        lbl_coord_icon.setStyleSheet("color:#5a5068; font-size:11px;")
        self._lbl_coord = QLabel("—")
        self._lbl_coord.setStyleSheet("font-size:11px; color:#70e870; font-family:Consolas;")
        coord_row.addWidget(lbl_coord_icon)
        coord_row.addWidget(self._lbl_coord, 1)
        lay.addLayout(coord_row)

        # ── 地址展示 ──────────────────────────────────────────────────────────
        addr_row = QHBoxLayout()
        lbl_addr_icon = QLabel("地址")
        lbl_addr_icon.setStyleSheet("color:#5a5068; font-size:11px;")
        self._lbl_addr = QLabel("—")
        self._lbl_addr.setStyleSheet("font-size:11px; color:#9070d0; font-family:Consolas;")
        self._lbl_addr.setTextInteractionFlags(Qt.TextSelectableByMouse)
        addr_row.addWidget(lbl_addr_icon)
        addr_row.addWidget(self._lbl_addr, 1)
        lay.addLayout(addr_row)

        # ── 日志 ──────────────────────────────────────────────────────────────
        lbl_log = QLabel("日志")
        lbl_log.setStyleSheet("color:#5a5068; font-size:11px; margin-top:3px;")
        lay.addWidget(lbl_log)

        self._log_edit = QTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setStyleSheet("""
            QTextEdit {
                background-color: rgba(4,4,12,210);
                color: #70c870;
                border: 1px solid #1a2a1a;
                border-radius:3px;
                font-family: Consolas,"Courier New",monospace;
                font-size:11px;
                padding:4px;
            }
        """)
        lay.addWidget(self._log_edit, 1)

        # ── 按钮行 ────────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._btn_start = QPushButton("完整扫描")
        self._btn_start.setStyleSheet("""
            QPushButton {
                background:#0f2e14; border:1px solid #236b28; color:#4fc254;
                font-size:13px; font-weight:bold; padding:7px 14px; border-radius:5px;
            }
            QPushButton:hover { background:#163d1c; border-color:#4fc254; color:#90ee90; }
            QPushButton:disabled { background:#121220; color:#3a3a4a; border-color:#1e1e30; }
        """)
        self._btn_start.clicked.connect(self._on_start)

        self._btn_resume = QPushButton("继续筛选")
        self._btn_resume.setStyleSheet("""
            QPushButton {
                background:#0e1e2e; border:1px solid #1e4060; color:#5090d0;
                font-size:13px; font-weight:bold; padding:7px 14px; border-radius:5px;
            }
            QPushButton:hover { background:#152538; border-color:#5090d0; color:#80b8f8; }
            QPushButton:disabled { background:#121220; color:#3a3a4a; border-color:#1e1e30; }
        """)
        self._btn_resume.clicked.connect(self._on_resume)

        self._btn_stop = QPushButton("停止")
        self._btn_stop.setEnabled(False)
        self._btn_stop.setStyleSheet("""
            QPushButton {
                background:#2e0e0e; border:1px solid #8b1a1a; color:#ff6060;
                font-size:13px; font-weight:bold; padding:7px 14px; border-radius:5px;
            }
            QPushButton:hover { background:#3e1414; border-color:#cc2020; color:#ff8080; }
            QPushButton:disabled { background:#121220; color:#3a3a4a; border-color:#1e1e30; }
        """)
        self._btn_stop.clicked.connect(self._on_stop)

        btn_row.addWidget(self._btn_start)
        btn_row.addWidget(self._btn_resume)
        btn_row.addWidget(self._btn_stop)
        lay.addLayout(btn_row)

        # ── 提示 + SizeGrip ───────────────────────────────────────────────────
        hint_row = QHBoxLayout()
        self._lbl_hint = QLabel("按下「开始扫描」后切换到游戏窗口")
        self._lbl_hint.setStyleSheet("color:#5a5068; font-size:10px;")
        self._lbl_hint.setWordWrap(True)
        hint_row.addWidget(self._lbl_hint, 1)
        grip = QSizeGrip(self._card)
        grip.setStyleSheet("background:transparent;")
        hint_row.addWidget(grip)
        lay.addLayout(hint_row)

        outer.addWidget(self._card)

    def _position_top_left(self):
        desktop = QApplication.primaryScreen().availableGeometry()
        self.move(desktop.x() + 12, desktop.y() + 12)

    # ── 状态辅助 ─────────────────────────────────────────────────────────────

    def _set_idle(self):
        self._dot.setStyleSheet("font-size:15px; color:#555;")
        self._lbl_status.setStyleSheet("font-size:12px; font-weight:bold; color:#888;")
        self._lbl_status.setText("空闲")

    def _set_running(self):
        self._dot.setStyleSheet("font-size:15px; color:#4caf50;")
        self._lbl_status.setStyleSheet("font-size:12px; font-weight:bold; color:#4caf50;")

    def _set_done_ok(self):
        self._dot.setStyleSheet("font-size:15px; color:#c9a227;")
        self._lbl_status.setStyleSheet("font-size:12px; font-weight:bold; color:#c9a227;")

    def _set_done_fail(self):
        self._dot.setStyleSheet("font-size:15px; color:#ff6060;")
        self._lbl_status.setStyleSheet("font-size:12px; font-weight:bold; color:#ff6060;")

    # ── 槽函数 ────────────────────────────────────────────────────────────────

    def _start_worker(self, skip_snapshot: bool = False):
        self._log_count = 0
        self._lbl_cand.setText("扫描中...")
        self._lbl_coord.setText("—")
        self._lbl_addr.setText("—")
        self._progress.setValue(0)
        self._btn_start.setEnabled(False)
        self._btn_resume.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._set_running()

        self._worker = ScanWorker(skip_snapshot=skip_snapshot)
        self._worker.log.connect(self._on_log)
        self._worker.status.connect(self._on_status)
        self._worker.progress.connect(self._on_progress)
        self._worker.found.connect(self._on_found)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_start(self):
        self._log_edit.clear()
        self._start_worker(skip_snapshot=False)

    def _on_resume(self):
        """跳过快照，直接用现有候选文件继续筛选。"""
        has_file = CAND_FILE.exists() and CAND_FILE.stat().st_size > 0
        if not has_file:
            self._on_log("warn", "没有找到已有候选文件，请先点「完整扫描」")
            return
        n = CAND_FILE.stat().st_size // ENTRY_SIZE
        self._on_log("ok", f"继续筛选模式，已有候选: {n:,} 个")
        self._start_worker(skip_snapshot=True)

    def _on_stop(self):
        if self._worker:
            self._worker.stop()
        self._btn_stop.setEnabled(False)
        self._lbl_status.setText("正在停止...")

    def _on_close(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(3000)
        self.close()
        QApplication.quit()

    def _on_log(self, level: str, msg: str):
        self._log_count += 1
        color = LEVEL_COLORS.get(level, "#a0c8e0")
        ts = datetime.now().strftime("%H:%M:%S")
        line = (
            f'<span style="color:#556655;">[{self._log_count:03d} {ts}]</span> '
            f'<span style="color:{color};">{_html(msg)}</span>'
        )
        self._log_edit.append(line)
        cur = self._log_edit.textCursor()
        cur.movePosition(QTextCursor.End)
        self._log_edit.setTextCursor(cur)

    def _on_status(self, msg: str):
        self._lbl_status.setText(msg)

    def _on_progress(self, pct: int, cand_cnt: int):
        self._progress.setValue(pct)
        if cand_cnt > 0:
            self._lbl_cand.setText(f"{cand_cnt:,} 个")

    def _on_found(self, addr: int, x: float, y: float, z: float):
        self._lbl_coord.setText(f"X={x:.2f}  Y={y:.2f}  Z={z:.2f}")
        self._lbl_addr.setText(f"0x{addr:016X}")

    def _on_done(self, success: bool, msg: str):
        self._btn_start.setEnabled(True)
        self._btn_resume.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._progress.setValue(100 if success else 0)
        self._lbl_status.setText(msg)
        if success:
            self._set_done_ok()
            self._lbl_hint.setText("扫描完成！地址已显示在上方。可再次点击「开始扫描」重新验证。")
        else:
            self._set_done_fail()
            self._lbl_hint.setText(f"失败：{msg}")
        self._worker = None

    # ── 拖动 ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(e.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None


# ─── 管理员权限检查 ───────────────────────────────────────────────────────────

def _is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def _relaunch_as_admin():
    """以管理员权限重新启动自身"""
    import subprocess
    script = str(Path(__file__).resolve())
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, f'"{script}"', None, 1
    )
    sys.exit(0)


# ─── 入口 ─────────────────────────────────────────────────────────────────────

def main():
    if not _is_admin():
        # 自动请求管理员权限（弹出 UAC 对话框）
        _relaunch_as_admin()
        return

    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei UI", 9))
    app.setStyle("Fusion")

    win = ScannerOverlay()
    win.show()

    # 检查 keyboard 库
    if not _HAS_KB:
        win._on_log("warn", "keyboard 库未安装！自动移动功能不可用")
        win._on_log("warn", "请在管理员 PowerShell 中运行: pip install keyboard")
        win._lbl_hint.setText("警告：请先安装 keyboard 库（pip install keyboard）")

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
