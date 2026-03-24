# open_packet/ui/tui/screens/setup_interface.py
from __future__ import annotations
from typing import Optional
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select
from textual.containers import Vertical, Horizontal
from open_packet.store.models import Interface

_CONN_TYPES = [("Telnet", "telnet"), ("KISS TCP", "kiss_tcp"), ("KISS Serial", "kiss_serial")]


class InterfaceSetupScreen(ModalScreen):
    DEFAULT_CSS = """
    InterfaceSetupScreen {
        align: center middle;
    }
    InterfaceSetupScreen > Vertical {
        width: 55;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    InterfaceSetupScreen .error {
        color: $error;
        height: 1;
    }
    """

    def __init__(self, interface: Optional[Interface] = None, **kwargs):
        super().__init__(**kwargs)
        self._interface = interface

    def compose(self) -> ComposeResult:
        iface = self._interface
        title = "Edit Interface" if iface else "New Interface"
        default_type = iface.iface_type if iface else "telnet"

        with Vertical():
            yield Label(title)
            yield Label("Label:")
            yield Input(placeholder="e.g. Home TNC", id="iface_label_field",
                        value=iface.label if iface else "")
            yield Label("", id="label_error", classes="error")
            yield Label("Type:")
            yield Select(_CONN_TYPES, value=default_type, id="iface_type_select")

            with Vertical(id="telnet_fields"):
                yield Label("Host:")
                yield Input(placeholder="e.g. 192.168.1.209", id="host_field",
                            value=iface.host or "" if iface else "")
                yield Label("Port:")
                yield Input(placeholder="8023", id="port_field",
                            value=str(iface.port) if iface and iface.port else "")
                yield Label("Username:")
                yield Input(placeholder="e.g. K0JLB", id="username_field",
                            value=iface.username or "" if iface else "")
                yield Label("Password:")
                yield Input(placeholder="", id="password_field", password=True,
                            value=iface.password or "" if iface else "")

            with Vertical(id="kiss_tcp_fields"):
                yield Label("Host:")
                yield Input(placeholder="e.g. 192.168.1.1", id="kiss_tcp_host_field",
                            value=iface.host or "" if iface else "")
                yield Label("Port:")
                yield Input(placeholder="8910", id="kiss_tcp_port_field",
                            value=str(iface.port) if iface and iface.port else "")

            with Vertical(id="kiss_serial_fields"):
                yield Label("Device:")
                yield Input(placeholder="/dev/ttyUSB0", id="device_field",
                            value=iface.device or "" if iface else "")
                yield Label("Baud:")
                yield Input(placeholder="9600", id="baud_field",
                            value=str(iface.baud) if iface and iface.baud else "")

            yield Label("", id="conn_error", classes="error")

            with Horizontal():
                yield Button("Save", variant="primary", id="save_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_mount(self) -> None:
        self._refresh_visibility()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "iface_type_select":
            self._refresh_visibility()

    def _iface_type(self) -> str:
        v = self.query_one("#iface_type_select", Select).value
        return str(v) if v and v != Select.BLANK else "telnet"

    def _refresh_visibility(self) -> None:
        t = self._iface_type()
        self.query_one("#telnet_fields").display = (t == "telnet")
        self.query_one("#kiss_tcp_fields").display = (t == "kiss_tcp")
        self.query_one("#kiss_serial_fields").display = (t == "kiss_serial")

    def _validate(self) -> bool:
        label = self.query_one("#iface_label_field", Input).value.strip()
        if not label:
            self.query_one("#label_error", Label).update("Label is required")
            return False
        self.query_one("#label_error", Label).update("")

        t = self._iface_type()
        err = self.query_one("#conn_error", Label)

        if t == "telnet":
            host = self.query_one("#host_field", Input).value.strip()
            port_str = self.query_one("#port_field", Input).value.strip()
            user = self.query_one("#username_field", Input).value.strip()
            pw = self.query_one("#password_field", Input).value.strip()
            if not host or not user or not pw:
                err.update("Host, username, and password are required")
                return False
            try:
                if int(port_str) <= 0:
                    raise ValueError
            except ValueError:
                err.update("Port must be a positive integer")
                return False

        elif t == "kiss_tcp":
            host = self.query_one("#kiss_tcp_host_field", Input).value.strip()
            port_str = self.query_one("#kiss_tcp_port_field", Input).value.strip()
            if not host:
                err.update("Host is required")
                return False
            try:
                if int(port_str) <= 0:
                    raise ValueError
            except ValueError:
                err.update("Port must be a positive integer")
                return False

        elif t == "kiss_serial":
            device = self.query_one("#device_field", Input).value.strip()
            baud_str = self.query_one("#baud_field", Input).value.strip()
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

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.dismiss(None)
        elif event.button.id == "save_btn":
            if not self._validate():
                return
            label = self.query_one("#iface_label_field", Input).value.strip()
            t = self._iface_type()

            if t == "telnet":
                host = self.query_one("#host_field", Input).value.strip()
                port = int(self.query_one("#port_field", Input).value.strip())
                username = self.query_one("#username_field", Input).value.strip()
                password = self.query_one("#password_field", Input).value.strip()
                self.dismiss(Interface(
                    id=self._interface.id if self._interface else None,
                    label=label, iface_type=t,
                    host=host, port=port, username=username, password=password,
                ))
            elif t == "kiss_tcp":
                host = self.query_one("#kiss_tcp_host_field", Input).value.strip()
                port = int(self.query_one("#kiss_tcp_port_field", Input).value.strip())
                self.dismiss(Interface(
                    id=self._interface.id if self._interface else None,
                    label=label, iface_type=t, host=host, port=port,
                ))
            elif t == "kiss_serial":
                device = self.query_one("#device_field", Input).value.strip()
                baud = int(self.query_one("#baud_field", Input).value.strip())
                self.dismiss(Interface(
                    id=self._interface.id if self._interface else None,
                    label=label, iface_type=t, device=device, baud=baud,
                ))

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
