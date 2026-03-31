"""
实时验证候选地址脚本
读取 d4_candidates.bin 中的所有地址，实时显示它们的值，
移动角色时观察哪些值在变化 -> 那些就是坐标地址。
需管理员权限运行。
"""
import ctypes, ctypes.wintypes, struct, math, time, sys
from pathlib import Path

kernel32 = ctypes.windll.kernel32
psapi    = ctypes.windll.psapi
PROCESS_VM_READ           = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

CAND_FILE = Path(__file__).parent / "d4_candidates.bin"
ENTRY_SIZE = 12

def find_pid(name="Diablo IV.exe"):
    buf = (ctypes.wintypes.DWORD * 1024)()
    nb  = ctypes.wintypes.DWORD(0)
    psapi.EnumProcesses(buf, ctypes.sizeof(buf), ctypes.byref(nb))
    nbuf = ctypes.create_unicode_buffer(260)
    for pid in list(buf[:nb.value // 4]):
        if not pid: continue
        h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not h: continue
        psapi.GetModuleBaseNameW(h, None, nbuf, 260)
        n = nbuf.value
        kernel32.CloseHandle(h)
        if n.lower() == name.lower():
            return pid
    return None

def read_float(h, addr):
    buf = ctypes.create_string_buffer(4)
    n   = ctypes.c_size_t(0)
    ok  = kernel32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, 4, ctypes.byref(n))
    if not (ok and n.value == 4): return None
    v = struct.unpack('<f', buf.raw)[0]
    return None if not math.isfinite(v) else v

def read_nearby_3(h, addr):
    """读地址及前后各4字节，共3个float"""
    buf = ctypes.create_string_buffer(12)
    n   = ctypes.c_size_t(0)
    ok  = kernel32.ReadProcessMemory(h, ctypes.c_void_p(addr - 4), buf, 12, ctypes.byref(n))
    if not (ok and n.value == 12): return None, None, None
    return struct.unpack('<fff', buf.raw)

def main():
    if not CAND_FILE.exists():
        print("找不到候选文件 d4_candidates.bin")
        input("回车退出"); return

    data = CAND_FILE.read_bytes()
    n    = len(data) // ENTRY_SIZE
    candidates = []
    for i in range(n):
        addr, snap_val = struct.unpack_from('<Qf', data, i * ENTRY_SIZE)
        candidates.append((addr, snap_val))

    print(f"加载 {n} 个候选地址")

    pid = find_pid()
    if not pid:
        print("未找到游戏进程"); input("回车退出"); return

    h = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        print(f"OpenProcess 失败 err={kernel32.GetLastError()} (需管理员权限)")
        input("回车退出"); return

    print(f"PID={pid} 已附加\n")
    print("=" * 90)
    print(f"  移动角色，观察哪些地址的值在变化。Ctrl+C 停止。")
    print("=" * 90)

    # 读第一次作为基准
    baseline = {}
    for addr, _ in candidates:
        v = read_float(h, addr)
        baseline[addr] = v

    interval = 0.4
    round_n  = 0

    try:
        while True:
            round_n += 1
            time.sleep(interval)

            changed = []
            for addr, snap_val in candidates:
                cur = read_float(h, addr)
                if cur is None: continue
                base = baseline[addr]
                delta = (cur - base) if base is not None else 0
                if abs(delta) > 0.05:  # 变化超过 0.05 才显示
                    # 读周围3个float
                    p, c, nx = read_nearby_3(h, addr)
                    changed.append((addr, snap_val, cur, delta, p, c, nx))

            if changed:
                print(f"\n── 轮次 {round_n}  发现 {len(changed)} 个变化中的地址 ──")
                print(f"  {'地址':>18s}  {'快照值':>10s}  {'当前值':>10s}  {'变化量':>9s}  {'前-自-后 (三元组)':s}")
                for addr, snap, cur, delta, p, c, nx in changed:
                    ps = f"{p:.3f}" if p is not None and math.isfinite(p) else "?"
                    cs = f"{c:.3f}" if c is not None and math.isfinite(c) else "?"
                    ns = f"{nx:.3f}" if nx is not None and math.isfinite(nx) else "?"
                    sign = "+" if delta > 0 else ""
                    print(f"  0x{addr:016X}  {snap:>10.4f}  {cur:>10.4f}  {sign}{delta:>8.4f}  [{ps}, {cs}, {ns}]")

                # 更新基准
                for addr, *_ in changed:
                    baseline[addr] = read_float(h, addr)
            else:
                print(f"\r  轮次 {round_n}  无变化（请移动角色）", end='', flush=True)

    except KeyboardInterrupt:
        print("\n\n已停止")

    kernel32.CloseHandle(h)

if __name__ == "__main__":
    main()
