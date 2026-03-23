from __future__ import annotations
from typing import Optional
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Switch
from textual.containers import Vertical, Horizontal
from open_packet.store.models import Node
from open_packet.ui.tui.screens import CALLSIGN_RE


class NodeSetupScreen(ModalScreen):
    DEFAULT_CSS = """
    NodeSetupScreen {
        align: center middle;
    }
    NodeSetupScreen Vertical {
        width: 50;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    NodeSetupScreen .error {
        color: $error;
        height: 1;
    }
    """

    def __init__(self, node: Optional[Node] = None, **kwargs):
        super().__init__(**kwargs)
        self._node = node

    def compose(self) -> ComposeResult:
        n = self._node
        title = "Edit Node" if n else "Node Setup"
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
            yield Label("SSID (0-15):")
            yield Input(placeholder="0", id="ssid_field",
                        value=str(n.ssid) if n else "")
            yield Label("", id="ssid_error", classes="error")
            yield Label("Node Type: bpq")
            yield Label("Set as default:")
            yield Switch(value=n.is_default if n else True, id="default_switch")
            with Horizontal():
                yield Button("Save", variant="primary", id="save_btn")
                yield Button("Cancel", id="cancel_btn")

    def _validate(self) -> bool:
        valid = True
        label = self.query_one("#label_field", Input).value.strip()
        callsign = self.query_one("#callsign_field", Input).value.strip()
        ssid_str = self.query_one("#ssid_field", Input).value.strip()

        label_error = self.query_one("#label_error", Label)
        callsign_error = self.query_one("#callsign_error", Label)
        ssid_error = self.query_one("#ssid_error", Label)

        if not label:
            label_error.update("Label is required")
            valid = False
        else:
            label_error.update("")

        if not CALLSIGN_RE.match(callsign):
            callsign_error.update("Callsign must be 1-6 alphanumeric characters")
            valid = False
        else:
            callsign_error.update("")

        try:
            ssid = int(ssid_str)
            if not 0 <= ssid <= 15:
                raise ValueError
            ssid_error.update("")
        except ValueError:
            ssid_error.update("SSID must be an integer 0-15")
            valid = False

        return valid

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.dismiss(None)
        elif event.button.id == "save_btn":
            if self._validate():
                label = self.query_one("#label_field", Input).value.strip()
                callsign = self.query_one("#callsign_field", Input).value.strip().upper()
                ssid = int(self.query_one("#ssid_field", Input).value.strip())
                is_default = self.query_one("#default_switch", Switch).value
                self.dismiss(Node(
                    label=label,
                    callsign=callsign,
                    ssid=ssid,
                    node_type=self._node.node_type if self._node else "bpq",
                    is_default=is_default,
                    id=self._node.id if self._node else None,
                ))

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
