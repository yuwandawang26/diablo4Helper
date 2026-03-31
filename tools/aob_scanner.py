#!/usr/bin/env python3
"""
D4 AOB 特征码扫描器 v1.0
自动在 Diablo IV.exe 代码段中找到访问 ClassMGR 全局指针的指令，
从中提取当前版本的 classmgr_offset，无需手动查偏移。

前提：
  已通过 Cheat Engine 或 x64dbg 找到一个 AOB 特征码（见 PATTERNS 字典）。
  首次使用需要填入特征码；之后每次版本更新只需重跑此脚本。

运行方式：
  管理员 PowerShell → python aob_scanner.py
"""

import ctypes
import ctypes.wintypes
import struct
import json
import sys
import math
import random
import time
from pathlib import Path

kernel32 = ctypes.windll.kernel32
psapi    = ctypes.windll.psapi

PROCESS_VM_READ           = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT  = 0x1000
MEM_IMAGE   = 0x1000000  # PE 镜像（代码区）
READABLE    = {0x02, 0x04, 0x20, 0x40}

OFFSETS_FILE = Path(__file__).parent / "d4_offsets.json"

# ─── AOB 特征码库 ─────────────────────────────────────────────────────────────
#
# 每条记录：
#   pattern    : bytes，'??' 用 None 占位
#   rip_at     : 4字节相对偏移在 pattern 中的起始索引（以字节计）
#   instr_len  : 整条指令的长度（计算 RIP 基准地址用）
#   description: 说明
#
# 如何获取新版本的特征码（只需做一次）：
#   1. 用 x64dbg 附加游戏
#   2. 搜索引用到 classmgr 全局变量的指令
#      典型形如：mov rax, [rip+xxxxxxxx]  →  48 8B 05 ?? ?? ?? ??
#   3. 复制该指令前后约 10 字节，其中 ?? 表示会变化的偏移字节
#   4. 添加到下方 PATTERNS 列表

PATTERNS: list[dict] = [
    # ── 旧版参考（2023-2024），可能已失效，但留作 AOB 格式示例 ──
    {
        "label":       "classmgr_mov_rax (示例，需用x64dbg确认)",
        "pattern":     [0x48, 0x8B, 0x05, None, None, None, None, 0x48, 0x85, 0xC0],
        "rip_at":      3,
        "instr_len":   7,
        "description": "mov rax, [rip+offset]; test rax,rax",
        "enabled":     False,   # ← 改为 True 后才会被扫描
    },
    {
        "label":       "classmgr_mov_rcx (示例，需用x64dbg确认)",
        "pattern":     [0x48, 0x8B, 0x0D, None, None, None, None, 0x48, 0x85, 0xC9],
        "rip_at":      3,
        "instr_len":   7,
        "description": "mov rcx, [rip+offset]; test rcx,rcx",
        "enabled":     False,
    },
    # ── 在此添加从 x64dbg 找到的新版本特征码 ──
    # {
    #     "label":      "classmgr_v202x",
    #     "pattern":    [0x48, 0x8B, 0x05, None, None, None, None, ...],
    #     "rip_at":     3,
    #     "instr_len":  7,
    #     "description": "从 x64dbg 复制的当前版本特征",
    #     "enabled":    True,
    # },
]

# ─── 进程工具 ─────────────────────────────────────────────────────────────────

MAX_PROCESSES = 1024

def get_pid(name: str = "Diablo IV.exe") -> int | None:
    buf     = (ctypes.wintypes.DWORD * MAX_PROCESSES)()
    needed  = ctypes.wintypes.DWORD(0)
    psapi.EnumProcesses(buf, ctypes.sizeof(buf), ctypes.byref(needed))
    count   = needed.value // ctypes.sizeof(ctypes.wintypes.DWORD)
    nbuf    = ctypes.create_unicode_buffer(260)
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

def open_process(pid: int) -> int:
    h = kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        raise PermissionError(f"OpenProcess 失败 (错误码={kernel32.GetLastError()})")
    return h

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

