@echo off
:: 已合并到 d4_coord_tool.py（见 launch_d4_tool.bat）
cd /d "%~dp0"
PowerShell -NoProfile -Command "Start-Process python -ArgumentList '\"%~dp0d4_coord_tool.py\"' -Verb RunAs -WorkingDirectory '%~dp0'"
