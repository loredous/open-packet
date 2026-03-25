from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, TextArea
from textual.containers import Vertical, Horizontal
from open_packet.engine.commands import PostBulletinCommand


class ComposeBulletinScreen(ModalScreen):
    DEFAULT_CSS = """
    ComposeBulletinScreen {
        align: center middle;
    }
    ComposeBulletinScreen Vertical {
        width: 70;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    ComposeBulletinScreen TextArea {
        height: 10;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("New Bulletin", id="compose_title")
            yield Label("Category:")
            yield Input(placeholder="e.g. WX", id="category_field")
            yield Label("", id="category_error")
            yield Label("Subject:")
            yield Input(placeholder="Subject", id="subject_field")
            yield Label("Body:")
            yield TextArea(id="body_field")
            with Horizontal():
                yield Button("Post", variant="primary", id="post_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.dismiss(None)
        elif event.button.id == "post_btn":
            category = self.query_one("#category_field", Input).value.strip()
            subject = self.query_one("#subject_field", Input).value.strip()
            body = self.query_one("#body_field", TextArea).text.strip()
            if not category:
                self.query_one("#category_error", Label).update("Category is required.")
                return
            self.dismiss(PostBulletinCommand(
                category=category, subject=subject, body=body
            ))
