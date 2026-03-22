# open_packet/ui/tui/widgets/console_panel.py
from __future__ import annotations
from collections import deque
from datetime import datetime
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import RichLog, Label, Input
from textual.containers import Vertical


class ConsolePanel(Widget):
    DEFAULT_CSS = """
    ConsolePanel {
        height: 8;
        border-top: solid $primary;
    }
    ConsolePanel Label {
        background: $primary;
        width: 100%;
        padding: 0 1;
        height: 1;
    }
    ConsolePanel RichLog {
        height: 1fr;
    }
    """

    def __init__(self, buffer_size: int = 500, **kwargs):
        super().__init__(**kwargs)
        self._buffer_size = buffer_size
        self._log_file = None
        self._buffer: deque = deque(maxlen=buffer_size)

    def compose(self) -> ComposeResult:
        yield Label("CONSOLE")
        yield RichLog(id="console_log", highlight=False, markup=False)

    def set_log_file(self, path: str) -> None:
        import logging
        from logging.handlers import RotatingFileHandler
        handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=3)
        self._log_file = logging.getLogger("open_packet.console")
        self._log_file.addHandler(handler)
        self._log_file.setLevel(logging.DEBUG)

    def log_frame(self, direction: str, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"{ts} {direction} {text}"
        self._buffer.append(line)
        log_widget = self.query_one("#console_log", RichLog)
        log_widget.write(line)
        if self._log_file:
            self._log_file.debug(line)
