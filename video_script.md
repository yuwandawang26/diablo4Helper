# 视频文案

## 标题
暗黑破坏神4 自动刷罗盘演示 基于Python

## 描述
本视频仅用于学习交流目的，没有任何商业利益往来。

这是一个基于Python开发的暗黑破坏神4全自动刷罗盘工具演示。工具使用OpenCV图像识别和EasyOCR文字识别技术，实现从城镇开始的全自动流程：自动激活罗盘、传送到副本、进入副本、战斗、拾取（30秒）、回城，循环往复。

**代码仓库：**
https://github.com/bean4896/diablo4compassfarm

**主要功能：**
- 全自动流程：从城镇开始，自动激活罗盘、传送到副本、进入副本、战斗、拾取（30秒）、回城，循环往复
- 智能状态同步：启动时自动识别当前游戏状态，实现断点续刷
- 精准导航：利用小地图图标进行亚像素级精准定位
- 事件识别与选择：自动识别并优先选择混沌供品事件
- 精准拾取：使用OpenCV模板匹配识别恢复卷轴和太古装备

**技术栈：**
- Python
- OpenCV（图像处理与模板匹配）
- EasyOCR（文字识别）
- PyAutoGUI（自动化控制）

**免责声明：**
本工具仅供学习交流使用，请勿用于商业用途。使用自动化脚本可能违反游戏服务协议，由此产生的风险由使用者自行承担。

---

# Video Script

## Title
Diablo 4 Auto Compass Farm Demo - Python Based

## Description
This video is for educational purposes only, with no commercial interests involved.

This is a demonstration of a fully automated Diablo 4 Compass Farm tool developed in Python. The tool uses OpenCV for image recognition and EasyOCR for text recognition to achieve a fully automated workflow: automatically activate compass, teleport to dungeon, enter dungeon, combat, loot (30 seconds), return to town, and repeat.

**Code Repository:**
https://github.com/bean4896/diablo4compassfarm

**Main Features:**
- Fully automated workflow: from town, automatically activate compass, teleport to dungeon, enter dungeon, combat, loot (30 seconds), return to town, and repeat
- Smart state synchronization: automatically detects current game state on startup for resume farming
- Precise navigation: uses minimap icons for sub-pixel level positioning
- Event recognition and selection: automatically recognizes and prioritizes Hellborne Offerings events
- Precise looting: uses OpenCV template matching to identify recovery scrolls and Primal Ancient gear

**Tech Stack:**
- Python
- OpenCV (Image processing and template matching)
- EasyOCR (Text recognition)
- PyAutoGUI (Automation control)

**Disclaimer:**
This tool is for educational purposes only. Do not use for commercial purposes. Using automation scripts may violate game service agreements, and users bear all risks.
