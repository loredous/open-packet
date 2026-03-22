# open_packet/ui/tui/widgets/status_bar.py
from __future__ import annotations
from textual.widget import Widget
from textual.reactive import reactive
from open_packet.engine.events import ConnectionStatus


class StatusBar(Widget):
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }
    """

    callsign: reactive[str] = reactive("---")
    status: reactive[ConnectionStatus] = reactive(ConnectionStatus.DISCONNECTED)
    last_sync: reactive[str] = reactive("Never")

    def render(self) -> str:
        status_icon = {
            ConnectionStatus.DISCONNECTED: "○",
            ConnectionStatus.CONNECTING: "◎",
            ConnectionStatus.CONNECTED: "●",
            ConnectionStatus.SYNCING: "⟳",
            ConnectionStatus.ERROR: "✗",
        }.get(self.status, "?")
        return (
            f"open-packet  {self.callsign}  "
            f"{status_icon}  {self.status.value.title()}  "
            f"| Last sync: {self.last_sync}"
        )
