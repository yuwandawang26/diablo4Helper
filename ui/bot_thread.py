"""Bot runner thread — wraps CompassBot in a QThread and exposes signals for UI."""

import sys
import io
from PyQt5.QtCore import QThread, pyqtSignal


class _StdoutCapture(io.TextIOBase):
    """Write proxy that forwards each complete line to a Qt signal."""

    def __init__(self, signal_emit, original):
        super().__init__()
        self._emit = signal_emit
        self._orig = original
        self._buf = ""

    def write(self, text: str):
        self._orig.write(text)
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                self._emit(line)
        return len(text)

    def flush(self):
        self._orig.flush()


class BotThread(QThread):
    # Signal payloads
    log_signal = pyqtSignal(str)                        # one log line
    state_signal = pyqtSignal(str, int, int, int, str)  # (state, compass, wave_curr, wave_max, ether)
    quest_signal = pyqtSignal(str)                      # current quest-tracker text
    run_count_signal = pyqtSignal(int, int)             # (current_run, max_runs)
    finished_signal = pyqtSignal()

    def __init__(self, lang: str = "cn", parent=None):
        super().__init__(parent)
        self.lang = lang
        self.bot = None

    # ── public control ────────────────────────────────────────────────────────

    def stop(self):
        """Request a clean stop of the bot loop."""
        if self.bot:
            self.bot._running = False

    def reload_skills(self):
        """Hot-reload skill config without restarting the bot."""
        if self.bot:
            self.bot.nav.reload_skills()

    # ── thread entry ──────────────────────────────────────────────────────────

    def run(self):
        old_stdout = sys.stdout
        sys.stdout = _StdoutCapture(self.log_signal.emit, old_stdout)
        try:
            # Late import so we don't initialise easyocr on UI startup
            from core.agent import CompassBot

            self.bot = CompassBot(lang=self.lang)
            self.bot._state_callback = self._on_state_change
            self.bot._quest_callback = self.quest_signal.emit
            self.bot._run_count_callback = self.run_count_signal.emit
            self.bot.run()
        except Exception as exc:
            import traceback
            self.log_signal.emit(f"[THREAD ERROR] {exc}")
            self.log_signal.emit(traceback.format_exc())
        finally:
            sys.stdout = old_stdout
            self.bot = None
            self.finished_signal.emit()

    # ── private ───────────────────────────────────────────────────────────────

    def _on_state_change(self, state: str, compass: int, wave_curr: int,
                         wave_max: int, ether):
        ether_str = str(ether) if ether is not None else "?"
        self.state_signal.emit(state, compass, wave_curr, wave_max, ether_str)
