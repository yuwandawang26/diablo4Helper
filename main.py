"""Entry point — launches the PyQt5 GUI control panel."""

import sys
import os

# Ensure the project root is on the path when running from any directory
sys.path.insert(0, os.path.dirname(__file__))

# ── Critical: pre-load heavy native libs BEFORE Qt touches any DLLs ──────────
# On Windows, Qt loads its own C++ runtime DLLs on QApplication creation.
# If torch/cv2 are first imported inside a QThread *after* Qt has already
# initialised, Windows refuses to re-initialise conflicting DLL sections
# (WinError 1114 / ERROR_DLL_INIT_FAILED).
# Importing them here — before QApplication — lets them win the load order.
def _preload_native_deps():
    try:
        import cv2          # noqa: F401
    except Exception:
        pass
    try:
        import torch        # noqa: F401
    except Exception:
        pass
    # easyocr is heavy; skip here — it will be imported on bot start inside
    # the thread, but cv2+torch DLLs are already resident by then so it works.

_preload_native_deps()
# ─────────────────────────────────────────────────────────────────────────────

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from ui.main_window import MainWindow


def main():
    # High-DPI support
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("D4 Auto")
    app.setApplicationDisplayName("D4 Auto — 暗黑破坏神4 自动脚本")

    # Default font (supports Chinese)
    font = QFont("Microsoft YaHei UI", 10)
    font.setHintingPreference(QFont.PreferFullHinting)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
