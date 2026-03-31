# D4 内存工具套件

> 目标：以**只读**方式获取 Diablo IV 玩家实时世界坐标，供自动化助手（agent.py）使用。

---

## 推荐入口（唯一 GUI）

| 文件 | 说明 |
|------|------|
| **`d4_coord_tool.py`** | **统一坐标工具**：① 全局扫描 ② 自动移动验证 ③ 自动指针链 ④ 顶部**实时大字 XYZ**（配置写入 `d4_offsets.json` 后自动刷新） |
| **`launch_d4_tool.bat`** | 以管理员身份启动上述工具（**首选**，双击即可） |

`launch_scanner.bat`、`launch_coord_wizard.bat` 已改为启动同一程序；底层仍复用 `mem_scanner_ui.py`、`live_xyz.py`、`coord_wizard.py` 中的逻辑，无需再记多个入口。

---

## 工具一览

| 文件 | 用途 | 运行时机 |
|------|------|----------|
| `mem_scanner.py` | 内存坐标扫描，找到动态坐标地址 | 新设备首次、游戏更新后 |
| `aob_scanner.py` | AOB特征码扫描，自动找 ClassMGR 偏移 | 游戏更新后 |
| `d4reader.py` | 实时读取坐标，供 agent.py 调用 | 运行中随时 |
| `d4_offsets.json` | 偏移配置文件（由工具自动写入） | 无需手动编辑 |
| `coord_wizard.py` | 旧版一键向导（逻辑已并入 `d4_coord_tool.py`） | 可仍单独运行 |
| `launch_coord_wizard.bat` | 已跳转至统一工具 | 与 `launch_d4_tool.bat` 等价 |

---

## 第一步：找到玩家坐标的动态地址（用 `mem_scanner.py`）

这是整个流程的起点，使用方法类似 Cheat Engine 的"未知初始值"扫描。

### 运行方式

```powershell
# 以管理员身份打开 PowerShell
cd d:\D4-Auto\diablo4Helper\tools
python mem_scanner.py
```

### 操作流程

```
游戏内让角色站立不动
    ↓
mem_scanner → 选1（快照扫描）  ← 约需 1-3 分钟，记录所有浮点值
    ↓
游戏内随意移动角色
    ↓
mem_scanner → 选2（筛选变化的值）
    ↓
重复：往右走 → 选3 → 往左走 → 选4 → 原地站 2 秒 → 选5
    ↓
候选 < 20 个时
    ↓
选6 查看候选列表，找连续排列的三个相近浮点（XYZ三元组）
    ↓
选7 输入地址实时监控，移动时数值应同步变化
    ↓
记录该地址（动态地址，每次启动游戏会变化）
```

### 示例输出（选7）

```
  监控 0x0000020A1B2C3D40  (Ctrl+C 停止)

       X/val0       Y/val1       Z/val2   周围16字节(hex)
     1234.5678   -456.1234    789.0000   ...
```

---

## 第二步：用 Cheat Engine 建立稳定的指针链

动态地址每次启动都变，所以需要找到从 `Diablo IV.exe` 基址出发的稳定指针链。

### Cheat Engine 操作步骤

1. 打开 Cheat Engine，附加 `Diablo IV.exe`
2. 在地址栏输入第一步找到的坐标地址（如 `0x020A1B2C3D40`）
3. 右键该条目 → **Pointer scan for this address**
4. 设置：
   - Max level: 6
   - Max offset: 2048（0x800）
   - 勾选 "Only find paths with static address"
5. 点 OK，等待扫描完成（约 1-5 分钟）
6. 扫描结果窗口中，找以 `Diablo IV.exe` 开头的记录
7. 重启游戏，用"重新扫描指针"验证哪条链路仍然指向正确地址
8. 稳定的链路格式如：`Diablo IV.exe + 0x2ABEC18 → +A18 → ... → +偏移 = 坐标`

记录以下信息，后面要用：
- `Diablo IV.exe + 0xXXXXXXX`（classmgr 偏移）
- 每一级的偏移（ractors、actor、entity 各层）
- 最后一级的偏移（pos_x_from_entity，Y和Z同理）

### 写入 `d4_offsets.json` 的 `pointer_chain`（推荐，免每次全量扫描）

CE 指针链解析规则与脚本一致：**第一项** = 相对 `Diablo IV.exe` 的静态偏移；**之后每一项**：先按 8 字节读指针，再加上下一项偏移（与 CE 扫描结果顺序相同）。

若链最终指向 **Z 分量**的 float 地址（与 `live_xyz` 自动测试一致），保持默认 `xyz_layout` 即可：X 在 Z−4，Y（高度）在 Z+4。

```json
"pointer_chain": {
  "module": "Diablo IV.exe",
  "offsets": ["0x1234567", "0xA18", "0x80", "0x40"],
  "xyz_layout": {
    "bytes_x_from_z": -4,
    "bytes_y_from_z": 4,
    "bytes_z_from_z": 0
  }
}
```

