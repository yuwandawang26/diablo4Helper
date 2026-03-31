#!/usr/bin/env python3
"""
D4 指针链扫描器 v1.0
在 mem_scanner.py 找到动态地址后，使用此工具寻找指向该地址的静态指针链

原理：
  游戏每次重启，动态地址会改变。
  需要找到一条从"模块静态基址 + 固定偏移"出发的指针链，
  每次都能解析到最终的坐标地址。

使用方法：
  python pointer_scan.py
  根据提示输入 mem_scanner.py 找到的目标动态地址
"""

import ctypes
import ctypes.wintypes
import struct
import json
import sys
import subprocess
import time
from pathlib import Path

kernel32 = ctypes.windll.kernel32

PROCESS_VM_READ           = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT                = 0x1000

class MEMORY_BASIC_INFORMATION64(ctypes.Structure):
    _fields_ = [
        ("BaseAddress",       ctypes.c_ulonglong),
        ("AllocationBase",    ctypes.c_ulonglong),
        ("AllocationProtect", ctypes.wintypes.DWORD),
        ("__alignment1",      ctypes.wintypes.DWORD),
        ("RegionSize",        ctypes.c_ulonglong),
        ("State",             ctypes.wintypes.DWORD),
        ("Protect",           ctypes.wintypes.DWORD),
        ("Type",              ctypes.wintypes.DWORD),
        ("__alignment2",      ctypes.wintypes.DWORD),
    ]

# ─── 基础工具 ──────────────────────────────────────────────────────────────────

def get_pid(name: str) -> int | None:
    result = subprocess.run(
        ['tasklist', '/FI', f'IMAGENAME eq {name}', '/FO', 'CSV', '/NH'],
        capture_output=True, text=True, encoding='gbk', errors='ignore'
    )
    for line in result.stdout.strip().split('\n'):
        if name.lower() in line.lower():
            parts = line.replace('"', '').split(',')
            if len(parts) >= 2:
                try:
                    return int(parts[1].strip())
                except ValueError:
                    pass
    return None

def open_process(pid: int) -> int:
    handle = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not handle:
        raise PermissionError(f"OpenProcess 失败，错误码={kernel32.GetLastError()}")
    return handle

def read_bytes(handle: int, address: int, size: int) -> bytes | None:
    buf = ctypes.create_string_buffer(size)
    n = ctypes.c_size_t(0)
    ok = kernel32.ReadProcessMemory(handle, ctypes.c_void_p(address), buf, size, ctypes.byref(n))
    return buf.raw[:n.value] if ok and n.value else None

def read_pointer(handle: int, address: int) -> int | None:
    data = read_bytes(handle, address, 8)
    if not data or len(data) < 8:
        return None
    val = struct.unpack('<Q', data)[0]
    return val if 0x10000 < val < 0x00007FFFFFFFFFFF else None

def read_float(handle: int, address: int) -> float | None:
    data = read_bytes(handle, address, 4)
    if not data or len(data) < 4:
        return None
    return struct.unpack('<f', data)[0]

# ─── 模块基址枚举 ──────────────────────────────────────────────────────────────

class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize",        ctypes.wintypes.DWORD),
        ("th32ModuleID",  ctypes.wintypes.DWORD),
        ("th32ProcessID", ctypes.wintypes.DWORD),
        ("GlblcntUsage",  ctypes.wintypes.DWORD),
        ("ProccntUsage",  ctypes.wintypes.DWORD),
        ("modBaseAddr",   ctypes.c_ulonglong),
        ("modBaseSize",   ctypes.wintypes.DWORD),
        ("hModule",       ctypes.wintypes.HMODULE),
        ("szModule",      ctypes.c_char * 256),
        ("szExePath",     ctypes.c_char * 260),
    ]

TH32CS_SNAPMODULE   = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010

def get_modules(pid: int) -> list[tuple[str, int, int]]:
    """返回进程所有模块的 (name, base, size) 列表"""
    modules = []
    snapshot = kernel32.CreateToolhelp32Snapshot(
        TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid
    )
    if snapshot == ctypes.wintypes.HANDLE(-1).value:
        return modules

    entry = MODULEENTRY32()
    entry.dwSize = ctypes.sizeof(entry)

    if kernel32.Module32First(snapshot, ctypes.byref(entry)):
        while True:
            name = entry.szModule.decode('utf-8', errors='ignore')
            modules.append((name, entry.modBaseAddr, entry.modBaseSize))
            if not kernel32.Module32Next(snapshot, ctypes.byref(entry)):
                break

    kernel32.CloseHandle(snapshot)
    return modules

