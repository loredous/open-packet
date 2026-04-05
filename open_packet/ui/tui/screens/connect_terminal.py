# open_packet/ui/tui/screens/connect_terminal.py
from __future__ import annotations
from typing import Optional
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select
from textual.containers import Vertical, Horizontal
from open_packet.store.database import Database
from open_packet.store.models import Interface, Node
from open_packet.terminal.session import TerminalConnectResult
from open_packet.ui.tui.screens import CALLSIGN_RE

_CUSTOM = "__custom__"
_NO_IFACE = "__none__"


class ConnectTerminalScreen(ModalScreen):
    DEFAULT_CSS = """
    ConnectTerminalScreen {
        align: center middle;
    }
    ConnectTerminalScreen > Vertical {
        width: 55;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    ConnectTerminalScreen .error {
        color: $error;
        height: 1;
    }
    """

    def __init__(self, db: Database, **kwargs) -> None:
        super().__init__(**kwargs)
        self._db = db
        self._node_list: list[Node] = []
        self._iface_list: list[Interface] = []

    def compose(self) -> ComposeResult:
        self._node_list = self._db.list_nodes()
        self._iface_list = self._db.list_interfaces()

        node_options = [("— custom connection —", _CUSTOM)]
        for n in self._node_list:
            node_options.append((n.label, str(n.id)))

        iface_options = [("— select interface —", _NO_IFACE)]
        for iface in self._iface_list:
            display = iface.label or f"{iface.iface_type}:{iface.host}"
            iface_options.append((display, str(iface.id)))

        with Vertical():
            yield Label("Connect to Station")
            yield Label("Node:")
            yield Select(node_options, value=_CUSTOM, id="node_select")
            yield Label("Interface:")
            yield Select(iface_options, value=_NO_IFACE, id="iface_select")
            yield Label("", id="iface_error", classes="error")
            yield Label("Callsign:")
            yield Input(placeholder="e.g. W0XYZ", id="callsign_field")
            yield Label("SSID (optional, 0–15):")
            yield Input(placeholder="0", id="ssid_field")
            yield Label("", id="callsign_error", classes="error")
            with Horizontal():
                yield Button("Connect", variant="primary", id="connect_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "node_select":
            self._on_node_changed(event.value)
        elif event.select.id == "iface_select":
            self._refresh_callsign_state()

    def _on_node_changed(self, value) -> None:
        if value == _CUSTOM or value == Select.BLANK:
            return
        node = next((n for n in self._node_list if str(n.id) == str(value)), None)
        if node is None:
            return
        if node.interface_id is not None:
            self.query_one("#iface_select", Select).value = str(node.interface_id)
        self.query_one("#callsign_field", Input).value = node.callsign
        ssid_val = str(node.ssid) if node.ssid is not None else ""
        self.query_one("#ssid_field", Input).value = ssid_val
        self._refresh_callsign_state()

    def _active_iface(self) -> Optional[Interface]:
        val = self.query_one("#iface_select", Select).value
        if not val or val in (Select.BLANK, _NO_IFACE):
            return None
        return next((i for i in self._iface_list if str(i.id) == str(val)), None)

    def _refresh_callsign_state(self) -> None:
        iface = self._active_iface()
        is_telnet = iface is not None and iface.iface_type == "telnet"
        self.query_one("#callsign_field", Input).disabled = is_telnet
        self.query_one("#ssid_field", Input).disabled = is_telnet

    def _validate(self) -> bool:
        iface = self._active_iface()
        iface_err = self.query_one("#iface_error", Label)
        call_err = self.query_one("#callsign_error", Label)

        if iface is None:
            iface_err.update("Interface is required")
            return False
        iface_err.update("")

        if iface.iface_type == "telnet":
            call_err.update("")
            return True

        callsign = self.query_one("#callsign_field", Input).value.strip()
        ssid_str = self.query_one("#ssid_field", Input).value.strip()

        if not CALLSIGN_RE.match(callsign):
            call_err.update("Callsign must be 1-6 alphanumeric characters")
            return False

        try:
            ssid = int(ssid_str) if ssid_str else 0
            if not 0 <= ssid <= 15:
                raise ValueError
        except ValueError:
            call_err.update("SSID must be 0–15")
            return False

        call_err.update("")
        return True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.dismiss(None)
            return
        if event.button.id != "connect_btn":
            return
        if not self._validate():
            return

        iface = self._active_iface()
        assert iface is not None

        callsign = self.query_one("#callsign_field", Input).value.strip().upper()
        ssid_str = self.query_one("#ssid_field", Input).value.strip()
        ssid = int(ssid_str) if ssid_str else 0

        node_val = self.query_one("#node_select", Select).value
        if node_val not in (_CUSTOM, Select.BLANK):
            node = next((n for n in self._node_list if str(n.id) == str(node_val)), None)
            label = node.label if node else (callsign or iface.label or "session")
        elif iface.iface_type == "telnet":
            label = iface.label or iface.host or "telnet"
        else:
            label = callsign or "session"

        self.dismiss(TerminalConnectResult(
            label=label,
            interface=iface,
            target_callsign=callsign,
            target_ssid=ssid,
        ))

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
