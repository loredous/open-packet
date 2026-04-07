# open_packet/ui/tui/widgets/status_bar.py
from __future__ import annotations
from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.events import Click
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Label
from textual.containers import Horizontal
from textual.reactive import reactive
from open_packet.engine.events import ConnectionStatus


class StatusBar(Widget):
    class IdentityClicked(Message):
        def __init__(self, kind: str) -> None:
            super().__init__()
            self.kind = kind

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
        content-align: left middle;
    }
    #identity_container {
        width: auto;
        height: 1;
        layout: horizontal;
    }
    #identity_sep {
        width: auto;
        content-align: left middle;
    }
    .identity-lbl {
        width: auto;
        height: 1;
        content-align: left middle;
        background: $primary;
        color: $text;
    }
    .identity-lbl:hover {
        background: $primary-lighten-1;
    }
    .identity-mid-sep {
        width: auto;
        content-align: left middle;
    }
    """

    status: reactive[ConnectionStatus] = reactive(ConnectionStatus.DISCONNECTED)
    sync_detail: reactive[str] = reactive("")
    last_sync: reactive[str] = reactive("Never")
    operator: reactive[str] = reactive("")
    node: reactive[str] = reactive("")
    interface_label: reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        yield Label("", id="status_left")
        with Horizontal(id="identity_container"):
            yield Label("│  ", id="identity_sep")
            yield Label("", id="identity_operator", classes="identity-lbl")
            yield Label("  :  ", classes="identity-mid-sep", id="identity_sep_node")
            yield Label("", id="identity_node", classes="identity-lbl")
            yield Label("  :  ", classes="identity-mid-sep", id="identity_sep_iface")
            yield Label("", id="identity_interface", classes="identity-lbl")

    def on_mount(self) -> None:
        self._render_left()
        self._render_identity()

    def watch_status(self, _) -> None:
        self._render_left()

    def watch_sync_detail(self, _) -> None:
        self._render_left()

    def watch_last_sync(self, _) -> None:
        self._render_left()

    def watch_operator(self, _) -> None:
        self._render_identity()

    def watch_node(self, _) -> None:
        self._render_identity()

    def watch_interface_label(self, _) -> None:
        self._render_identity()

    def _render_left(self) -> None:
        icon = {
            ConnectionStatus.DISCONNECTED: "○",
            ConnectionStatus.CONNECTING: "◎",
            ConnectionStatus.CONNECTED: "●",
            ConnectionStatus.SYNCING: "⟳",
            ConnectionStatus.ERROR: "✗",
        }.get(self.status, "?")
        status_text = self.status.value.title()
        if self.status == ConnectionStatus.SYNCING and self.sync_detail:
            status_text = f"Syncing: {self.sync_detail}"
        text = f"📻 open-packet  {icon}  {status_text}  | Last sync: {self.last_sync}"
        try:
            self.query_one("#status_left", Label).update(text)
        except NoMatches:
            return

    def _render_identity(self) -> None:
        try:
            any_set = bool(self.operator or self.node or self.interface_label)
            self.query_one("#identity_container").display = any_set
            self.query_one("#identity_operator", Label).update(self.operator)
            self.query_one("#identity_operator").display = bool(self.operator)
            self.query_one("#identity_sep_node").display = bool(self.operator and self.node)
            self.query_one("#identity_node", Label).update(self.node)
            self.query_one("#identity_node").display = bool(self.node)
            self.query_one("#identity_sep_iface").display = bool(self.node and self.interface_label)
            self.query_one("#identity_interface", Label).update(self.interface_label)
            self.query_one("#identity_interface").display = bool(self.interface_label)
        except NoMatches:
            return

    def on_click(self, event: Click) -> None:
        kind_map = {
            "identity_operator": "operator",
            "identity_node": "node",
            "identity_interface": "interface",
        }
        widget_id = getattr(event.widget, "id", "") or ""
        kind = kind_map.get(widget_id)
        if kind:
            event.stop()
            self.post_message(self.IdentityClicked(kind))
