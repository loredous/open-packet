from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from textual.containers import Vertical, Horizontal


class ShorterPathConfirmScreen(ModalScreen):
    DEFAULT_CSS = """
    ShorterPathConfirmScreen { align: center middle; }
    ShorterPathConfirmScreen Vertical {
        width: 60; height: auto; border: solid $primary;
        background: $surface; padding: 1 2;
    }
    """

    def __init__(self, node_label: str, current_len: int,
                 new_path_summary: str, **kwargs):
        super().__init__(**kwargs)
        self._node_label = node_label
        self._current_len = current_len
        self._new_path_summary = new_path_summary

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"Shorter path discovered for [b]{self._node_label}[/b]")
            yield Label(f"Current path: {self._current_len} hop(s)")
            yield Label(f"Shorter path: {self._new_path_summary}")
            yield Label("Update to shorter path?")
            with Horizontal():
                yield Button("Update", variant="primary", id="update_btn")
                yield Button("Skip", id="skip_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "update_btn")

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)