# ─── 指针链扫描核心 ───────────────────────────────────────────────────────────

def get_readable_regions(handle: int) -> list[tuple[int, int]]:
    regions = []
    address = 0
    mbi = MEMORY_BASIC_INFORMATION64()
    while address < 0x00007FFFFFFFFFFF:
        ret = kernel32.VirtualQueryEx(handle, ctypes.c_void_p(address), ctypes.byref(mbi), ctypes.sizeof(mbi))
        if not ret:
            break
        protect_ok = mbi.Protect in {0x02, 0x04, 0x20, 0x40}
        if mbi.State == MEM_COMMIT and protect_ok and mbi.RegionSize > 0:
            regions.append((mbi.BaseAddress, mbi.RegionSize))
        next_addr = mbi.BaseAddress + mbi.RegionSize
        if next_addr <= address:
            break
        address = next_addr
    return regions

CHUNK = 0x10000  # 64KB

def find_pointers_to(handle: int, target: int,
                     regions: list[tuple[int, int]]) -> list[int]:
    """
    在所有可读内存中找到所有"指向 target 附近"的指针地址
    允许偏移范围 [target-max_offset, target]，max_offset=0x1000
    """
    max_offset = 0x1000
    lo = target - max_offset
    hi = target
    results = []
    target_bytes_lo = struct.pack('<Q', lo)
    target_bytes_hi = struct.pack('<Q', hi)

    for base, size in regions:
        for off in range(0, size - 7, CHUNK):
            chunk_size = min(CHUNK, size - off)
            data = read_bytes(handle, base + off, chunk_size)
            if not data:
                continue
            # 8字节对齐扫描指针
            for i in range(0, len(data) - 7, 8):
                val = struct.unpack_from('<Q', data, i)[0]
                if lo <= val <= hi:
                    results.append(base + off + i)
    return results

def resolve_chain(handle: int, base: int, offsets: list[int]) -> int | None:
    """解析指针链，返回最终地址"""
    addr = base
    for off in offsets[:-1]:
        ptr = read_pointer(handle, addr + off)
        if ptr is None:
            return None
        addr = ptr
    return addr + offsets[-1]

def scan_pointer_chain(handle: int, target_addr: int,
                       module_base: int, module_size: int,
                       max_depth: int = 5,
                       max_offset: int = 0x800) -> list[list[int]]:
    """
    BFS 指针链扫描：从 target_addr 向上追溯，
    找到从"模块静态地址"出发的指针链
    
    返回：满足条件的偏移链列表，每个元素为 [offset0, offset1, ..., final_offset]
    """
    regions = get_readable_regions(handle)
    valid_chains: list[list[int]] = []

    # BFS 队列：(当前地址, 到目前为止的偏移链)
    # 偏移链格式：从最终地址反向存储（最后的偏移在最前）
    queue: list[tuple[int, list[int]]] = [(target_addr, [])]
    visited = set()

    print(f"  BFS 搜索指针链（最大深度={max_depth}，每层最大偏移=0x{max_offset:X}）")
    print(f"  模块范围: 0x{module_base:016X} ~ 0x{module_base+module_size:016X}")

    for depth in range(max_depth):
        next_queue = []
        print(f"\n  深度 {depth+1}: 当前节点数 {len(queue)}")

        for cur_addr, chain in queue:
            if cur_addr in visited:
                continue
            visited.add(cur_addr)

            # 找所有指向 cur_addr 附近的指针
            pointers = find_pointers_to(handle, cur_addr, regions)

            for ptr_addr in pointers:
                offset = cur_addr - read_pointer(handle, ptr_addr)  # 实际偏移
                if offset < 0 or offset > max_offset:
                    continue

                new_chain = [offset] + chain

                # 检查 ptr_addr 是否在模块静态区域内
                if module_base <= ptr_addr < module_base + module_size:
                    static_offset = ptr_addr - module_base
                    full_chain = [static_offset] + new_chain
                    valid_chains.append(full_chain)
                    print(f"  [发现] 深度={depth+1} 链: base+0x{static_offset:X} "
                          f"-> {' -> '.join(f'0x{o:X}' for o in new_chain)}")

                next_queue.append((ptr_addr, new_chain))

        queue = next_queue
        if not queue or len(valid_chains) >= 20:
            break

    return valid_chains

# ─── 验证指针链 ────────────────────────────────────────────────────────────────

