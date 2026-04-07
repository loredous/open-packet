# open_packet/ui/tui/screens/compose.py
from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, TextArea
from textual.containers import Vertical, Horizontal
from open_packet.engine.commands import SendMessageCommand


class ComposeScreen(ModalScreen):
    DEFAULT_CSS = """
    ComposeScreen {
        align: center middle;
    }
    ComposeScreen Vertical {
        width: 70;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    ComposeScreen TextArea {
        height: 10;
    }
    """

    def __init__(self, to_call: str = "", subject: str = "", **kwargs):
        super().__init__(**kwargs)
        self._to_call = to_call
        self._subject = subject

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("New Message", id="compose_title")
            yield Label("To:")
            yield Input(value=self._to_call, placeholder="Callsign", id="to_field")
            yield Label("Subject:")
            yield Input(value=self._subject, placeholder="Subject", id="subject_field")
            yield Label("Body:")
            yield TextArea(id="body_field")
            with Horizontal():
                yield Button("Send", variant="primary", id="send_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.dismiss(None)
        elif event.button.id == "send_btn":
            to_call = self.query_one("#to_field", Input).value.strip()
            subject = self.query_one("#subject_field", Input).value.strip()
            body = self.query_one("#body_field", TextArea).text.strip()
            if to_call and subject:
                self.dismiss(SendMessageCommand(
                    to_call=to_call, subject=subject, body=body
                ))