def read_pointer(handle: int, addr: int) -> int | None:
    d = read_bytes(handle, addr, 8)
    if not d or len(d) < 8:
        return None
    v = struct.unpack('<Q', d)[0]
    return v if 0x10000 < v < 0x7FFFFFFFFFFF else None

# ─── 模块基址 ─────────────────────────────────────────────────────────────────

class MODULEENTRY(ctypes.Structure):
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

def get_module_base(pid: int, module: str = "Diablo IV.exe") -> tuple[int, int]:
    """返回 (base_address, module_size)"""
    snap = kernel32.CreateToolhelp32Snapshot(0x00000008 | 0x00000010, pid)
    if snap == ctypes.wintypes.HANDLE(-1).value:
        return 0, 0
    entry = MODULEENTRY()
    entry.dwSize = ctypes.sizeof(entry)
    if kernel32.Module32First(snap, ctypes.byref(entry)):
        while True:
            name = entry.szModule.decode('utf-8', errors='ignore')
            if module.lower() in name.lower():
                kernel32.CloseHandle(snap)
                return entry.modBaseAddr, entry.modBaseSize
            if not kernel32.Module32Next(snap, ctypes.byref(entry)):
                break
    kernel32.CloseHandle(snap)
    return 0, 0

# ─── IAT 版本指纹 ──────────────────────────────────────────────────────────────

# 读取 IAT 第一项（CryptGetHashParam 的 IAT 地址）来识别游戏版本
# 这里存的是 IAT 相对模块基址的偏移（从 REF 数据已知三个旧版本）
KNOWN_IAT_OFFSETS = {
    0x1d4a000: "REF版 (2023)",
    0x1d47000: "旧版v1 (2023)",
    0x1d50000: "旧版v2 (2024)",
}

def detect_version(handle: int, module_base: int) -> str:
    """
    通过读取模块内 IAT 区第一项的实际地址，推断游戏版本。
    仅作参考，当前版本大概率是新版本。
    """
    for rel_offset, label in KNOWN_IAT_OFFSETS.items():
        ptr = read_pointer(handle, module_base + rel_offset)
        if ptr and ptr > 0x7FF000000000:  # 系统 DLL 通常在高地址
            return f"{label} (IAT匹配 0x{rel_offset:x})"
    return "未知版本（当前版本，需重新扫描特征码）"

# ─── AOB 扫描 ─────────────────────────────────────────────────────────────────

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

CHUNK = 0x100000  # 1MB

