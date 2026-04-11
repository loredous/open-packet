from __future__ import annotations
from pathlib import Path
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, TextArea, Select
from textual.containers import Vertical, Horizontal
from open_packet.engine.commands import SendMessageCommand
from open_packet.winlink.message import validate_winlink_address, normalize_winlink_address

_MSG_TYPES = [("BBS", "bbs"), ("Winlink", "winlink")]


class ComposeScreen(ModalScreen):
    DEFAULT_CSS = """
    ComposeScreen {
        align: center middle;
    }
    ComposeScreen Vertical {
        width: 90%;
        height: auto;
        max-height: 90%;
        overflow-y: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    ComposeScreen TextArea {
        height: 10;
    }
    ComposeScreen .error {
        color: $error;
        height: 1;
    }
    """

    def __init__(self, to_call: str = "", subject: str = "", body: str = "",
                 default_type: str = "bbs", **kwargs):
        super().__init__(**kwargs)
        self._to_call = to_call
        self._subject = subject
        self._body = body
        self._default_type = default_type

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("New Message", id="compose_title")
            yield Label("Message Type:")
            yield Select(_MSG_TYPES, value=self._default_type, id="msg_type_select")
            yield Label("To:")
            yield Input(value=self._to_call, placeholder="Callsign (or CALLSIGN@domain for Winlink)",
                        id="to_field")
            yield Label("", id="to_error", classes="error")
            yield Label("Subject:")
            yield Input(value=self._subject, placeholder="Subject", id="subject_field")
            yield Label("Body:")
            yield TextArea(self._body, id="body_field")
            with Horizontal():
                yield Button("Send", variant="primary", id="send_btn")
                yield Button("Use Form", id="use_form_btn")
                yield Button("Cancel", id="cancel_btn")

    def _msg_type(self) -> str:
        v = self.query_one("#msg_type_select", Select).value
        return str(v) if v and v != Select.BLANK else "bbs"

    def _validate_to(self, to_call: str) -> str | None:
        """Validate the To field. Returns an error message or None if valid."""
        if not to_call:
            return "Recipient is required"
        msg_type = self._msg_type()
        if msg_type == "winlink":
            if not validate_winlink_address(to_call):
                return "Invalid Winlink address (use CALLSIGN or CALLSIGN@domain)"
        return None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.dismiss(None)
        elif event.button.id == "send_btn":
            to_call = self.query_one("#to_field", Input).value.strip()
            subject = self.query_one("#subject_field", Input).value.strip()
            body = self.query_one("#body_field", TextArea).text.strip()
            msg_type = self._msg_type()

            err = self._validate_to(to_call)
            if err:
                self.query_one("#to_error", Label).update(err)
                return
            self.query_one("#to_error", Label).update("")

            if not subject:
                return

            # Normalize Winlink addresses (append @winlink.org if no domain)
            if msg_type == "winlink":
                to_call = normalize_winlink_address(to_call)

            self.dismiss(SendMessageCommand(
                to_call=to_call, subject=subject, body=body,
                message_type=msg_type,
            ))
        elif event.button.id == "use_form_btn":
            from open_packet.forms.loader import discover_forms
            from open_packet.ui.tui.screens.form_picker import FormPickerScreen
            forms_dir = getattr(self.app, "forms_dir", Path.home() / ".config/open-packet/forms")
            forms = discover_forms(forms_dir)
            self.app.push_screen(FormPickerScreen(forms), callback=self._on_form_picked)

    def _on_form_picked(self, form_def) -> None:
        if form_def is None:
            return
        from open_packet.ui.tui.screens.form_fill import FormFillScreen
        self.app.push_screen(FormFillScreen(form_def), callback=self._on_form_filled)

    def _on_form_filled(self, result) -> None:
        if result is None:
            return
        subject, body = result
        self.query_one("#subject_field", Input).value = subject
        self.query_one("#body_field", TextArea).load_text(body)
