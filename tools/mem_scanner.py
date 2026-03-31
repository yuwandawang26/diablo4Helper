#!/usr/bin/env python3
"""
D4 内存坐标扫描器 v3.0
用于配合 Cheat Engine 发现玩家坐标的动态地址，
以及辅助确认 entity 结构体内的 position 字段偏移。

使用场景：
  - 第一次使用，还没有任何偏移数据
  - 游戏大版本更新后，所有旧偏移失效
  - 配合 Cheat Engine 验证找到的地址

运行方式：
  以管理员身份启动 PowerShell
  cd d:/D4-Auto/diablo4Helper/tools
  python mem_scanner.py
"""

import ctypes
import ctypes.wintypes
import struct
import sys
import time
import math
import random
import json
from pathlib import Path

# 值域过滤（关键优化）
COORD_MIN = 1.0
COORD_MAX = 200000.0

try:
    import numpy as np
    _HAS_NP = True
except ImportError:
    _HAS_NP = False

# keyboard 库用于自动移动角色
try:
    import keyboard as _kb
    _HAS_KEYBOARD = True
except ImportError:
    _HAS_KEYBOARD = False

# ─── 移动键配置（从 settings.json 读取，或使用默认值）─────────────────────────

_SETTINGS = Path(__file__).parent.parent / "config" / "settings.json"

def _get_move_keys() -> dict[str, str]:
    try:
        data = json.loads(_SETTINGS.read_text(encoding='utf-8'))
        scheme = data.get("move_keys", "arrows")
    except Exception:
        scheme = "arrows"
    if scheme == "wasd":
        return {"up": "w", "down": "s", "left": "a", "right": "d"}
    return {"up": "up", "down": "down", "left": "left", "right": "right"}

def _send_move(direction: str, duration: float):
    """向游戏发送移动按键（需游戏窗口在前台，或使用 SendInput 直接注入）"""
    if not _HAS_KEYBOARD:
        return
    keys = _get_move_keys()
    key  = keys.get(direction, direction)
    _kb.press(key)
    time.sleep(duration)
    _kb.release(key)
    time.sleep(0.15)

# ─── Windows API 常量 ────────────────────────────────────────────────────────

kernel32  = ctypes.windll.kernel32
psapi     = ctypes.windll.psapi

PROCESS_VM_READ           = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT  = 0x1000
MEM_PRIVATE = 0x20000   # 堆/栈 ← 游戏对象在这里
MEM_MAPPED  = 0x40000   # 文件映射 ← 跳过
MEM_IMAGE   = 0x1000000 # PE 镜像 ← 跳过

READABLE = {0x02, 0x04, 0x20, 0x40}
MAX_REGION_MB = 64

# ─── 快照文件 ─────────────────────────────────────────────────────────────────

SNAP_FILE = Path(__file__).parent / "d4_snapshot.bin"
CAND_FILE = Path(__file__).parent / "d4_candidates.bin"
ENTRY_SIZE = 12  # uint64 addr + float32 val + 4-byte pad

# ─── MBI 结构 ─────────────────────────────────────────────────────────────────

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

# ─── 进程工具（纯 API，不调用 tasklist/cmd）──────────────────────────────────

MAX_PROCESSES = 1024

def _get_all_pids() -> list[int]:
    buf = (ctypes.wintypes.DWORD * MAX_PROCESSES)()
    needed = ctypes.wintypes.DWORD(0)
    psapi.EnumProcesses(buf, ctypes.sizeof(buf), ctypes.byref(needed))
    count = needed.value // ctypes.sizeof(ctypes.wintypes.DWORD)
    return list(buf[:count])

def _get_process_name(pid: int) -> str:
    h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        return ""
    buf = ctypes.create_unicode_buffer(260)
    psapi.GetModuleBaseNameW(h, None, buf, 260)
    kernel32.CloseHandle(h)
    return buf.value

