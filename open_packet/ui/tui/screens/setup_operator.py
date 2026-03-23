from __future__ import annotations
import re
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Switch
from textual.containers import Vertical, Horizontal
from open_packet.store.models import Operator


CALLSIGN_RE = re.compile(r'^[A-Za-z0-9]{1,6}$')


class OperatorSetupScreen(ModalScreen):
    DEFAULT_CSS = """
    OperatorSetupScreen {
        align: center middle;
    }
    OperatorSetupScreen Vertical {
        width: 50;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    OperatorSetupScreen .error {
        color: $error;
        height: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Operator Setup")
            yield Label("Callsign:")
            yield Input(placeholder="e.g. KD9ABC", id="callsign_field")
            yield Label("", id="callsign_error", classes="error")
            yield Label("SSID (0-15):")
            yield Input(placeholder="0", id="ssid_field")
            yield Label("", id="ssid_error", classes="error")
            yield Label("Label:")
            yield Input(placeholder="e.g. home", id="label_field")
            yield Label("", id="label_error", classes="error")
            yield Label("Set as default:")
            yield Switch(value=True, id="default_switch")
            with Horizontal():
                yield Button("Save", variant="primary", id="save_btn")
                yield Button("Cancel", id="cancel_btn")

    def _validate(self) -> bool:
        valid = True
        callsign = self.query_one("#callsign_field", Input).value.strip()
        ssid_str = self.query_one("#ssid_field", Input).value.strip()
        label = self.query_one("#label_field", Input).value.strip()

        callsign_error = self.query_one("#callsign_error", Label)
        ssid_error = self.query_one("#ssid_error", Label)
        label_error = self.query_one("#label_error", Label)

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

        if not label:
            label_error.update("Label is required")
            valid = False
        else:
            label_error.update("")

        return valid

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.dismiss(None)
        elif event.button.id == "save_btn":
            if self._validate():
                callsign = self.query_one("#callsign_field", Input).value.strip().upper()
                ssid = int(self.query_one("#ssid_field", Input).value.strip())
                label = self.query_one("#label_field", Input).value.strip()
                is_default = self.query_one("#default_switch", Switch).value
                self.dismiss(Operator(
                    callsign=callsign,
                    ssid=ssid,
                    label=label,
                    is_default=is_default,
                ))

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
