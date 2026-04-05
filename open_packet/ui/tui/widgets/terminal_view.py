# open_packet/ui/tui/widgets/terminal_view.py
from __future__ import annotations
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message as TMessage
from textual.widgets import Input, Label, RichLog


class TerminalView(Vertical):
    DEFAULT_CSS = """
    TerminalView {
        height: 1fr;
    }
    TerminalView #terminal_header {
        height: 1;
        background: $primary-darken-2;
        color: $text;
        padding: 0 1;
    }
    TerminalView RichLog {
        height: 1fr;
    }
    TerminalView #terminal_input {
        height: 3;
        border-top: solid $primary;
    }
    """

    class LineSubmitted(TMessage):
        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()

    def compose(self) -> ComposeResult:
        yield Label("", id="terminal_header")
        yield RichLog(id="terminal_log", auto_scroll=True, markup=False)
        yield Input(placeholder="Type and press Enter to send...", id="terminal_input")

    def set_header(self, text: str) -> None:
        self.query_one("#terminal_header", Label).update(text)

    def append_line(self, text: str) -> None:
        self.query_one("#terminal_log", RichLog).write(text)

    def clear(self) -> None:
        self.query_one("#terminal_log", RichLog).clear()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if text:
            self.post_message(self.LineSubmitted(text))
            event.input.clear()
