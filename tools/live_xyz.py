"""
实时 XYZ 坐标浮窗 + 自动测试
自动控制角色左右移动，根据响应判断哪个地址是玩家坐标，打印完整日志。
需管理员权限运行。
"""
import ctypes, ctypes.wintypes, struct, math, time, sys, json, random
from pathlib import Path
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                              QLabel, QFrame, QSizeGrip, QTextEdit, QPushButton)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QTextCursor

kernel32 = ctypes.windll.kernel32
psapi    = ctypes.windll.psapi
PROCESS_VM_READ           = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

OFFSETS_FILE = Path(__file__).parent / "d4_offsets.json"

# ── 从候选文件动态加载，或使用已知地址 ─────────────────────────────────────
CAND_FILE  = Path(__file__).parent / "d4_candidates.bin"
ENTRY_SIZE = 12

def _load_targets():
    """优先从候选文件加载，过滤掉 0x25... 组（已证明不是坐标）"""
    targets = []
    if CAND_FILE.exists():
        data = CAND_FILE.read_bytes()
        for i in range(len(data) // ENTRY_SIZE):
            addr, _ = struct.unpack_from('<Qf', data, i * ENTRY_SIZE)
            # 跳过 0x25... 地址组（X=Y=Z相同，已排除）
            if (addr >> 32) == 0x25:
                continue
            targets.append(addr)
    # 去重保序
    seen = set()
    result = []
    for a in targets:
        if a not in seen:
            seen.add(a)
            result.append(a)
    return result

# ── 移动按键 ─────────────────────────────────────────────────────────────────
try:
    import keyboard as _kb
    _HAS_KB = True
except ImportError:
    _HAS_KB = False

def _get_keys():
    cfg = Path(__file__).parent.parent / "config" / "settings.json"
    try:
        scheme = json.loads(cfg.read_text('utf-8')).get("move_keys", "arrows")
    except Exception:
        scheme = "arrows"
    if scheme == "wasd":
        return {"left": "a", "right": "d", "up": "w", "down": "s"}
    return {"left": "left", "right": "right", "up": "up", "down": "down"}

def _move(direction: str, duration: float):
    if not _HAS_KB:
        return
    key = _get_keys().get(direction, direction)
    _kb.press(key)
    time.sleep(max(0.05, duration))
    _kb.release(key)
    time.sleep(0.12)

# ── 内存读取 ─────────────────────────────────────────────────────────────────
def _find_pid(name="Diablo IV.exe"):
    buf = (ctypes.wintypes.DWORD * 1024)()
    nb  = ctypes.wintypes.DWORD(0)
    psapi.EnumProcesses(buf, ctypes.sizeof(buf), ctypes.byref(nb))
    nbuf = ctypes.create_unicode_buffer(260)
    for pid in list(buf[:nb.value // 4]):
        if not pid: continue
        h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not h: continue
        psapi.GetModuleBaseNameW(h, None, nbuf, 260)
        n = nbuf.value; kernel32.CloseHandle(h)
        if n.lower() == name.lower(): return pid
    return None

def _read_3f(h, addr):
    buf = ctypes.create_string_buffer(12)
    n   = ctypes.c_size_t(0)
    ok  = kernel32.ReadProcessMemory(h, ctypes.c_void_p(addr - 4), buf, 12, ctypes.byref(n))
    if not (ok and n.value == 12): return None
    x, z, y = struct.unpack('<fff', buf.raw)
    if not all(math.isfinite(v) for v in (x, z, y)): return None
    return x, z, y

def _read_f(h, addr):
    buf = ctypes.create_string_buffer(4)
    n   = ctypes.c_size_t(0)
    ok  = kernel32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, 4, ctypes.byref(n))
    if not (ok and n.value == 4): return None
    v = struct.unpack('<f', buf.raw)[0]
    return v if math.isfinite(v) else None

# ── 自动测试线程 ──────────────────────────────────────────────────────────────
class AutoTester(QThread):
    log    = pyqtSignal(str, str)   # (level, msg)
    result = pyqtSignal(dict)       # {addr: score_info}
    status = pyqtSignal(str)

    MOVE_SECS  = 1.2
    ROUNDS     = 4
    COUNTDOWN  = 5
    SETTLE     = 0.4   # 移动后等待稳定

    def __init__(self, targets):
        super().__init__()
        self._targets = targets
        self._stop    = False

    def stop(self): self._stop = True

    def _L(self, msg, level="info"): self.log.emit(level, msg)

    def run(self):
        if not _HAS_KB:
            self._L("keyboard 库未安装，自动移动不可用 (pip install keyboard)", "err")
            return

        # ── 找进程 ────────────────────────────────────────────────────────────
        pid = _find_pid()
        if not pid:
            self._L("未找到 Diablo IV.exe", "err"); return
        h = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
        if not h:
            self._L(f"OpenProcess 失败 err={kernel32.GetLastError()}", "err"); return
        self._L(f"附加进程 PID={pid}", "ok")
        self._L(f"待测地址: {len(self._targets)} 个", "info")

        # ── 倒计时 ────────────────────────────────────────────────────────────
        for i in range(self.COUNTDOWN, 0, -1):
            if self._stop: break
            self.status.emit(f"请切换到游戏窗口  {i}s 后开始...")
            time.sleep(1)
        if self._stop:
            kernel32.CloseHandle(h); return

        # ── 记分板 ────────────────────────────────────────────────────────────
        # scores[addr] = {
        #   right_response: 向右移动时该轴增大的次数
        #   left_response:  向左移动时该轴减小的次数
        #   total_delta:    累计移动量
        #   y_stability:    Y轴(高度)标准差（越小越像高度轴）
        # }
        scores = {a: {"right": 0, "left": 0, "delta": 0.0,
                      "y_vals": [], "last_xyz": None} for a in self._targets}

        # ── 测试轮次 ──────────────────────────────────────────────────────────
        for rnd in range(self.ROUNDS):
            if self._stop: break
            self._L(f"── 轮次 {rnd+1}/{self.ROUNDS} ──", "info")

            # 读取移动前的值
            before = {}
            for addr in self._targets:
                v = _read_3f(h, addr)
                before[addr] = v

            # 向右移动
            secs = self.MOVE_SECS + random.uniform(-0.15, 0.15)
            self.status.emit(f"轮次{rnd+1} → 向右移动 {secs:.1f}s")
            self._L(f"→ 向右 {secs:.1f}s", "info")
            _move("right", secs)
            time.sleep(self.SETTLE)

            # 读取移动后的值
            after = {}
            for addr in self._targets:
                v = _read_3f(h, addr)
                after[addr] = v

            # 统计向右响应
            right_changes = []
            for addr in self._targets:
                b = before.get(addr); a = after.get(addr)
                if b is None or a is None: continue
                # addr = Z axis (自身值), addr-4 = X axis
                dz = a[1] - b[1]   # addr 自身（Z）
                dx = a[0] - b[0]   # addr-4 （X）
                total = abs(dz) + abs(dx)
                if total > 0.05:
                    scores[addr]["delta"] += total
                    right_changes.append((addr, dx, dz, a[2]))
                    scores[addr]["y_vals"].append(a[2])
                    scores[addr]["last_xyz"] = a

            # 如果某轴随向右移动而增大 → 加分
            if right_changes:
                # 找 dx 最大的地址
                best = max(right_changes, key=lambda x: x[1])
                addr, dx, dz, y = best
                self._L(f"  向右变化最大: 0x{addr:X}  ΔX={dx:+.3f}  ΔZ={dz:+.3f}  Y={y:.3f}", "ok")
                for addr, dx, dz, y in right_changes:
                    if dx > 0.02: scores[addr]["right"] += 1
                    if dz > 0.02: scores[addr]["right"] += 1
            else:
                self._L("  向右无明显变化（角色可能被墙阻挡）", "warn")

            # 读取移动前（向左）
            before2 = {}
            for addr in self._targets:
                v = _read_3f(h, addr); before2[addr] = v

            # 向左移动（距离稍大，走回来）
            secs2 = secs * 2 + random.uniform(-0.1, 0.1)
            self.status.emit(f"轮次{rnd+1} ← 向左移动 {secs2:.1f}s")
            self._L(f"← 向左 {secs2:.1f}s", "info")
            _move("left", secs2)
            time.sleep(self.SETTLE)

            after2 = {}
            for addr in self._targets:
                v = _read_3f(h, addr); after2[addr] = v

            # 统计向左响应
            left_changes = []
            for addr in self._targets:
                b = before2.get(addr); a = after2.get(addr)
                if b is None or a is None: continue
                dx = a[0] - b[0]; dz = a[1] - b[1]
                total = abs(dz) + abs(dx)
                if total > 0.05:
                    scores[addr]["delta"] += total
                    left_changes.append((addr, dx, dz, a[2]))
                    scores[addr]["y_vals"].append(a[2])
                    scores[addr]["last_xyz"] = a

            if left_changes:
                best = min(left_changes, key=lambda x: x[1])  # dx 最小（负得最多）
                addr, dx, dz, y = best
                self._L(f"  向左变化最大: 0x{addr:X}  ΔX={dx:+.3f}  ΔZ={dz:+.3f}  Y={y:.3f}", "ok")
                for addr, dx, dz, y in left_changes:
                    if dx < -0.02: scores[addr]["left"] += 1
                    if dz < -0.02: scores[addr]["left"] += 1
            else:
                self._L("  向左无明显变化", "warn")

            # 走回右边（平衡位移）
            _move("right", secs)
            time.sleep(0.2)

        # ── 分析结果 ──────────────────────────────────────────────────────────
        self._L("\n══ 分析结果 ══", "ok")
        self.status.emit("分析完成")

        ranked = []
        for addr, s in scores.items():
            total_score = s["right"] + s["left"]
            y_std = 0.0
            if len(s["y_vals"]) > 1:
                mean = sum(s["y_vals"]) / len(s["y_vals"])
                y_std = math.sqrt(sum((v-mean)**2 for v in s["y_vals"]) / len(s["y_vals"]))
            ranked.append((total_score, s["delta"], y_std, addr, s["last_xyz"]))

        ranked.sort(reverse=True)

        self._L(f"{'排名':>4}  {'地址':>18}  {'响应分':>6}  {'总位移':>8}  {'Y稳定性':>10}  {'最终XZY'}", "info")
        best_addr = None
        for i, (score, delta, y_std, addr, xyz) in enumerate(ranked[:8]):
            xyz_s = f"[{xyz[0]:.2f}, {xyz[1]:.2f}, {xyz[2]:.2f}]" if xyz else "—"
            mark = "★ 玩家坐标!" if i == 0 and score > 0 else ""
            self._L(f"  #{i+1:02d}  0x{addr:016X}  {score:6d}  {delta:8.3f}  ±{y_std:.4f}  {xyz_s}  {mark}",
                    "ok" if i == 0 else "info")
            if i == 0 and score > 0:
                best_addr = addr

        if best_addr and ranked[0][0] > 0:
            xyz = ranked[0][4]
            if xyz:
                self._L(f"\n✓ 最可能的玩家坐标地址: 0x{best_addr:016X}", "ok")
                self._L(f"  X={xyz[0]:.4f}  Z={xyz[1]:.4f}  Y={xyz[2]:.4f}", "ok")
                # 保存到 offsets.json
                try:
                    data = json.loads(OFFSETS_FILE.read_text('utf-8')) if OFFSETS_FILE.exists() else {}
                    data.setdefault('current', {})['player_coord_addr_dynamic'] = hex(best_addr)
                    data['current']['player_x_addr']    = hex(best_addr - 4)
                    data['current']['player_z_addr']    = hex(best_addr)
                    data['current']['player_y_addr']    = hex(best_addr + 4)
                    data['current']['coord_x_approx']   = round(xyz[0], 3)
                    data['current']['coord_z_approx']   = round(xyz[1], 3)
                    data['current']['coord_y_approx']   = round(xyz[2], 3)
                    OFFSETS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), 'utf-8')
                    self._L(f"  已保存到 d4_offsets.json", "ok")
                except Exception as e:
                    self._L(f"  保存失败: {e}", "warn")
        else:
            self._L("未找到明确响应坐标的地址，建议重新扫描或换开阔地带测试", "warn")

        self.result.emit({a: s for a, s in scores.items()})
        kernel32.CloseHandle(h)