def verify_chain(handle: int, module_base: int,
                 chain: list[int], expected_val: float,
                 tolerance: float = 1.0) -> bool:
    """验证指针链是否能解析到预期的浮点值"""
    addr = resolve_chain(handle, module_base, chain)
    if addr is None:
        return False
    val = read_float(handle, addr)
    return val is not None and abs(val - expected_val) < tolerance

# ─── 主程序 ───────────────────────────────────────────────────────────────────

RESULT_FILE = Path(__file__).parent / "d4_pointer_chains.json"

def main():
    print("""
╔══════════════════════════════════════════════════════╗
║       D4 指针链扫描器  (需管理员权限运行)            ║
║  在 mem_scanner.py 找到坐标地址后，运行此工具        ║
╚══════════════════════════════════════════════════════╝
""")

    pid = get_pid("Diablo IV.exe")
    if not pid:
        print("[错误] 未找到 Diablo IV.exe")
        input("按回车退出...")
        sys.exit(1)

    print(f"[OK] PID: {pid}")
    handle = open_process(pid)
    print("[OK] 已附加进程\n")

    modules = get_modules(pid)
    main_module = next((m for m in modules if 'diablo iv' in m[0].lower()), None)
    if not main_module:
        # fallback：选第一个
        main_module = modules[0] if modules else None

    if not main_module:
        print("[错误] 无法获取模块信息")
        sys.exit(1)

    mod_name, mod_base, mod_size = main_module
    print(f"[模块] {mod_name}")
    print(f"       基址: 0x{mod_base:016X}  大小: 0x{mod_size:X}\n")
    print("  所有已加载模块：")
    for name, base, size in modules[:10]:
        print(f"    {name:40s}  0x{base:016X}  (0x{size:X} bytes)")
    if len(modules) > 10:
        print(f"    ... 共 {len(modules)} 个模块")

    print("\n" + "─" * 60)
    print("  请输入 mem_scanner.py 找到的目标坐标地址")
    print("  （即 X 坐标所在的动态地址）")

    addr_str = input("\n  目标地址 (0x...): ").strip()
    try:
        target = int(addr_str, 16)
    except ValueError:
        print("[错误] 地址格式错误")
        sys.exit(1)

    cur_x = read_float(handle, target)
    cur_y = read_float(handle, target + 4)
    cur_z = read_float(handle, target + 8)
    print(f"\n  当前读取到的值: X={cur_x}  Y={cur_y}  Z={cur_z}")
    if cur_x is None:
        print("[警告] 无法读取该地址，请确认地址正确")

    print(f"\n  开始扫描指针链，这可能需要几分钟...")
    t0 = time.time()
    chains = scan_pointer_chain(handle, target, mod_base, mod_size)
    elapsed = time.time() - t0

    print(f"\n  扫描完成，耗时 {elapsed:.1f}s，找到 {len(chains)} 条候选指针链")

    if chains:
        print("\n  ═══ 候选指针链 ═══")
        for i, chain in enumerate(chains):
            static_off = chain[0]
            inner_offs = chain[1:]
            chain_str = f"Diablo IV.exe + 0x{static_off:X}"
            for off in inner_offs:
                chain_str += f" -> [+0x{off:X}]"
            print(f"  [{i:02d}] {chain_str}")

        # 验证
        if cur_x is not None:
            print("\n  验证各链（当前X值作为参考）：")
            for i, chain in enumerate(chains):
                ok = verify_chain(handle, mod_base, chain, cur_x)
                status = "✓ 有效" if ok else "✗ 无效"
                print(f"  [{i:02d}] {status}")

        # 保存
        result = {
            "module": mod_name,
            "module_base_hex": hex(mod_base),
            "target_addr_hex": hex(target),
            "chains": [
                {
                    "static_offset": hex(c[0]),
                    "pointer_offsets": [hex(o) for o in c[1:]],
                    "description": f"Diablo IV.exe + {hex(c[0])} -> " +
                                   " -> ".join(f"[+{hex(o)}]" for o in c[1:])
                }
                for c in chains
            ]
        }
        RESULT_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"\n  [已保存] 结果写入 {RESULT_FILE}")
    else:
        print("  未找到有效指针链。可能原因：")
        print("    1. 目标地址不是通过指针访问的（直接静态地址？）")
        print("    2. 扫描深度不够 (尝试增大 max_depth)")
        print("    3. 指针偏移超过 0x800（尝试增大 max_offset）")

    kernel32.CloseHandle(handle)
    print("\n[退出]")


if __name__ == "__main__":
    main()
