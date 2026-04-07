from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from textual.containers import Vertical, Horizontal


class DeleteConfirmScreen(ModalScreen[bool]):
    DEFAULT_CSS = """
    DeleteConfirmScreen {
        align: center middle;
    }
    DeleteConfirmScreen > Vertical {
        width: 60;
        height: auto;
        border: solid $error;
        background: $surface;
        padding: 1 2;
    }
    DeleteConfirmScreen #confirm_body {
        margin: 1 0;
    }
    DeleteConfirmScreen .footer-row {
        height: 3;
        align: right middle;
    }
    DeleteConfirmScreen .footer-row Button {
        width: auto;
        min-width: 12;
        margin: 0 0 0 1;
    }
    """

    def __init__(self, title: str, body: str, **kwargs):
        super().__init__(**kwargs)
        self._title = title
        self._body = body

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title)
            yield Label(self._body, id="confirm_body")
            with Horizontal(classes="footer-row"):
                yield Button("Delete", id="delete_btn", variant="error")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "delete_btn")

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)
