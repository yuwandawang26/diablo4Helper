#!/usr/bin/env python3
"""
D4 实时坐标监控器 v1.0
使用指针链配置文件，实时监控并输出玩家世界坐标

使用前提：
  已通过 mem_scanner.py + pointer_scan.py 找到有效的指针链
  并将偏移写入 d4_offsets.json（首次运行会生成模板）

用法：
  python coord_monitor.py
"""

import ctypes
import ctypes.wintypes
import struct
import json
import sys
import time
import math
import subprocess
from pathlib import Path

kernel32 = ctypes.windll.kernel32
PROCESS_VM_READ           = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

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

def read_float(handle: int, address: int) -> float | None:
    data = read_bytes(handle, address, 4)
    if not data or len(data) < 4:
        return None
    v = struct.unpack('<f', data)[0]
    return None if math.isnan(v) or math.isinf(v) else v

def read_pointer(handle: int, address: int) -> int | None:
    data = read_bytes(handle, address, 8)
    if not data or len(data) < 8:
        return None
    val = struct.unpack('<Q', data)[0]
    return val if 0x10000 < val < 0x00007FFFFFFFFFFF else None

# ─── 模块基址 ─────────────────────────────────────────────────────────────────

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

def get_module_base(pid: int, module_name: str = "Diablo IV.exe") -> int:
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000008 | 0x00000010, pid)
    if snapshot == ctypes.wintypes.HANDLE(-1).value:
        return 0
    entry = MODULEENTRY32()
    entry.dwSize = ctypes.sizeof(entry)
    if kernel32.Module32First(snapshot, ctypes.byref(entry)):
        while True:
            name = entry.szModule.decode('utf-8', errors='ignore')
            if module_name.lower() in name.lower():
                kernel32.CloseHandle(snapshot)
                return entry.modBaseAddr
            if not kernel32.Module32Next(snapshot, ctypes.byref(entry)):
                break
    kernel32.CloseHandle(snapshot)
    return 0

# ─── 指针链解析 ───────────────────────────────────────────────────────────────

def resolve_chain(handle: int, module_base: int,
                  static_offset: int, pointer_offsets: list[int]) -> int | None:
    """
    解析指针链：
      module_base + static_offset -> ptr1
      ptr1 + pointer_offsets[0]   -> ptr2
      ...
      ptrN + pointer_offsets[-1]  = 最终坐标地址
    """
    addr = module_base + static_offset
    for off in pointer_offsets[:-1]:
        ptr = read_pointer(handle, addr + off)
        if ptr is None:
            return None
        addr = ptr
    return addr + pointer_offsets[-1]

# ─── 配置文件 ─────────────────────────────────────────────────────────────────

OFFSET_FILE = Path(__file__).parent / "d4_offsets.json"

DEFAULT_CONFIG = {
    "_comment": "将 mem_scanner.py + pointer_scan.py 找到的偏移填入此文件",
    "_usage": "static_offset: 模块静态偏移(int); pointer_offsets: 指针链各层偏移列表",
    "player_x": {
        "static_offset": 0,
        "pointer_offsets": [],
        "description": "玩家 X 坐标（世界空间）"
    },
    "player_y": {
        "static_offset": 0,
        "pointer_offsets": [],
        "description": "玩家 Y 坐标（高度）"
    },
    "player_z": {
        "static_offset": 0,
        "pointer_offsets": [],
        "description": "玩家 Z 坐标（世界空间，第二水平轴）"
    },
    "calibration": {
        "world_origin_x": 0.0,
        "world_origin_z": 0.0,
        "minimap_center_px": 960,
        "minimap_center_py": 540,
        "scale": 1.0,
        "_comment": "world→pixel: px = (wx - origin_x) * scale + center_px"
    }
}

def load_config() -> dict:
    if not OFFSET_FILE.exists():
        OFFSET_FILE.write_text(
            json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False)
        )
        print(f"[创建] 配置模板 → {OFFSET_FILE}")
        print("  请先用 mem_scanner.py 和 pointer_scan.py 找到偏移，")
        print("  然后填入 d4_offsets.json 中的 static_offset 和 pointer_offsets 字段")
        sys.exit(0)
    return json.loads(OFFSET_FILE.read_text(encoding='utf-8'))

# ─── 坐标转换 ─────────────────────────────────────────────────────────────────

def world_to_minimap(wx: float, wz: float, cal: dict) -> tuple[int, int]:
    """世界坐标 → 小地图像素坐标"""
    scale = cal.get('scale', 1.0)
    ox    = cal.get('world_origin_x', 0.0)
    oz    = cal.get('world_origin_z', 0.0)
    cx    = cal.get('minimap_center_px', 960)
    cy    = cal.get('minimap_center_py', 540)
    px = int((wx - ox) * scale + cx)
    py = int((wz - oz) * scale + cy)
    return px, py

