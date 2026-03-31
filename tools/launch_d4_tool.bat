@echo off
:: D4 坐标统一工具（扫描 + 验证 + 指针链 + 实时 XYZ）
:: 已合并 mem_scanner_ui / live_xyz / coord_wizard 能力，推荐只使用本入口
cd /d "%~dp0"
PowerShell -NoProfile -Command "Start-Process python -ArgumentList '\"%~dp0d4_coord_tool.py\"' -Verb RunAs -WorkingDirectory '%~dp0'"
