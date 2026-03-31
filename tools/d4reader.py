#!/usr/bin/env python3
"""
D4 实时坐标读取器 v2.0
读取玩家世界坐标（x, y, z），并转换为小地图像素坐标。

前提：
  d4_offsets.json 中的 current 分区已填写有效偏移。
  运行 aob_scanner.py 可自动填充 classmgr_offset，
  pos_*_from_entity 字段需通过 mem_scanner.py + CE 手动确认后填入。

供 agent.py 调用的接口：
  reader = D4Reader()
  x, y, z = reader.get_world_coords()
  px, py  = reader.get_minimap_pixel()
  reader.close()

或后台线程模式：
  def on_update(x, y, z): ...
  reader.start_background(on_update, hz=10)
  ...
  reader.stop_background()
"""

import ctypes
import ctypes.wintypes
import struct
import json
import sys
import time
import math
import random
import threading
from pathlib import Path

kernel32 = ctypes.windll.kernel32
psapi    = ctypes.windll.psapi

PROCESS_VM_READ           = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

OFFSETS_FILE = Path(__file__).parent / "d4_offsets.json"

# ─── 基础读取 ─────────────────────────────────────────────────────────────────

def _read_bytes(handle: int, addr: int, size: int) -> bytes | None:
    buf = ctypes.create_string_buffer(size)
    n   = ctypes.c_size_t(0)
    ok  = kernel32.ReadProcessMemory(handle, ctypes.c_void_p(addr), buf, size, ctypes.byref(n))
    return buf.raw[:n.value] if (ok and n.value > 0) else None

def _read_float(handle: int, addr: int) -> float | None:
    d = _read_bytes(handle, addr, 4)
    if not d or len(d) < 4:
        return None
    v = struct.unpack('<f', d)[0]
    return None if (math.isnan(v) or math.isinf(v)) else v

def _read_pointer(handle: int, addr: int) -> int | None:
    d = _read_bytes(handle, addr, 8)
    if not d or len(d) < 8:
        return None
    v = struct.unpack('<Q', d)[0]
    return v if 0x10000 < v < 0x7FFFFFFFFFFF else None


def resolve_pointer_chain(handle: int, module_base: int, offsets: list[int]) -> int | None:
    """
    解析 Cheat Engine 风格指针链（与 CE「指针扫描」导出一致）：

      ptr = module_base + offsets[0]
      对 offsets[1:] 中每一个 off：
          ptr = read_u64(ptr) + off

    若某次 read 失败则返回 None。
    """
    if not offsets:
        return None
    ptr = module_base + int(offsets[0])
    for off in offsets[1:]:
        p = _read_pointer(handle, ptr)
        if p is None:
            return None
        ptr = p + int(off)
    return ptr


def _parse_hex_int(v) -> int | None:
    if v is None:
        return None
    if isinstance(v, int):
        return v
    s = str(v).strip()
    if s.startswith("0x") or s.startswith("0X"):
        return int(s, 16)
    return int(s, 0)

# ─── 进程/模块工具 ────────────────────────────────────────────────────────────

MAX_PROCS = 1024

def _get_pid(name: str = "Diablo IV.exe") -> int | None:
    buf    = (ctypes.wintypes.DWORD * MAX_PROCS)()
    needed = ctypes.wintypes.DWORD(0)
    psapi.EnumProcesses(buf, ctypes.sizeof(buf), ctypes.byref(needed))
    count  = needed.value // ctypes.sizeof(ctypes.wintypes.DWORD)
    nbuf   = ctypes.create_unicode_buffer(260)
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

class _MODULEENTRY(ctypes.Structure):
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

def _get_module_base(pid: int, name: str = "Diablo IV.exe") -> int:
    snap = kernel32.CreateToolhelp32Snapshot(0x00000008 | 0x00000010, pid)
    if snap == ctypes.wintypes.HANDLE(-1).value:
        return 0
    e = _MODULEENTRY()
    e.dwSize = ctypes.sizeof(e)
    if kernel32.Module32First(snap, ctypes.byref(e)):
        while True:
            if name.lower() in e.szModule.decode('utf-8', errors='ignore').lower():
                kernel32.CloseHandle(snap)
                return e.modBaseAddr
            if not kernel32.Module32Next(snap, ctypes.byref(e)):
                break
    kernel32.CloseHandle(snap)
    return 0

# ─── 坐标转换 ─────────────────────────────────────────────────────────────────

def _world_to_minimap(wx: float, wz: float, cal: dict) -> tuple[int, int]:
    scale = cal.get('scale', 1.0)
    ox    = cal.get('origin_x', 0.0)
    oz    = cal.get('origin_z', 0.0)
    cx    = cal.get('minimap_center_px', 960)
    cy    = cal.get('minimap_center_py', 540)
    return int((wx - ox) * scale + cx), int((wz - oz) * scale + cy)

