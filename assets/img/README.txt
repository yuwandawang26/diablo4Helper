大地图 / 罗盘相关模板（可选）
================================

可将 `map_compass_entrance.png` 等大图放在此目录，脚本会**优先**在 `templates/` 查找，找不到时再查本目录。

槽位名与 `core/config.py` → `get_template_path` / GUI「模板管理」一致；覆盖路径写在 config.json 的 `vision.template_files`。

常用：
- map_compass_entrance.png — 全屏地图上红色罗盘/魔潮入口图标（匹配 ROI：MAP_COMPASS_SEARCH）

炼狱罗盘战斗寻路（小地图 ROI 内图标，也可用 ROI 编辑器截取到 templates/）：
- 恶魔.png — 槽位 minimap_pit_demon，优先导航目标
- 罗盘大怪物.png — 槽位 minimap_pit_elite，无恶魔时走向最近一个
- 亦可使用 templates/minimap_pit_demon.png、minimap_pit_elite.png

WASD 回中心（需在 config.json 的 bot 里设 minimap_wasd_center_nav: true）：
- minimap_extrahand.png → 槽位 minimap_center_extrahand（优先）
- minimap_bonehand.png → 槽位 minimap_center_bonehand
  可从 diablo4compassfarm 的 assets 复制同名小图到本目录。