填好后运行 `python d4reader.py` 验证；**重启游戏后无需再扫内存**，除非游戏大版本更新导致链断裂。

---

## 第三步：用 x64dbg 找 AOB 特征码（用于游戏更新后自动更新）

> **此步骤可选，但强烈推荐。** 这样游戏更新后只需重跑 `aob_scanner.py` 即可。

### x64dbg 操作步骤

1. 以**管理员身份**运行 x64dbg
2. 文件 → 附加 → 选 `Diablo IV.exe`（不要选"打开"）
3. 游戏会暂停，按 F9 恢复运行
4. 在 CPU 面板（上方），按 `Ctrl+G`，输入地址：
   ```
   Diablo IV.exe + 0xXXXXXXX
   ```
   （用 CE 找到的 classmgr 偏移）
5. 看到该地址附近的汇编代码，找到**读取 classmgr**的那行指令：
   - 通常是：`mov rax, [rip+XXXXXXXX]`  对应字节：`48 8B 05 XX XX XX XX`
   - 或者：`mov rcx, [rip+XXXXXXXX]`  对应字节：`48 8B 0D XX XX XX XX`
6. 右键该行 → **Binary** → **Copy** → 复制10字节左右
7. 将 `XX XX XX XX`（4字节偏移）替换为 `?? ?? ?? ??`（通配符）
8. 在 `aob_scanner.py` 的 `PATTERNS` 列表中添加记录，设 `enabled: True`

**示例（假设找到的指令字节为 `48 8B 05 18 EC AB 02 48 85 C0`）：**

```python
{
    "label":       "classmgr_your_version",
    "pattern":     [0x48, 0x8B, 0x05, None, None, None, None, 0x48, 0x85, 0xC0],
    "rip_at":      3,
    "instr_len":   7,
    "description": "mov rax, [classmgr]; test rax,rax",
    "enabled":     True,
}
```

---

## 第四步：填写配置文件 `d4_offsets.json`

运行 `aob_scanner.py` 会自动填入 `classmgr_offset` 和 `ractors_from_classmgr`。

剩余的 pos 偏移需手动填入（只需一次，除非游戏更新了 entity 结构）：

```json
{
  "current": {
    "classmgr_offset": 44961816,
    "ractors_from_classmgr": 2584,
    "pos_x_from_entity": 320,
    "pos_y_from_entity": 324,
    "pos_z_from_entity": 328
  }
}
```

> pos 偏移的单位是**字节**（不是十六进制）。可以先写十六进制如 `0x140` 再换算。

---

## 第五步：验证 `d4reader.py`

```powershell
python d4reader.py
```

输出示例：

```
[OK] 模块基址: 0x00007FF6A0000000
[OK] classmgr_offset: 0x2ABEC18

  指针链调试信息：
    module_base               = 0x7ff6a0000000
    classmgr_static           = 0x7ff6a2abec18
    classmgr_ptr              = 0x000002501aaa0000
    ractors_ptr               = 0x000002501f330000

       X(世界)       Y(高度)       Z(世界)  小地图PX  小地图PY
     1234.5678   -456.1234    789.0000      1100       420
```

---

## 供 agent.py 调用

```python
from diablo4Helper.tools.d4reader import D4Reader

# 一次性读取
with D4Reader() as reader:
    coords = reader.get_world_coords()  # (x, y, z) 或 None
    pixel  = reader.get_minimap_pixel() # (px, py) 或 None

# 后台线程持续更新
def on_update(x, y, z):
    print(f"玩家位置: {x:.1f}, {z:.1f}")

reader = D4Reader()
reader.start_background(on_update, hz=10)
# ... 其他逻辑 ...
reader.stop_background()
reader.close()
```

---

## 常见问题

**Q: 运行提示"OpenProcess 失败"**
A: 必须以**管理员身份**运行 PowerShell，游戏必须已启动。

**Q: mem_scanner.py 运行很慢（> 5 分钟）**
A: 正常，私有堆内存通常有 1-3 GB，初次快照需要时间。

**Q: 游戏更新后偏移失效**
A: 重新运行 `aob_scanner.py`（自动修复 classmgr_offset）。
   如果 entity 的 pos 偏移也变了，需重跑 `mem_scanner.py` + CE 指针扫描。

**Q: CE 指针扫描找到很多结果，不知道选哪个**
A: 重启游戏后用 CE "重新扫描指针"功能，只保留重启后仍然指向正确地址的链路。
   最终选择层级最少、且偏移值均在 0x000~0xFFF 范围内的链路。

**Q: aob_scanner.py 提示没有启用的模式**
A: 需要先用 x64dbg 做一次特征码提取（参见第三步）。
   初次设置后，此工具就能完全自动化应对后续版本更新。