def get_pid(target: str = "Diablo IV.exe") -> int | None:
    for pid in _get_all_pids():
        if pid == 0:
            continue
        try:
            name = _get_process_name(pid)
            if name.lower() == target.lower():
                return pid
        except Exception:
            pass
    return None

def open_process(pid: int) -> int:
    h = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        err = kernel32.GetLastError()
        raise PermissionError(
            f"OpenProcess 失败 (错误码={err})\n"
            "请以【管理员身份】运行 PowerShell 后再执行此脚本"
        )
    return h

# ─── 内存读取 ─────────────────────────────────────────────────────────────────

def read_bytes(handle: int, addr: int, size: int) -> bytes | None:
    buf = ctypes.create_string_buffer(size)
    n   = ctypes.c_size_t(0)
    ok  = kernel32.ReadProcessMemory(handle, ctypes.c_void_p(addr), buf, size, ctypes.byref(n))
    return buf.raw[:n.value] if (ok and n.value > 0) else None

def read_float(handle: int, addr: int) -> float | None:
    d = read_bytes(handle, addr, 4)
    if not d or len(d) < 4:
        return None
    v = struct.unpack('<f', d)[0]
    return None if (math.isnan(v) or math.isinf(v)) else v

# ─── 内存区域枚举（只要私有堆）────────────────────────────────────────────────

