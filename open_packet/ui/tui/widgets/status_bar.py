# open_packet/ui/tui/widgets/status_bar.py
from __future__ import annotations
from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Label
from textual.reactive import reactive
from open_packet.engine.events import ConnectionStatus


class StatusBar(Widget):
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
        layout: horizontal;
    }
    #status_left {
        width: 1fr;
    }
    #status_right {
        width: auto;
    }
    """

    status: reactive[ConnectionStatus] = reactive(ConnectionStatus.DISCONNECTED)
    last_sync: reactive[str] = reactive("Never")
    operator: reactive[str] = reactive("")
    node: reactive[str] = reactive("")
    interface_label: reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        yield Label("", id="status_left")
        yield Label("", id="status_right")

    def on_mount(self) -> None:
        self._render_left()
        self._render_right()

    # --- Watchers ---

    def watch_status(self, _) -> None:
        self._render_left()

    def watch_last_sync(self, _) -> None:
        self._render_left()

    def watch_operator(self, _) -> None:
        self._render_right()

    def watch_node(self, _) -> None:
        self._render_right()

    def watch_interface_label(self, _) -> None:
        self._render_right()

    # --- Render helpers ---

    def _render_left(self) -> None:
        icon = {
            ConnectionStatus.DISCONNECTED: "○",
            ConnectionStatus.CONNECTING: "◎",
            ConnectionStatus.CONNECTED: "●",
            ConnectionStatus.SYNCING: "⟳",
            ConnectionStatus.ERROR: "✗",
        }.get(self.status, "?")
        text = f"📻 open-packet  {icon}  {self.status.value.title()}  | Last sync: {self.last_sync}"
        try:
            self.query_one("#status_left", Label).update(text)
        except NoMatches:
            return

    def _render_right(self) -> None:
        fields = [f for f in [self.operator, self.node, self.interface_label] if f]
        right = ("│  " + "  :  ".join(fields)) if fields else ""
        try:
            self.query_one("#status_right", Label).update(right)
        except NoMatches:
            return
