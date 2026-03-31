"""
从动态 Z 地址反向查找 Cheat Engine 风格指针链（仅「读指针 + 加偏移」模型）。

与 d4reader.resolve_pointer_chain 一致：
  ptr = module_base + offsets[0]
  for off in offsets[1:]:
      ptr = read_u64(ptr) + off

默认中间偏移为 0（纯指针链）。若失败可改用 Cheat Engine 手动扫描。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import struct
from pathlib import Path

kernel32 = ctypes.windll.kernel32
psapi    = ctypes.windll.psapi

PROCESS_VM_READ           = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT  = 0x1000
MEM_PRIVATE = 0x20000
READABLE    = {0x02, 0x04, 0x20, 0x40}
MAX_REGION_MB = 64
CHUNK         = 0x100000  # 1MB

class MBI(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_ulonglong),
        ("AllocationBase", ctypes.c_ulonglong),
        ("AllocationProtect", ctypes.wintypes.DWORD),
        ("_pad1", ctypes.wintypes.DWORD),
        ("RegionSize", ctypes.c_ulonglong),
        ("State", ctypes.wintypes.DWORD),
        ("Protect", ctypes.wintypes.DWORD),
        ("Type", ctypes.wintypes.DWORD),
        ("_pad2", ctypes.wintypes.DWORD),
    ]

def _read_bytes(h: int, addr: int, size: int) -> bytes | None:
    buf = ctypes.create_string_buffer(size)
    n   = ctypes.c_size_t(0)
    ok  = kernel32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(n))
    return buf.raw[:n.value] if (ok and n.value > 0) else None

def _read_u64(h: int, addr: int) -> int | None:
    d = _read_bytes(h, addr, 8)
    if not d or len(d) < 8:
        return None
    return struct.unpack('<Q', d)[0]

def _get_private_regions(h: int) -> list[tuple[int, int]]:
    regions = []
    addr = 0
    mbi  = MBI()
    max_b = MAX_REGION_MB * 1024 * 1024
    while addr < 0x7FFFFFFFFFFF:
        if not kernel32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
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

def find_addresses_with_qword_value(h: int, target: int, regions: list[tuple[int, int]],
                                     progress_cb=None) -> list[int]:
    """扫描私有堆，找出所有 8 字节对齐且 *(uint64)==target 的地址。"""
    out: list[int] = []
    total = sum(s for _, s in regions)
    scanned = 0
    for base, size in regions:
        for off in range(0, size, CHUNK):
            chunk_sz = min(CHUNK + 8, size - off)
            data = _read_bytes(h, base + off, chunk_sz)
            if not data or len(data) < 8:
                continue
            lim = len(data) - 7
            for i in range(0, lim, 8):
                try:
                    v = struct.unpack_from('<Q', data, i)[0]
                except Exception:
                    continue
                if v == target:
                    out.append(base + off + i)
            if len(out) > 200_000:
                break
        scanned += size
        if progress_cb:
            progress_cb(scanned / max(total, 1) * 100, len(out))
        if len(out) > 200_000:
            break
    return out


def reverse_pointer_chain(
    handle: int,
    module_base: int,
    module_size: int,
    target_z_addr: int,
    max_depth: int = 8,
    progress_cb=None,
) -> list[int] | None:
    """
    返回 offsets 列表，满足 d4reader.resolve_pointer_chain(handle, module_base, offsets)==target_z_addr。
    仅使用中间偏移 0（read(ptr)+0）。
    """
    regions = _get_private_regions(handle)
    cur     = target_z_addr

    for depth in range(max_depth):
        parents = find_addresses_with_qword_value(handle, cur, regions, progress_cb)
        if not parents:
            return None

        in_module = [p for p in parents if module_base <= p < module_base + module_size]
        if in_module:
            static = in_module[0] - module_base
            # depth=0 → [static,0] 一次 read；depth=1 → [static,0,0] 两次 read …
            return [static] + [0] * (depth + 1)

        parents.sort()
        cur = parents[0]

    return None


def get_module_base_size(pid: int, name: str = "Diablo IV.exe") -> tuple[int, int]:
    class ME(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.wintypes.DWORD),
            ("th32ModuleID", ctypes.wintypes.DWORD),
            ("th32ProcessID", ctypes.wintypes.DWORD),
            ("GlblcntUsage", ctypes.wintypes.DWORD),
            ("ProccntUsage", ctypes.wintypes.DWORD),
            ("modBaseAddr", ctypes.c_ulonglong),
            ("modBaseSize", ctypes.wintypes.DWORD),
            ("hModule", ctypes.wintypes.HMODULE),
            ("szModule", ctypes.c_char * 256),
            ("szExePath", ctypes.c_char * 260),
        ]
    snap = kernel32.CreateToolhelp32Snapshot(0x8 | 0x10, pid)
    if snap == ctypes.wintypes.HANDLE(-1).value:
        return 0, 0
    e = ME()
    e.dwSize = ctypes.sizeof(e)
    if kernel32.Module32First(snap, ctypes.byref(e)):
        while True:
            if name.lower() in e.szModule.decode('utf-8', errors='ignore').lower():
                kernel32.CloseHandle(snap)
                return e.modBaseAddr, e.modBaseSize
            if not kernel32.Module32Next(snap, ctypes.byref(e)):
                break
    kernel32.CloseHandle(snap)
    return 0, 0
