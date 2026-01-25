from enum import Enum, auto

class GameState(Enum):
    IDLE = auto()                   # 初始/空闲状态
    NAVIGATING_TO_CENTER = auto()   # 准备波次：回到地图中心
    SCANNING_FOR_EVENTS = auto()    # 识别事件：寻找屏幕上的选项
    SELECTING_EVENT = auto()        # 选择事件：点击最佳选项
    WAITING_FOR_WAVE_START = auto() # 等待确认：检测UI波次变化
    COMBAT = auto()                 # 战斗中：60秒循环
    LOOTING = auto()                # 拾取：战斗间隙或结束后的拾取
    NAVIGATING_TO_BOSS = auto()     # 前往Boss房区域
    SELECTING_BOSS_ENTRY = auto()   # 选择进入Boss房的选项
    NAVIGATING_TO_BOSS_DOOR = auto()# 寻找并前往实际的门图标
    INTERACTING_WITH_BOSS_DOOR = auto()  # 在Boss门处，检测并点击交互
    BOSS_FIGHT = auto()             # Boss战
    NAVIGATING_TO_CHEST = auto()    # 寻找并前往宝箱（通过参照物）
    INTERACTING_WITH_CHEST = auto() # 交互并开启宝箱
    ACTIVATING_NEXT_COMPASS = auto() # 开启下一个罗盘
    TELEPORTING_TO_INSTANCE = auto() # 传送至副本
    ENTERING_INSTANCE = auto()      # 进入副本并前往中心
    FINISHED = auto()               # 脚本结束
