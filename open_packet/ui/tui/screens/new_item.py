# open_packet/ui/tui/screens/new_item.py
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class NewItemScreen(ModalScreen[str | None]):
    """Modal for selecting the type of new item to create."""

    DEFAULT_CSS = """
    NewItemScreen {
        align: center middle;
    }
    #dialog {
        width: 40;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    #title {
        text-align: center;
        margin-bottom: 1;
    }
    Button {
        width: 100%;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("m", "new_message", "New Message"),
        Binding("b", "new_bulletin", "New Bulletin"),
        Binding("f", "new_form", "New Form Message"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Create New Item", id="title")
            yield Button("[m] Message", id="btn_message", variant="primary")
            yield Button("[b] Bulletin", id="btn_bulletin", variant="primary")
            yield Button("[f] Form Message", id="btn_form", variant="primary")
            yield Button("Cancel", id="btn_cancel", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn_message":
            self.dismiss("message")
        elif button_id == "btn_bulletin":
            self.dismiss("bulletin")
        elif button_id == "btn_form":
            self.dismiss("form")
        else:
            self.dismiss(None)

    def action_new_message(self) -> None:
        self.dismiss("message")

    def action_new_bulletin(self) -> None:
        self.dismiss("bulletin")

    def action_new_form(self) -> None:
        self.dismiss("form")

    def action_cancel(self) -> None:
        self.dismiss(None)
