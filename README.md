# Diablo 4 罗盘全自动刷本工具 / Diablo 4 Compass Farm Bot

这是一个基于图像识别和 OCR 的暗黑破坏神 4 (Diablo 4) 罗盘副本全自动刷本工具。

This is a fully automated Diablo 4 Compass Farm tool based on image recognition and OCR technology.

---

## 主要功能 / Main Features

*   **全自动流程 / Fully Automated Workflow**：从城镇开始，自动激活罗盘、传送到副本、进入副本、战斗、拾取（30秒）、回城，循环往复。
  
  From town, automatically activate compass, teleport to dungeon, enter dungeon, combat, loot (30 seconds), return to town, and repeat.

*   **智能状态同步 / Smart State Synchronization**：启动时自动识别当前游戏状态（城镇、波次中、首领房、宝箱房），实现断点续刷。
  
  Automatically detects current game state (town, wave in progress, boss room, chest room) on startup for resume farming.

*   **精准导航 / Precise Navigation**：利用小地图图标（事件图标、血井图标、首领入口等）进行亚像素级的精准定位。
  
  Uses minimap icons (event icons, health well icons, boss entrance, etc.) for sub-pixel level precise positioning.

*   **事件识别与选择 / Event Recognition and Selection**：自动识别波次间的"混沌供品"等事件，优先使用OpenCV模板匹配检测混沌事件，确保准确识别。
  
  Automatically recognizes events like "Hellborne Offerings" between waves, prioritizing OpenCV template matching for accurate detection.

*   **首领选择逻辑 / Boss Selection Logic**：根据当前以太数量自动选择收益最高的首领入口（如以太 > 1066 自动选择巴图克）。
  
  Automatically selects the most profitable boss entrance based on current Aether count (e.g., selects Barthuk when Aether > 1066).

*   **精准开箱与拾取 / Precise Chest Opening and Looting**：
    *   使用模板匹配锁定宝箱位置 / Uses template matching to lock chest position
    *   **F 键交互 / F Key Interaction**：使用强制交互键 (F) 打开宝箱，避免攻击动作干扰 / Uses force interaction key (F) to open chest, avoiding attack interference
    *   **智能拾取 / Smart Looting**：使用OpenCV模板匹配识别恢复卷轴和太古装备，鼠标左键点击拾取 / Uses OpenCV template matching to identify recovery scrolls and Primal Ancient gear, left-click to loot
    *   **持续Alt显示 / Continuous Alt Display**：拾取过程中持续按Alt键显示物品名称，提高识别准确率 / Continuously presses Alt key during looting to display item names, improving recognition accuracy

## 技术栈 / Tech Stack

*   **图像处理 / Image Processing**：OpenCV (模板匹配) / OpenCV (Template Matching)
*   **文字识别 / Text Recognition**：EasyOCR (波次识别、以太计数、事件文字) / EasyOCR (Wave recognition, Aether counting, event text)
*   **自动化控制 / Automation Control**：PyAutoGUI (鼠标移动、点击)、Keyboard (键盘按键模拟) / PyAutoGUI (Mouse movement, clicking), Keyboard (Keyboard key simulation)
*   **逻辑控制 / Logic Control**：基于状态机的 Python 脚本 / State machine-based Python script

## 文件结构 / File Structure

*   `main.py`: 程序入口 / Program entry point
*   `core/agent.py`: 核心状态机逻辑 / Core state machine logic
*   `core/vision.py`: 视觉识别系统（OCR、截图、模板匹配）/ Vision recognition system (OCR, screenshot, template matching)
*   `core/navigation.py`: 导航与操作执行（移动、技能、拾取）/ Navigation and operation execution (movement, skills, looting)
*   `config.py`: 全局配置（ROI 区域、资产路径、优先级列表等）/ Global configuration (ROI regions, asset paths, priority lists, etc.)
*   `verify_*.py`: 各个环节的独立测试与视觉化调试脚本 / Independent testing and visualization debug scripts for each stage

## 使用说明 / Usage Instructions

1.  确保游戏分辨率为 2560x1440（或根据 `config.py` 调整 ROI）/ Ensure game resolution is 2560x1440 (or adjust ROI in `config.py`)
2.  安装依赖 / Install dependencies：`pip install -r requirements.txt`
3.  运行 / Run：`python main.py`
4.  脚本运行期间请勿手动操作鼠标键盘，如需紧急停止请按 `Ctrl+C` 或移动鼠标至屏幕角落（PyAutoGUI 安全保护）/ Do not manually operate mouse or keyboard during script execution. Press `Ctrl+C` or move mouse to screen corner for emergency stop (PyAutoGUI safety protection)

## 代码仓库 / Code Repository

https://github.com/bean4896/diablo4compassfarm

## 免责声明 / Disclaimer

**中文 / Chinese：**

本工具仅供学习交流使用，请勿用于商业用途。使用自动化脚本可能违反游戏服务协议，由此产生的风险由使用者自行承担。

**English：**

This tool is for educational purposes only. Do not use for commercial purposes. Using automation scripts may violate game service agreements, and users bear all risks.