def get_heap_regions(handle: int) -> list[tuple[int, int]]:
    regions = []
    addr = 0
    mbi = MBI()
    max_bytes = MAX_REGION_MB * 1024 * 1024
    while addr < 0x7FFFFFFFFFFF:
        if not kernel32.VirtualQueryEx(handle, ctypes.c_void_p(addr),
                                       ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        if (mbi.State == MEM_COMMIT
                and mbi.Protect in READABLE
                and mbi.Type == MEM_PRIVATE
                and 0 < mbi.RegionSize <= max_bytes):
            regions.append((mbi.BaseAddress, mbi.RegionSize))
        nxt = mbi.BaseAddress + mbi.RegionSize
        if nxt <= addr:
            break
        addr = nxt
    return regions

# ─── 快照扫描（写磁盘，不占 RAM）─────────────────────────────────────────────

CHUNK = 0x40000  # 256 KB

def snapshot_scan(handle: int, regions: list[tuple[int, int]]) -> int:
    """
    快照扫描（带值域过滤）：
    只记录绝对值在 [COORD_MIN, COORD_MAX] 范围内的浮点，
    跳过颜色/法线/UV等小值，大幅减少候选数量。
    """
    total   = sum(s for _, s in regions)
    scanned = 0
    count   = 0
    with open(SNAP_FILE, 'wb') as fout:
        for base, size in regions:
            for off in range(0, size, CHUNK):
                chunk_sz = min(CHUNK, size - off)
                data = read_bytes(handle, base + off, chunk_sz)
                if not data:
                    continue
                if _HAS_NP:
                    arr  = np.frombuffer(data, dtype='<f4')
                    av   = np.abs(arr)
                    mask = np.isfinite(arr) & (av >= COORD_MIN) & (av <= COORD_MAX)
                    for idx in np.where(mask)[0]:
                        fout.write(struct.pack('<Qf', base + off + int(idx) * 4, float(arr[idx])))
                        count += 1
                else:
                    for i in range(0, len(data) - 3, 4):
                        v = struct.unpack_from('<f', data, i)[0]
                        if not math.isfinite(v):
                            continue
                        av = abs(v)
                        if av < COORD_MIN or av > COORD_MAX:
                            continue
                        fout.write(struct.pack('<Qf', base + off + i, v))
                        count += 1
            scanned += size
            pct = scanned / total * 100
            print(f"\r  进度 {pct:5.1f}%  已记录: {count:,}", end='', flush=True)
    print()
    import shutil
    shutil.copy(SNAP_FILE, CAND_FILE)
    return count


def rescan(handle: int, mode: str,
           vmin: float = None, vmax: float = None) -> int:
    """
    候选筛选（批量读取优化）：
    按地址排序后，按 4KB 页分组，每页只调用一次 ReadProcessMemory，
    从 N百万次系统调用降低到 N/1000 次。
    """
    if not CAND_FILE.exists():
        print("  [错误] 还没有候选文件，请先执行快照扫描（选1）")
        return 0

    total_entries = CAND_FILE.stat().st_size // ENTRY_SIZE
    if total_entries == 0:
        return 0

    raw_all = CAND_FILE.read_bytes()
    BATCH_ENTRIES = 200_000
    PAGE          = 4096
    tmp           = CAND_FILE.with_suffix('.tmp')
    kept          = 0

    with open(CAND_FILE, 'rb') as fin, open(tmp, 'wb') as fout:
        processed = 0
        while True:
            raw = fin.read(ENTRY_SIZE * BATCH_ENTRIES)
            if not raw:
                break
            batch_n = len(raw) // ENTRY_SIZE

            pairs = []
            for j in range(0, batch_n * ENTRY_SIZE, ENTRY_SIZE):
                addr, val = struct.unpack_from('<Qf', raw, j)
                pairs.append((addr, val))
            pairs.sort(key=lambda x: x[0])

            i = 0
            nb = len(pairs)
            while i < nb:
                page_base = pairs[i][0] & ~(PAGE - 1)
                page_end  = page_base + PAGE
                j = i
                while j < nb and pairs[j][0] < page_end:
                    j += 1
                page_data = read_bytes(handle, page_base, PAGE)
                if page_data and len(page_data) == PAGE:
                    for k in range(i, j):
                        addr, old_v = pairs[k]
                        off = addr - page_base
                        if off + 4 > PAGE:
                            continue
                        cur = struct.unpack_from('<f', page_data, off)[0]
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
            pct = processed / max(total_entries, 1) * 100
            print(f"\r  筛选中 {pct:5.1f}%  保留: {kept:,}", end='', flush=True)

    print()
    tmp.replace(CAND_FILE)
    import shutil
    shutil.copy(CAND_FILE, SNAP_FILE)
    return kept


def candidate_count() -> int:
    f = CAND_FILE if CAND_FILE.exists() else SNAP_FILE
    return f.stat().st_size // ENTRY_SIZE if f.exists() else 0


# ─── 结果显示 ─────────────────────────────────────────────────────────────────

def show_candidates(handle: int, limit: int = 30):
    src = CAND_FILE if CAND_FILE.exists() else SNAP_FILE
    if not src or not src.exists():
        print("  [无数据] 请先执行快照扫描")
        return
    cnt = src.stat().st_size // ENTRY_SIZE
    shown = min(cnt, limit)
    print(f"\n  共 {cnt:,} 个候选，显示前 {shown} 个")
    print(f"  {'地址':20s}  {'旧值':>10s}  {'当前值':>10s}  {'前后8个float（[X]是目标位置）'}")
    print(f"  {'-'*90}")
    with open(src, 'rb') as f:
        for _ in range(shown):
            raw = f.read(ENTRY_SIZE)
            if not raw or len(raw) < 12:
                break
            addr, old_v = struct.unpack('<Qf', raw[:12])
            cur_v = read_float(handle, addr)
            cur_s = f"{cur_v:.4f}" if cur_v is not None else "读取失败"

            # 读周围 8 个 float（-16 到 +12 字节）
            nearby = read_bytes(handle, addr - 16, 48)
            if nearby and len(nearby) == 48:
                vals = [struct.unpack_from('<f', nearby, i)[0] for i in range(0, 48, 4)]
                parts = []
                for i, v in enumerate(vals):
                    s = f"{v:.2f}" if not math.isnan(v) and not math.isinf(v) else "?"
                    parts.append(f"[{s}]" if i == 4 else s)
                nearby_s = "  ".join(parts)
            else:
                nearby_s = "读取失败"
            print(f"  0x{addr:016X}  {old_v:>10.4f}  {cur_s:>10s}  {nearby_s}")


def monitor_xyz(handle: int, addr: int):
    """实时显示指定地址及后续 XYZ 三个 float"""
    print(f"\n  监控 0x{addr:016X}  (Ctrl+C 停止)\n")
    print(f"  {'X/val0':>12s}  {'Y/val1':>12s}  {'Z/val2':>12s}   {'周围16字节(hex)':s}")
    try:
        while True:
            data = read_bytes(handle, addr, 12)
            if data and len(data) == 12:
                x, y, z = struct.unpack('<fff', data)
                xs = f"{x:.4f}" if not math.isnan(x) else "NaN"
                ys = f"{y:.4f}" if not math.isnan(y) else "NaN"
                zs = f"{z:.4f}" if not math.isnan(z) else "NaN"
                extra = read_bytes(handle, addr - 4, 20) or b''
                hex_s = extra.hex(' ') if extra else ''
                print(f"\r  {xs:>12s}  {ys:>12s}  {zs:>12s}   {hex_s}", end='', flush=True)
            else:
                print(f"\r  [读取失败]", end='', flush=True)
            time.sleep(random.uniform(0.08, 0.15))
    except KeyboardInterrupt:
        print("\n  已停止")


# ─── 自动扫描模式 ─────────────────────────────────────────────────────────────

def _auto_scan(handle: int):
    """
    全自动扫描流程：
      1. 倒计时让用户切换到游戏窗口
      2. 快照扫描
      3. 循环：向右移动 → 筛选增大 → 向左移动 → 筛选减小
      4. 直到候选 < 20 个或达到最大轮次
      5. 自动显示剩余候选并进入监控
    """
    if not _HAS_KEYBOARD:
        print("""
  [错误] 自动模式需要 keyboard 库。
  请先安装：pip install keyboard
  安装后重新运行此脚本。
""")
        return

    MOVE_SECS   = 1.5   # 每次移动持续时间（秒）
    MAX_ROUNDS  = 8     # 最大来回轮次
    TARGET_CAND = 20    # 目标候选数量

    print(f"""
  【自动扫描模式】
  ────────────────────────────────────────────────────────────
  原理：脚本自动控制角色向右走、向左走，通过坐标变化筛选出地址。
  
  注意事项：
    ① 请确保游戏窗口处于前台（不要遮挡或最小化）
    ② 角色应在开阔地带，避免被墙壁阻挡
    ③ 扫描期间不要操作鼠标键盘（脚本会自动控制）
    ④ 按 Ctrl+C 可随时中止
  
  移动按键: {_get_move_keys()}
  每次移动时长: {MOVE_SECS}s  最大轮次: {MAX_ROUNDS}
  ────────────────────────────────────────────────────────────
""")

    # 倒计时，让用户切换到游戏
    COUNTDOWN = 5
    print(f"  请在 {COUNTDOWN} 秒内切换到游戏窗口...")
    for i in range(COUNTDOWN, 0, -1):
        print(f"\r  倒计时: {i} 秒", end='', flush=True)
        time.sleep(1)
    print("\r  开始执行！                    ")

    try:
        # ── Step 1: 快照 ──────────────────────────────────────────────────────
        print("\n  [1/3] 正在建立快照（站立不动）...")
        for f in [SNAP_FILE, CAND_FILE]:
            if f.exists():
                f.unlink()
        regions = get_heap_regions(handle)
        total_mb = sum(s for _, s in regions) / 1024 / 1024
        print(f"  私有堆: {len(regions)} 个区域，{total_mb:.1f} MB")
        n = snapshot_scan(handle, regions)
        print(f"  快照完成，记录 {n:,} 个浮点地址")

        # ── Step 2: 来回移动 + 筛选循环 ──────────────────────────────────────
        for round_i in range(MAX_ROUNDS):
            cur_cnt = candidate_count()
            print(f"\n  [轮次 {round_i + 1}/{MAX_ROUNDS}] 当前候选: {cur_cnt:,}")

            if cur_cnt <= TARGET_CAND and round_i > 0:
                print(f"  候选已 ≤ {TARGET_CAND}，提前结束！")
                break

            # 向右移动
            print(f"  → 向右移动 {MOVE_SECS}s ...")
            _send_move("right", MOVE_SECS)
            time.sleep(0.3)
            kept = rescan(handle, 'increased')
            print(f"    筛选增大后: {kept:,} 个候选")

            if kept == 0:
                print("  候选归零！可能角色被墙阻挡。尝试换方向...")
                # 恢复快照重试
                if SNAP_FILE.exists():
                    import shutil
                    shutil.copy(SNAP_FILE, CAND_FILE)
                _send_move("up", MOVE_SECS)
                time.sleep(0.3)
                kept = rescan(handle, 'changed')
                print(f"    换方向后: {kept:,}")
                if kept == 0:
                    print("  仍然归零，建议检查角色是否卡住。按回车重新快照...")
                    input()
                    n = snapshot_scan(handle, regions)
                    print(f"  重新快照: {n:,} 个")
                    continue

            if candidate_count() <= TARGET_CAND:
                break

            # 向左移动（距离稍大，来回平衡）
            print(f"  ← 向左移动 {MOVE_SECS * 2:.1f}s ...")
            _send_move("left", MOVE_SECS * 2)
            time.sleep(0.3)
            kept = rescan(handle, 'decreased')
            print(f"    筛选减小后: {kept:,} 个候选")

            if kept == 0:
                print("  候选归零，重置快照...")
                if SNAP_FILE.exists():
                    import shutil
                    shutil.copy(SNAP_FILE, CAND_FILE)
                continue

            # 走回右边（保持大致起点位置）
            _send_move("right", MOVE_SECS)
            time.sleep(0.2)

        # ── Step 3: 显示结果 ──────────────────────────────────────────────────
        final_cnt = candidate_count()
        print(f"\n  【自动扫描完成】最终候选: {final_cnt:,} 个")

        if final_cnt == 0:
            print("  没有找到候选地址，请尝试手动模式（选1～5）")
            return

        show_candidates(handle, limit=30)

        if final_cnt <= 30:
            ans = input("\n  是否对第一个候选地址开始实时监控？(y/n): ").strip().lower()
            if ans == 'y':
                src = CAND_FILE if CAND_FILE.exists() else SNAP_FILE
                with open(src, 'rb') as f:
                    raw = f.read(ENTRY_SIZE)
                if raw and len(raw) >= 8:
                    addr = struct.unpack('<Q', raw[:8])[0]
                    monitor_xyz(handle, addr)

    except KeyboardInterrupt:
        print("\n\n  [已中止] 自动扫描已停止")


# ─── 主界面 ───────────────────────────────────────────────────────────────────

BANNER = """
╔══════════════════════════════════════════════════════════════╗
║  D4 内存坐标扫描器 v3.0  (需【管理员权限】运行)              ║
║  目标：找到玩家坐标的动态地址，配合 Cheat Engine 使用        ║
╚══════════════════════════════════════════════════════════════╝
"""

def print_menu(cnt: int):
    status = f"候选: {cnt:,} 个" if cnt else "尚未扫描"
    kb_ok  = "✓ 已安装" if _HAS_KEYBOARD else "✗ 未安装（pip install keyboard）"
    print(f"\n  [{status}]  [keyboard库: {kb_ok}]")
    print("""
  ── 第一步：建立快照 ──────────────────────────────────────────
  1. 快照扫描  (站立不动，记录当前所有私有堆浮点值到磁盘)

  ── 第二步：反复移动 + 筛选，直到候选 < 10 个 ────────────────
  2. 筛选→变化的值     (任意方向移动后执行)
  3. 筛选→增大的值     (向右/某固定方向走后执行)
  4. 筛选→减小的值     (反方向走后执行)
  5. 筛选→不变的值     (原地静止 2 秒后执行，排除噪声)

  ── 自动模式（自动控制角色移动，无需手动操作游戏）──────────
  8. 【自动扫描】快照→自动来回移动→筛选，直到候选 < 20

  ── 辅助 ──────────────────────────────────────────────────────
  6. 显示当前候选地址（查看周围浮点，确认 XYZ 三元组）
  7. 实时监控地址 XYZ（验证某地址是否为坐标）
  0. 退出
""")


def main():
    print(BANNER)

    pid = get_pid("Diablo IV.exe")
    if not pid:
        print("[错误] 未找到 Diablo IV.exe\n请先启动游戏（单机/脱机模式）后再运行此工具")
        input("按回车退出...")
        sys.exit(1)
    print(f"[OK] 找到进程 PID: {pid}")

    try:
        handle = open_process(pid)
    except PermissionError as e:
        print(f"[错误] {e}")
        input("按回车退出...")
        sys.exit(1)
    print("[OK] 已附加进程（只读模式，不会修改游戏内存）\n")
    print("  提示：只扫描私有堆内存（游戏对象所在区域），")
    print(f"  跳过 >{ MAX_REGION_MB}MB 的大区域，避免资源文件干扰。\n")

    while True:
        cnt = candidate_count()
        print_menu(cnt)
        cmd = input("  输入命令编号: ").strip()

        if cmd == '8':
            _auto_scan(handle)
            continue

        if cmd == '1':
            regions = get_heap_regions(handle)
            total_mb = sum(s for _, s in regions) / 1024 / 1024
            print(f"\n  私有堆: {len(regions)} 个区域，共 {total_mb:.1f} MB")
            print("  站立不动，开始扫描...\n")
            for f in [SNAP_FILE, CAND_FILE]:
                if f.exists():
                    f.unlink()
            n = snapshot_scan(handle, regions)
            print(f"  [完成] 记录 {n:,} 个浮点地址")
            print("\n  下一步：在游戏中移动角色，然后选 2、3 或 4 进行筛选")

        elif cmd in ('2', '3', '4', '5'):
            mode_map  = {'2': 'changed', '3': 'increased', '4': 'decreased', '5': 'unchanged'}
            guide_map = {
                '2': '向任意方向移动角色',
                '3': '向右方（或某固定方向）移动一段距离',
                '4': '向相反方向走回来',
                '5': '原地静止约 2 秒（不要移动）',
            }
            print(f"\n  [操作] {guide_map[cmd]}，完成后按回车")
            input("  准备好了按回车: ")
            kept = rescan(handle, mode_map[cmd])
            print(f"  [结果] 筛选后剩余: {kept:,} 个候选")
            if kept == 0:
                print("  提示：候选归零，可能移动幅度太小或噪声太多，建议重新快照（选1）")
            elif kept < 20:
                print("  候选很少了！选 6 查看地址，选 7 监控确认")
            elif kept > 100000:
                print("  候选仍然较多，继续交替执行选3和选4（来回走）")

        elif cmd == '6':
            show_candidates(handle)

        elif cmd == '7':
            addr_in = input(
                "\n  输入地址（0x... 格式）\n"
                "  或直接回车使用第一个候选: "
            ).strip()
            if addr_in:
                try:
                    addr = int(addr_in, 16)
                except ValueError:
                    print("  [错误] 格式不对，应为如 0x1A2B3C4D5E6F")
                    continue
            else:
                src = CAND_FILE if CAND_FILE.exists() else SNAP_FILE
                if not src or not src.exists():
                    print("  [错误] 无候选文件")
                    continue
                with open(src, 'rb') as f:
                    raw = f.read(ENTRY_SIZE)
                if not raw or len(raw) < 8:
                    print("  [错误] 候选文件为空")
                    continue
                addr = struct.unpack('<Q', raw[:8])[0]
            monitor_xyz(handle, addr)

        elif cmd == '0':
            break
        else:
            print("  未知命令，请输入 0-7")

    kernel32.CloseHandle(handle)
    print("\n[退出] 已释放进程句柄")


if __name__ == "__main__":
    main()