def get_image_regions(handle: int, module_base: int, module_size: int) -> list[tuple[int, int]]:
    """返回模块的 MEM_IMAGE 可执行区域"""
    regions = []
    addr = module_base
    end  = module_base + module_size
    mbi  = MBI()
    while addr < end:
        if not kernel32.VirtualQueryEx(handle, ctypes.c_void_p(addr),
                                       ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        if (mbi.State == MEM_COMMIT
                and mbi.Type == MEM_IMAGE
                and mbi.Protect in READABLE
                and mbi.RegionSize > 0):
            regions.append((mbi.BaseAddress, mbi.RegionSize))
        nxt = mbi.BaseAddress + mbi.RegionSize
        if nxt <= addr:
            break
        addr = nxt
    return regions


def aob_scan(handle: int, regions: list[tuple[int, int]],
             pattern: list[int | None]) -> list[int]:
    """
    在给定内存区域中搜索字节特征码，None 表示通配。
    返回所有匹配的起始地址列表。
    """
    plen    = len(pattern)
    matches = []
    total   = sum(s for _, s in regions)
    scanned = 0

    for base, size in regions:
        for off in range(0, size, CHUNK):
            chunk_sz = min(CHUNK + plen, size - off)
            data = read_bytes(handle, base + off, chunk_sz)
            if not data:
                continue
            for i in range(len(data) - plen + 1):
                if all(pattern[j] is None or data[i + j] == pattern[j]
                       for j in range(plen)):
                    matches.append(base + off + i)
        scanned += size
        pct = scanned / total * 100
        print(f"\r  AOB 扫描 {pct:5.1f}%  匹配: {len(matches)}", end='', flush=True)

    print()
    return matches


def extract_classmgr_offset(handle: int, match_addr: int,
                             rip_at: int, instr_len: int,
                             module_base: int) -> int | None:
    """
    从匹配地址读取 RIP 相对偏移，计算 classmgr 的模块内静态偏移。
    公式：classmgr_abs = (match_addr + rip_at + 4-byte-signed-offset + instr_len)
          classmgr_offset = classmgr_abs - module_base
    """
    d = read_bytes(handle, match_addr + rip_at, 4)
    if not d or len(d) < 4:
        return None
    rel = struct.unpack('<i', d)[0]  # 有符号 32-bit 相对偏移
    abs_addr = match_addr + rip_at + 4 + rel   # +4 因为偏移本身占4字节
    # 严格说 instr_len 应减去 rip_at + 4，但通常 rip_at + 4 == instr_len
    # 所以: next_instr = match_addr + instr_len
    #       classmgr_abs = next_instr + (rel - correction)
    # 简化：直接用下面公式
    classmgr_abs = match_addr + instr_len + rel + (rip_at - instr_len + 4)
    # 标准公式：next_rip = match_addr + instr_len
    #            data_ptr = next_rip + signed_offset
    next_rip     = match_addr + instr_len
    data_d = read_bytes(handle, match_addr + rip_at, 4)
    if not data_d:
        return None
    signed_off   = struct.unpack('<i', data_d)[0]
    classmgr_abs = next_rip + signed_off
    offset       = classmgr_abs - module_base
    if offset < 0 or offset > 0x10000000:  # 合理性检查
        return None
    return offset


def verify_classmgr(handle: int, module_base: int, classmgr_offset: int) -> bool:
    """
    验证 classmgr 偏移：读取指针后再读 +0xA18（旧版 ractors 偏移），
    检查是否是一个合理的堆指针。
    """
    classmgr_ptr = read_pointer(handle, module_base + classmgr_offset)
    if not classmgr_ptr:
        return False
    # 尝试读 classmgr 后的几个常见 ractors 偏移
    for candidate_off in [0xA18, 0xA20, 0xA10, 0xA28, 0xA00]:
        ractors_ptr = read_pointer(handle, classmgr_ptr + candidate_off)
        if ractors_ptr and ractors_ptr > 0x10000:
            return True
    return False

# ─── 配置文件读写 ─────────────────────────────────────────────────────────────

def load_offsets() -> dict:
    if not OFFSETS_FILE.exists():
        return {}
    try:
        return json.loads(OFFSETS_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {}

def save_offsets(data: dict):
    OFFSETS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )
    print(f"  [保存] {OFFSETS_FILE}")

# ─── 交互式主程序 ─────────────────────────────────────────────────────────────

def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║  D4 AOB 特征码扫描器 v1.0  (需【管理员权限】运行)           ║
║  自动在游戏代码段中找到 ClassMGR 的当前版本偏移              ║
╚══════════════════════════════════════════════════════════════╝
""")

    pid = get_pid("Diablo IV.exe")
    if not pid:
        print("[错误] 未找到 Diablo IV.exe，请先启动游戏")
        input("按回车退出...")
        sys.exit(1)
    print(f"[OK] PID: {pid}")

    handle = open_process(pid)
    print("[OK] 已附加进程（只读）\n")

    module_base, module_size = get_module_base(pid, "Diablo IV.exe")
    if not module_base:
        print("[错误] 无法获取模块基址")
        sys.exit(1)
    print(f"[模块] Diablo IV.exe  基址: 0x{module_base:016X}  大小: 0x{module_size:X}")

    version = detect_version(handle, module_base)
    print(f"[版本] {version}\n")

    # 显示已有配置
    offsets = load_offsets()
    if offsets.get('current', {}).get('classmgr_offset'):
        cur = offsets['current']
        print(f"[已有配置] classmgr_offset = 0x{cur['classmgr_offset']:X}")
        print(f"           ractors_from_classmgr = {cur.get('ractors_from_classmgr', '未知')}")
        print(f"           verified = {cur.get('verified', False)}\n")

    # 列出可用的 AOB 模式
    enabled = [p for p in PATTERNS if p.get('enabled', False)]
    print(f"[AOB模式] 已配置 {len(PATTERNS)} 个，已启用 {len(enabled)} 个")
    for p in PATTERNS:
        status = "✓启用" if p.get('enabled') else "✗禁用"
        print(f"  [{status}] {p['label']}")

    if not enabled:
        print("""
  ⚠ 没有启用的 AOB 模式！

  要使用此工具，你需要先用 x64dbg 找到特征码：
  ─────────────────────────────────────────────
  1. 用 x64dbg 附加 Diablo IV.exe（不需要管理员，x64dbg 本身会处理）
  2. 在命令栏输入：bp kernel32.ReadProcessMemory  ← 先不管这个
  3. 用 Ctrl+G 转到地址，搜索 "classmgr" 相关的全局访问：
     在 CPU 面板用 Ctrl+F 搜索字节序列：48 8B 05 ?? ?? ?? ?? 48 85 C0
     或搜索：48 8B 0D ?? ?? ?? ?? 48 85 C9
  4. 找到后，复制该指令及前后 3 字节的完整 hex 序列
  5. 将序列填入 aob_scanner.py 顶部的 PATTERNS 列表并设 enabled=True

  也可以先用 Cheat Engine 的指针扫描找到 classmgr，
  然后在 x64dbg 里对该地址下内存访问断点，找到读取它的指令。
  ─────────────────────────────────────────────
""")
        input("按回车退出...")
        kernel32.CloseHandle(handle)
        return

    # 执行 AOB 扫描
    print(f"\n  扫描 Diablo IV.exe 代码段（共 {module_size / 1024 / 1024:.0f} MB）...")
    regions = get_image_regions(handle, module_base, module_size)
    print(f"  IMAGE 区域: {len(regions)} 个")

    found_offsets = []
    for pattern_def in enabled:
        print(f"\n  [模式] {pattern_def['label']}")
        matches = aob_scan(handle, regions, pattern_def['pattern'])
        print(f"  匹配数: {len(matches)}")
        for m in matches[:10]:  # 最多处理前10个
            offset = extract_classmgr_offset(
                handle, m,
                pattern_def['rip_at'],
                pattern_def['instr_len'],
                module_base
            )
            if offset is None:
                continue
            valid = verify_classmgr(handle, module_base, offset)
            status = "✓验证通过" if valid else "✗验证失败"
            print(f"  0x{m:016X} → classmgr_offset=0x{offset:X}  {status}")
            if valid:
                found_offsets.append(offset)

    if not found_offsets:
        print("\n  未找到有效的 classmgr 偏移。可能原因：")
        print("    1. AOB 特征码已失效（游戏更新后代码改变）")
        print("    2. 特征码填写有误")
        print("    3. 当前版本使用了不同的指令序列")
        print("\n  建议：用 x64dbg 重新找特征码")
    else:
        # 取第一个通过验证的
        best = found_offsets[0]
        print(f"\n  [成功] 最终 classmgr_offset = 0x{best:X}")

        # 尝试探测 ractors 偏移
        classmgr_ptr = read_pointer(handle, module_base + best)
        ractors_off  = None
        print(f"  classmgr 指针 = 0x{classmgr_ptr:016X}")
        print("  探测 ractors 偏移...")
        for coff in [0xA18, 0xA20, 0xA10, 0xA28, 0xA00, 0xA30, 0xA40]:
            ptr = read_pointer(handle, classmgr_ptr + coff)
            if ptr and ptr > 0x10000:
                print(f"    classmgr + 0x{coff:X} = 0x{ptr:016X}  ← 可能是 ractors")
                if ractors_off is None:
                    ractors_off = coff

        # 更新配置
        offsets = load_offsets()
        if 'current' not in offsets:
            offsets['current'] = {}
        offsets['current']['classmgr_offset']      = best
        offsets['current']['ractors_from_classmgr'] = ractors_off
        offsets['current']['verified']              = True
        offsets['current']['last_scan_base']        = hex(module_base)
        save_offsets(offsets)

    kernel32.CloseHandle(handle)
    print("\n[完成]")


if __name__ == "__main__":
    main()