# ─── D4Reader 主类 ────────────────────────────────────────────────────────────

class D4Reader:
    """
    实时读取 Diablo IV 玩家世界坐标。

    三种数据来源（按优先级）：
      1) pointer_chain — Cheat Engine 指针链，重启游戏仍有效（直到版本更新）
      2) current.player_z_addr — 仅当次进程的动态地址，重启后失效
      3) classmgr + entity 偏移 — 需完整逆向偏移
    """

    def __init__(self, offsets_file: Path = OFFSETS_FILE):
        self._lock   = threading.Lock()
        self._thread = None
        self._running = False
        self._last_coords: tuple[float, float, float] | None = None

        cfg = json.loads(offsets_file.read_text(encoding='utf-8')) if offsets_file.exists() else {}
        cur = cfg.get('current', {})
        cal = cfg.get('calibration', {})
        pc  = cfg.get('pointer_chain') or {}

        self._calibration = cal
        self._classmgr_offset       = cur.get('classmgr_offset')
        self._ractors_from_classmgr = cur.get('ractors_from_classmgr')
        self._pos_x_off             = cur.get('pos_x_from_entity')
        self._pos_y_off             = cur.get('pos_y_from_entity')
        self._pos_z_off             = cur.get('pos_z_from_entity')

        # ── 模式：chain | dynamic | classmgr ─────────────────────────────────
        self._mode = None
        self._chain_module: str = pc.get('module', 'Diablo IV.exe')
        self._chain_offsets: list[int] = []
        self._dz_x = -4
        self._dz_y = 4
        self._dz_z = 0

        offs = pc.get('offsets')
        if offs and isinstance(offs, list) and len(offs) >= 1:
            self._mode = 'chain'
            self._chain_offsets = [_parse_hex_int(x) for x in offs]
            layout = pc.get('xyz_layout') or {}
            self._dz_x = int(layout.get('bytes_x_from_z', -4))
            self._dz_y = int(layout.get('bytes_y_from_z', 4))
            self._dz_z = int(layout.get('bytes_z_from_z', 0))

        z_dyn = cur.get('player_z_addr') or cur.get('player_coord_addr_dynamic')
        if self._mode is None and z_dyn:
            self._mode = 'dynamic'
            self._dynamic_z = _parse_hex_int(z_dyn)

        if self._mode is None and self._classmgr_offset is not None:
            self._mode = 'classmgr'

        if self._mode is None:
            raise RuntimeError(
                "d4_offsets.json 需至少配置其一：\n"
                "  · pointer_chain（推荐，CE 指针扫描一次即可跨重启）\n"
                "  · current.player_z_addr（仅本次游戏有效）\n"
                "  · classmgr_offset + entity 偏移（完整逆向）\n"
                "详见 tools/README.md「指针链」一节。"
            )

        pid = _get_pid("Diablo IV.exe")
        if not pid:
            raise RuntimeError("未找到 Diablo IV.exe，请先启动游戏")
        self._pid    = pid
        self._handle = kernel32.OpenProcess(
            PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid
        )
        if not self._handle:
            raise PermissionError(f"OpenProcess 失败 (错误码={kernel32.GetLastError()})")
        self._module_base = _get_module_base(pid, self._chain_module if self._mode == 'chain' else 'Diablo IV.exe')
        if not self._module_base:
            raise RuntimeError("无法获取模块基址")

    # ── 内部指针链解析 ────────────────────────────────────────────────────────

    def _resolve_classmgr(self) -> int | None:
        return _read_pointer(self._handle,
                             self._module_base + self._classmgr_offset)

    def _resolve_ractors(self, classmgr: int) -> int | None:
        off = self._ractors_from_classmgr
        if off is None:
            return None
        return _read_pointer(self._handle, classmgr + off)

    def _read_xyz_at_z_base(self, z_addr: int) -> tuple[float, float, float] | None:
        """以 Z 分量为锚：x=z-4, z_mid=z, y=z+4（与扫描器结论一致，可在 pointer_chain.xyz_layout 改）"""
        x = _read_float(self._handle, z_addr + self._dz_x)
        y = _read_float(self._handle, z_addr + self._dz_y)
        z = _read_float(self._handle, z_addr + self._dz_z)
        if None in (x, y, z):
            return None
        return (x, y, z)

    def _resolve_coords_raw(self) -> tuple[float, float, float] | None:
        if self._mode == 'chain':
            z_addr = resolve_pointer_chain(self._handle, self._module_base, self._chain_offsets)
            if z_addr is None:
                return None
            return self._read_xyz_at_z_base(z_addr)

        if self._mode == 'dynamic':
            return self._read_xyz_at_z_base(self._dynamic_z)

        if self._mode == 'classmgr':
            if None in (self._pos_x_off, self._pos_y_off, self._pos_z_off):
                return None
            return None  # TODO: entity 遍历未实现

        return None

    # ── 公开接口 ──────────────────────────────────────────────────────────────

    def get_world_coords(self) -> tuple[float, float, float] | None:
        """读取玩家世界坐标 (x, y, z)。返回 None 表示链路失效。"""
        with self._lock:
            try:
                coords = self._resolve_coords_raw()
                if coords:
                    self._last_coords = coords
                return coords
            except Exception:
                return None

    def get_minimap_pixel(self) -> tuple[int, int] | None:
        """将世界坐标转换为小地图像素坐标。"""
        coords = self.get_world_coords() or self._last_coords
        if not coords:
            return None
        x, _, z = coords
        return _world_to_minimap(x, z, self._calibration)

    def debug_chain(self) -> dict:
        """调试用：当前解析模式与关键地址"""
        result: dict = {'mode': self._mode, 'module_base': hex(self._module_base)}
        try:
            if self._mode == 'chain':
                result['pointer_offsets'] = [hex(o) for o in self._chain_offsets]
                z_addr = resolve_pointer_chain(self._handle, self._module_base, self._chain_offsets)
                result['resolved_z_addr'] = hex(z_addr) if z_addr else None
            elif self._mode == 'dynamic':
                result['dynamic_z_addr'] = hex(self._dynamic_z)
            elif self._mode == 'classmgr' and self._classmgr_offset is not None:
                base = self._module_base
                cm_off = self._classmgr_offset
                result['classmgr_static'] = hex(base + cm_off)
                classmgr = _read_pointer(self._handle, base + cm_off)
                result['classmgr_ptr'] = hex(classmgr) if classmgr else None
                if classmgr and self._ractors_from_classmgr:
                    ractors = _read_pointer(self._handle, classmgr + self._ractors_from_classmgr)
                    result['ractors_ptr'] = hex(ractors) if ractors else None
        except Exception as e:
            result['error'] = str(e)
        return result

    def start_background(self, callback, hz: float = 10):
        """
        启动后台线程，以约 hz 的频率调用 callback(x, y, z)。
        callback 中不应有耗时操作。
        """
        if self._thread and self._thread.is_alive():
            return
        self._running = True

        def _loop():
            interval = 1.0 / hz
            while self._running:
                coords = self.get_world_coords()
                if coords:
                    try:
                        callback(*coords)
                    except Exception:
                        pass
                time.sleep(interval + random.uniform(-0.02, 0.02))

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop_background(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def close(self):
        self.stop_background()
        if self._handle:
            kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# ─── 独立运行模式（调试用）────────────────────────────────────────────────────

def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║  D4 坐标读取器 v2.0  调试模式                                ║
╚══════════════════════════════════════════════════════════════╝
""")
    try:
        reader = D4Reader()
    except (RuntimeError, PermissionError) as e:
        print(f"[错误] {e}")
        input("按回车退出...")
        sys.exit(1)

    print(f"[OK] 模块基址: 0x{reader._module_base:016X}")
    print(f"[OK] 模式: {reader._mode}\n")

    chain = reader.debug_chain()
    print("  调试信息：")
    for k, v in chain.items():
        print(f"    {k:30s} = {v}")

    if reader._mode == 'classmgr' and None in (reader._pos_x_off, reader._pos_y_off, reader._pos_z_off):
        print("""
  ⚠ classmgr 模式需配置 pos_*_from_entity，或使用 pointer_chain / 动态地址。
""")
    else:
        print("\n  实时监控坐标（Ctrl+C 停止）\n")
        print(f"  {'X':>12s}  {'Y(高)':>12s}  {'Z':>12s}  {'小地图PX':>8s}  {'小地图PY':>8s}")
        print(f"  {'-'*60}")
        try:
            while True:
                coords = reader.get_world_coords()
                pix    = reader.get_minimap_pixel()
                if coords:
                    x, y, z = coords
                    px, py  = pix if pix else ('N/A', 'N/A')
                    print(f"\r  {x:12.4f}  {y:12.4f}  {z:12.4f}  {str(px):>8s}  {str(py):>8s}",
                          end='', flush=True)
                else:
                    print(f"\r  [读取失败或链失效]", end='', flush=True)
                time.sleep(random.uniform(0.08, 0.15))
        except KeyboardInterrupt:
            print("\n  已停止")

    reader.close()


if __name__ == "__main__":
    main()