# ─── 主监控循环 ───────────────────────────────────────────────────────────────

class D4Coords:
    """
    对外暴露的坐标读取接口，供其他模块 import 使用：

        from tools.coord_monitor import D4Coords
        reader = D4Coords()
        x, y, z = reader.get_world_coords()
        px, py = reader.get_minimap_pixel()
    """

    def __init__(self):
        self.pid = get_pid("Diablo IV.exe")
        if not self.pid:
            raise RuntimeError("未找到 Diablo IV.exe，请先启动游戏")
        self.handle = open_process(self.pid)
        self.module_base = get_module_base(self.pid)
        if not self.module_base:
            raise RuntimeError("无法获取 Diablo IV.exe 模块基址")
        self.config = load_config()
        self._build_chains()

    def _build_chains(self):
        def parse(key: str):
            cfg = self.config.get(key, {})
            return cfg.get('static_offset', 0), cfg.get('pointer_offsets', [])
        self._x_static, self._x_offsets = parse('player_x')
        self._y_static, self._y_offsets = parse('player_y')
        self._z_static, self._z_offsets = parse('player_z')

    def _read_coord(self, static_off: int, offsets: list[int]) -> float | None:
        if not offsets:
            return None
        addr = resolve_chain(self.handle, self.module_base, static_off, offsets)
        return read_float(self.handle, addr) if addr else None

    def get_world_coords(self) -> tuple[float | None, float | None, float | None]:
        x = self._read_coord(self._x_static, self._x_offsets)
        y = self._read_coord(self._y_static, self._y_offsets)
        z = self._read_coord(self._z_static, self._z_offsets)
        return x, y, z

    def get_minimap_pixel(self) -> tuple[int, int] | None:
        x, _, z = self.get_world_coords()
        if x is None or z is None:
            return None
        cal = self.config.get('calibration', {})
        return world_to_minimap(x, z, cal)

    def close(self):
        kernel32.CloseHandle(self.handle)


def main():
    print("""
╔══════════════════════════════════════════════════════╗
║       D4 实时坐标监控器  (需管理员权限运行)          ║
╚══════════════════════════════════════════════════════╝
""")
    try:
        reader = D4Coords()
    except (RuntimeError, PermissionError) as e:
        print(f"[错误] {e}")
        input("按回车退出...")
        sys.exit(1)

    cfg = reader.config
    print(f"[OK] 模块基址: 0x{reader.module_base:016X}")

    x_cfg = cfg.get('player_x', {})
    if not x_cfg.get('pointer_offsets'):
        print("\n[警告] d4_offsets.json 中尚未填写偏移量！")
        print("  请先运行 mem_scanner.py → pointer_scan.py → 将结果填入 d4_offsets.json")
        print("\n  当前仅演示：直接读取上次扫描状态的第一个候选地址")
        state_file = Path(__file__).parent / "d4_scan_state.json"
        if state_file.exists():
            state = json.loads(state_file.read_text())
            addrs = [int(k) for k in state.keys()]
            if addrs:
                addr = addrs[0]
                print(f"  尝试监控 0x{addr:016X}...")
                print(f"  {'X':>12s}  {'Y':>12s}  {'Z':>12s}")
                try:
                    handle = reader.handle
                    while True:
                        data_bytes = read_bytes(handle, addr, 12)
                        if data_bytes and len(data_bytes) == 12:
                            x, y, z = struct.unpack('<fff', data_bytes)
                            print(f"\r  {x:12.4f}  {y:12.4f}  {z:12.4f}", end='', flush=True)
                        time.sleep(0.1)
                except KeyboardInterrupt:
                    print("\n已停止")
        reader.close()
        return

    print(f"\n  实时监控玩家坐标 (Ctrl+C 停止)\n")
    print(f"  {'X(世界)':>12s}  {'Y(高度)':>12s}  {'Z(世界)':>12s}  {'小地图PX':>10s}  {'小地图PY':>10s}")
    print(f"  {'-'*65}")
    try:
        while True:
            x, y, z = reader.get_world_coords()
            pix = reader.get_minimap_pixel()
            xs = f"{x:.3f}" if x is not None else "N/A"
            ys = f"{y:.3f}" if y is not None else "N/A"
            zs = f"{z:.3f}" if z is not None else "N/A"
            pxs = str(pix[0]) if pix else "N/A"
            pys = str(pix[1]) if pix else "N/A"
            print(f"\r  {xs:>12s}  {ys:>12s}  {zs:>12s}  {pxs:>10s}  {pys:>10s}", end='', flush=True)
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n  已停止监控")

    reader.close()


if __name__ == "__main__":
    main()
