from __future__ import annotations
from textual.app import ComposeResult
from textual.binding import Binding
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
        width: 90%;
        height: auto;
        max-height: 90%;
        overflow-y: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    ComposeBulletinScreen TextArea {
        height: 10;
    }
    """

    BINDINGS = [
        Binding("ctrl+s", "submit", "Post", priority=True),
        Binding("escape", "cancel", "Cancel"),
    ]

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

    def action_submit(self) -> None:
        category = self.query_one("#category_field", Input).value.strip()
        subject = self.query_one("#subject_field", Input).value.strip()
        body = self.query_one("#body_field", TextArea).text.strip()
        if not category:
            self.query_one("#category_error", Label).update("Category is required.")
            return
        self.dismiss(PostBulletinCommand(
            category=category, subject=subject, body=body
        ))

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.action_cancel()
        elif event.button.id == "post_btn":
            self.action_submit()
