from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from textual.containers import Vertical


class SettingsScreen(ModalScreen):
    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
    }
    SettingsScreen Vertical {
        width: 40;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    SettingsScreen Button {
        width: 100%;
        margin: 0 0 1 0;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Settings")
            yield Button("General", id="general_btn")
            yield Button("Operator", id="operator_btn")
            yield Button("Node", id="node_btn")
            yield Button("Interfaces", id="interfaces_btn")
            yield Button("Close", id="close_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "general_btn":
            self.dismiss("general")
        elif event.button.id == "operator_btn":
            self.dismiss("operator")
        elif event.button.id == "node_btn":
            self.dismiss("node")
        elif event.button.id == "interfaces_btn":
            self.dismiss("interfaces")
        else:
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
