# open_packet/ui/tui/screens/setup_node.py
from __future__ import annotations
from typing import Optional
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Switch, Select, TextArea
from textual.containers import Vertical, Horizontal
from open_packet.store.database import Database
from open_packet.store.models import Node, Interface
from open_packet.ui.tui.screens import CALLSIGN_RE

_NEW_IFACE = "__new__"
_CONN_TYPES = [("Telnet", "telnet"), ("KISS TCP", "kiss_tcp"), ("KISS Serial", "kiss_serial")]


def _hops_to_text(hops) -> str:
    lines = []
    for h in hops:
        lines.append(f"{h.callsign}:{h.port}" if h.port is not None else h.callsign)
    return "\n".join(lines)


def _text_to_hops(text: str) -> list:
    from open_packet.store.models import NodeHop
    hops = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            parts = line.rsplit(":", 1)
            try:
                hops.append(NodeHop(callsign=parts[0].strip(), port=int(parts[1])))
            except ValueError:
                hops.append(NodeHop(callsign=line))
        else:
            hops.append(NodeHop(callsign=line))
    return hops


class NodeSetupScreen(ModalScreen):
    DEFAULT_CSS = """
    NodeSetupScreen {
        align: center middle;
    }
    NodeSetupScreen > Vertical {
        width: 90%;
        height: auto;
        max-height: 90%;
        overflow-y: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    NodeSetupScreen .error {
        color: $error;
        height: 1;
    }
    NodeSetupScreen .section {
        margin-top: 1;
    }
    """

    def __init__(
        self,
        node: Optional[Node] = None,
        interfaces: Optional[list[Interface]] = None,
        db: Optional[Database] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._node = node
        self._interfaces = interfaces or []
        self._db = db

    def compose(self) -> ComposeResult:
        n = self._node
        title = "Edit Node" if n else "Node Setup"
        default_type = "telnet"
        if n and n.interface_id:
            existing = next((i for i in self._interfaces if i.id == n.interface_id), None)
            if existing:
                default_type = existing.iface_type

        with Vertical():
            yield Label(title)
            yield Label("Label:")
            yield Input(placeholder="e.g. Home BBS", id="label_field",
                        value=n.label if n else "")
            yield Label("", id="label_error", classes="error")
            yield Label("Callsign:")
            yield Input(placeholder="e.g. W0BPQ", id="callsign_field",
                        value=n.callsign if n else "")
            yield Label("", id="callsign_error", classes="error")
            yield Label("SSID (optional, 0–15):")
            yield Input(placeholder="0", id="ssid_field",
                        value=str(n.ssid) if n else "")
            yield Label("", id="ssid_error", classes="error")
            yield Label("Set as default:")
            yield Switch(value=n.is_default if n else True, id="default_switch")

            yield Label("Connection Type:", classes="section")
            yield Select(_CONN_TYPES, value=default_type, id="conn_type_select")
            yield Label("Interface:")
            yield Select([("— New interface —", _NEW_IFACE)], value=_NEW_IFACE,
                         id="iface_selector")

            with Vertical(id="telnet_fields"):
                yield Label("Host:")
                yield Input(placeholder="e.g. 192.168.1.209", id="telnet_host")
                yield Label("Port:")
                yield Input(placeholder="8023", id="telnet_port")
                yield Label("Username:")
                yield Input(placeholder="e.g. K0JLB", id="telnet_user")
                yield Label("Password:")
                yield Input(placeholder="", id="telnet_pass", password=True)
                yield Label("Interface Label (optional):")
                yield Input(placeholder="auto-generated if blank", id="iface_label_telnet")

            with Vertical(id="kiss_tcp_fields"):
                yield Label("Host:")
                yield Input(placeholder="e.g. 192.168.1.1", id="kiss_tcp_host")
                yield Label("Port:")
                yield Input(placeholder="8910", id="kiss_tcp_port")
                yield Label("Interface Label (optional):")
                yield Input(placeholder="auto-generated if blank", id="iface_label_kiss_tcp")

            with Vertical(id="kiss_serial_fields"):
                yield Label("Device:")
                yield Input(placeholder="/dev/ttyUSB0", id="kiss_serial_device")
                yield Label("Baud:")
                yield Input(placeholder="9600", id="kiss_serial_baud")
                yield Label("Interface Label (optional):")
                yield Input(placeholder="auto-generated if blank", id="iface_label_kiss_serial")

            yield Label("", id="conn_error", classes="error")

            yield Label("Path Strategy:", classes="section")
            yield Select(
                [("Path Route", "path_route"), ("Digipeat", "digipeat")],
                value=getattr(n, "path_strategy", "path_route") if n else "path_route",
                id="strategy_select",
            )

            yield Label("Hop Path (one per line, CALLSIGN or CALLSIGN:PORT):")
            yield TextArea(
                _hops_to_text(getattr(n, "hop_path", []) if n else []),
                id="hop_path_area",
            )

            yield Label("Auto Forward:")
            yield Switch(value=getattr(n, "auto_forward", False) if n else False, id="auto_forward_switch")

            with Horizontal():
                yield Button("Save", variant="primary", id="save_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_mount(self) -> None:
        self._refresh_iface_selector()
        self._refresh_field_visibility()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "conn_type_select":
            self._refresh_iface_selector()
            self._refresh_field_visibility()
        elif event.select.id == "iface_selector":
            self._refresh_field_visibility()

    def _conn_type(self) -> str:
        v = self.query_one("#conn_type_select", Select).value
        return str(v) if v and v != Select.BLANK else "telnet"

    def _using_new_iface(self) -> bool:
        v = self.query_one("#iface_selector", Select).value
        return v == _NEW_IFACE or v == Select.BLANK

    def _refresh_iface_selector(self) -> None:
        conn_type = self._conn_type()
        matching = [i for i in self._interfaces if i.iface_type == conn_type]
        options = [("— New interface —", _NEW_IFACE)]
        for i in matching:
            if i.label:
                display = i.label
            elif i.iface_type == "kiss_serial":
                display = i.device or "serial"
            else:
                display = f"{i.host}:{i.port}"
            options.append((display, i.id))
        sel = self.query_one("#iface_selector", Select)
        sel.set_options(options)
        # Pre-select the node's existing interface if editing
        if self._node and self._node.interface_id:
            match = next((i for i in matching if i.id == self._node.interface_id), None)
            if match:
                sel.value = match.id
                return
        sel.value = _NEW_IFACE

    def _refresh_field_visibility(self) -> None:
        conn_type = self._conn_type()
        using_new = self._using_new_iface()
        self.query_one("#telnet_fields").display = (conn_type == "telnet" and using_new)
        self.query_one("#kiss_tcp_fields").display = (conn_type == "kiss_tcp" and using_new)
        self.query_one("#kiss_serial_fields").display = (conn_type == "kiss_serial" and using_new)

    def _validate(self) -> bool:
        valid = True
        label = self.query_one("#label_field", Input).value.strip()
        callsign = self.query_one("#callsign_field", Input).value.strip()
        ssid_str = self.query_one("#ssid_field", Input).value.strip()

        if not label:
            self.query_one("#label_error", Label).update("Label is required")
            valid = False
        else:
            self.query_one("#label_error", Label).update("")

        if not CALLSIGN_RE.match(callsign):
            self.query_one("#callsign_error", Label).update(
                "Callsign must be 1-6 alphanumeric characters"
            )
            valid = False
        else:
            self.query_one("#callsign_error", Label).update("")

        try:
            ssid = int(ssid_str) if ssid_str else 0
            if not 0 <= ssid <= 15:
                raise ValueError
            self.query_one("#ssid_error", Label).update("")
        except ValueError:
            self.query_one("#ssid_error", Label).update("SSID must be an integer 0-15")
            valid = False

        if self._using_new_iface():
            valid = self._validate_new_iface() and valid

        return valid

    def _validate_new_iface(self) -> bool:
        conn_type = self._conn_type()
        err = self.query_one("#conn_error", Label)

        if conn_type == "telnet":
            host = self.query_one("#telnet_host", Input).value.strip()
            port_str = self.query_one("#telnet_port", Input).value.strip()
            user = self.query_one("#telnet_user", Input).value.strip()
            pw = self.query_one("#telnet_pass", Input).value.strip()
            if not host or not user or not pw:
                err.update("Host, username, and password are required")
                return False
            try:
                if int(port_str) <= 0:
                    raise ValueError
            except ValueError:
                err.update("Port must be a positive integer")
                return False

        elif conn_type == "kiss_tcp":
            host = self.query_one("#kiss_tcp_host", Input).value.strip()
            port_str = self.query_one("#kiss_tcp_port", Input).value.strip()
            if not host:
                err.update("Host is required")
                return False
            try:
                if int(port_str) <= 0:
                    raise ValueError
            except ValueError:
                err.update("Port must be a positive integer")
                return False

        elif conn_type == "kiss_serial":
            device = self.query_one("#kiss_serial_device", Input).value.strip()
            baud_str = self.query_one("#kiss_serial_baud", Input).value.strip()
            if not device:
                err.update("Device is required")
                return False
            try:
                if int(baud_str) <= 0:
                    raise ValueError
            except ValueError:
                err.update("Baud must be a positive integer")
                return False

        err.update("")
        return True

    def _build_and_save_interface(self) -> int:
        """Insert a new Interface record and return its id."""
        assert self._db is not None
        conn_type = self._conn_type()
        callsign = self.query_one("#callsign_field", Input).value.strip().upper()

        if conn_type == "telnet":
            host = self.query_one("#telnet_host", Input).value.strip()
            port = int(self.query_one("#telnet_port", Input).value.strip())
            username = self.query_one("#telnet_user", Input).value.strip()
            password = self.query_one("#telnet_pass", Input).value.strip()
            label = (self.query_one("#iface_label_telnet", Input).value.strip()
                     or f"{callsign} via {host}")
            iface = Interface(label=label, iface_type="telnet",
                              host=host, port=port, username=username, password=password)

        elif conn_type == "kiss_tcp":
            host = self.query_one("#kiss_tcp_host", Input).value.strip()
            port = int(self.query_one("#kiss_tcp_port", Input).value.strip())
            label = (self.query_one("#iface_label_kiss_tcp", Input).value.strip()
                     or f"{callsign} via {host}")
            iface = Interface(label=label, iface_type="kiss_tcp", host=host, port=port)

        else:  # kiss_serial
            device = self.query_one("#kiss_serial_device", Input).value.strip()
            baud = int(self.query_one("#kiss_serial_baud", Input).value.strip())
            label = (self.query_one("#iface_label_kiss_serial", Input).value.strip()
                     or f"{callsign} via {device}")
            iface = Interface(label=label, iface_type="kiss_serial", device=device, baud=baud)

        saved = self._db.insert_interface(iface)
        assert saved is not None and saved.id is not None, "insert_interface returned no id"
        return saved.id

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.dismiss(None)
        elif event.button.id == "save_btn":
            if self._validate():
                label = self.query_one("#label_field", Input).value.strip()
                callsign = self.query_one("#callsign_field", Input).value.strip().upper()
                ssid = int(self.query_one("#ssid_field", Input).value.strip() or "0")
                is_default = self.query_one("#default_switch", Switch).value

                if self._using_new_iface():
                    interface_id = self._build_and_save_interface()
                else:
                    interface_id = self.query_one("#iface_selector", Select).value
                    assert isinstance(interface_id, int), f"Expected int interface id, got {interface_id!r}"

                hop_path = _text_to_hops(self.query_one("#hop_path_area", TextArea).text)
                path_strategy = str(self.query_one("#strategy_select", Select).value)
                auto_forward = self.query_one("#auto_forward_switch", Switch).value

                self.dismiss(Node(
                    label=label,
                    callsign=callsign,
                    ssid=ssid,
                    node_type="bpq",
                    is_default=is_default,
                    interface_id=interface_id,
                    id=self._node.id if self._node else None,
                    hop_path=hop_path,
                    path_strategy=path_strategy,
                    auto_forward=auto_forward,
                ))

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