# ── 浮窗 ─────────────────────────────────────────────────────────────────────
def _esc(t):
    return t.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

LEVEL_COLOR = {"info":"#a0c8e0","ok":"#70ff70","warn":"#f0c050","err":"#ff6060"}

class Overlay(QWidget):
    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(0.96)
        self.resize(500, 560)
        self._drag   = None
        self._tester = None
        self._log_n  = 0
        self._build()
        geo = QApplication.primaryScreen().availableGeometry()
        self.move(geo.x() + 12, geo.y() + 12)

    def _build(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(0,0,0,0)
        card = QFrame(self); card.setObjectName("card")
        card.setStyleSheet("""
            QFrame#card { background:rgba(7,7,18,238);
                          border:1px solid #2e2448; border-radius:8px; }
        """)
        lay = QVBoxLayout(card); lay.setContentsMargins(10,8,10,8); lay.setSpacing(5)

        # 标题栏
        tb = QHBoxLayout()
        t = QLabel("D4 坐标自动识别")
        t.setStyleSheet("color:#c9a227;font-size:13px;font-weight:bold;letter-spacing:1px;")
        self._lbl_x = QLabel("×")
        self._lbl_x.setStyleSheet("color:#6a5060;font-size:16px;font-weight:bold;padding:0 4px;")
        self._lbl_x.mousePressEvent = lambda e: self._quit()
        tb.addWidget(t); tb.addStretch(); tb.addWidget(self._lbl_x)
        lay.addLayout(tb)

        div = QFrame(); div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("color:#2e2448;background:#2e2448;max-height:1px;")
        lay.addWidget(div)

        # 状态行
        self._lbl_st = QLabel("等待开始...")
        self._lbl_st.setStyleSheet("color:#5090d0;font-size:12px;font-weight:bold;")
        self._lbl_st.setWordWrap(True)
        lay.addWidget(self._lbl_st)

        # 日志区
        lbl_log = QLabel("日志")
        lbl_log.setStyleSheet("color:#3a3a5a;font-size:10px;")
        lay.addWidget(lbl_log)

        self._log = QTextEdit(); self._log.setReadOnly(True)
        self._log.setStyleSheet("""
            QTextEdit { background:rgba(4,4,12,220); color:#70c870;
                        border:1px solid #1a2a1a; border-radius:3px;
                        font-family:Consolas,"Courier New",monospace; font-size:11px; padding:4px; }
        """)
        lay.addWidget(self._log, 1)

        # 按钮
        btn_row = QHBoxLayout()
        self._btn = QPushButton("开始自动测试")
        self._btn.setStyleSheet("""
            QPushButton { background:#0f2e14;border:1px solid #236b28;color:#4fc254;
                          font-size:13px;font-weight:bold;padding:7px 20px;border-radius:5px; }
            QPushButton:hover { background:#163d1c;border-color:#4fc254;color:#90ee90; }
            QPushButton:disabled { background:#121220;color:#3a3a4a;border-color:#1e1e30; }
        """)
        self._btn.clicked.connect(self._start)

        self._btn_stop = QPushButton("停止")
        self._btn_stop.setEnabled(False)
        self._btn_stop.setStyleSheet("""
            QPushButton { background:#2e0e0e;border:1px solid #8b1a1a;color:#ff6060;
                          font-size:13px;font-weight:bold;padding:7px 20px;border-radius:5px; }
            QPushButton:hover { background:#3e1414;border-color:#cc2020;color:#ff8080; }
            QPushButton:disabled { background:#121220;color:#3a3a4a;border-color:#1e1e30; }
        """)
        self._btn_stop.clicked.connect(self._stop)
        btn_row.addWidget(self._btn); btn_row.addWidget(self._btn_stop)
        lay.addLayout(btn_row)

        # 提示 + grip
        bot = QHBoxLayout()
        hint = QLabel("自动控制角色左右移动，判断哪个地址是玩家坐标")
        hint.setStyleSheet("color:#5a5068;font-size:10px;")
        bot.addWidget(hint,1)
        grip = QSizeGrip(card); grip.setStyleSheet("background:transparent;")
        bot.addWidget(grip)
        lay.addLayout(bot)

        outer.addWidget(card)

    def _start(self):
        targets = _load_targets()
        if not targets:
            self._on_log("err", "没有找到候选地址，请先运行扫描器")
            return
        self._log.clear(); self._log_n = 0
        self._on_log("info", f"加载 {len(targets)} 个候选地址（已排除0x25...组）")
        if not _HAS_KB:
            self._on_log("warn", "keyboard 库未安装: pip install keyboard")
        self._btn.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._tester = AutoTester(targets)
        self._tester.log.connect(self._on_log)
        self._tester.status.connect(self._lbl_st.setText)
        self._tester.result.connect(self._on_result)
        self._tester.finished.connect(self._on_done)
        self._tester.start()

    def _stop(self):
        if self._tester: self._tester.stop()
        self._btn_stop.setEnabled(False)
        self._lbl_st.setText("正在停止...")

    def _on_done(self):
        self._btn.setEnabled(True)
        self._btn_stop.setEnabled(False)

    def _on_log(self, level, msg):
        self._log_n += 1
        ts    = datetime.now().strftime("%H:%M:%S")
        color = LEVEL_COLOR.get(level, "#a0c8e0")
        line  = (f'<span style="color:#556655;">[{self._log_n:03d} {ts}]</span> '
                 f'<span style="color:{color};">{_esc(msg)}</span>')
        self._log.append(line)
        cur = self._log.textCursor()
        cur.movePosition(QTextCursor.End)
        self._log.setTextCursor(cur)

    def _on_result(self, scores):
        pass  # 详细结果已在日志中显示

    def _quit(self):
        if self._tester: self._tester.stop(); self._tester.wait(2000)
        QApplication.quit()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPos() - self.frameGeometry().topLeft()
    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.LeftButton and self._drag:
            self.move(e.globalPos() - self._drag)
    def mouseReleaseEvent(self, e): self._drag = None


# ── 管理员 + 入口 ─────────────────────────────────────────────────────────────
def _is_admin():
    try: return ctypes.windll.shell32.IsUserAnAdmin()
    except: return False

def main():
    if not _is_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, f'"{Path(__file__).resolve()}"', None, 1)
        sys.exit(0)
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei UI", 9))
    win = Overlay(); win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
