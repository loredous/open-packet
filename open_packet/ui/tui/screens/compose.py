from __future__ import annotations
from pathlib import Path
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
    """

    def __init__(self, to_call: str = "", subject: str = "", body: str = "", **kwargs):
        super().__init__(**kwargs)
        self._to_call = to_call
        self._subject = subject
        self._body = body

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("New Message", id="compose_title")
            yield Label("To:")
            yield Input(value=self._to_call, placeholder="Callsign", id="to_field")
            yield Label("Subject:")
            yield Input(value=self._subject, placeholder="Subject", id="subject_field")
            yield Label("Body:")
            yield TextArea(self._body, id="body_field")
            with Horizontal():
                yield Button("Send", variant="primary", id="send_btn")
                yield Button("Use Form", id="use_form_btn")
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
        initial_values, on_field_values = self._nts_form_extras(form_def)
        self.app.push_screen(
            FormFillScreen(form_def, initial_values=initial_values, on_field_values=on_field_values),
            callback=self._on_form_filled,
        )

    def _nts_form_extras(self, form_def) -> tuple[dict, object]:
        """Delegate NTS-specific initial-values/callback to the app if available."""
        app = self.app
        if hasattr(app, "_nts_form_extras"):
            return app._nts_form_extras(form_def)
        return {}, None

    def _on_form_filled(self, result) -> None:
        if result is None:
            return
        subject, body = result
        self.query_one("#subject_field", Input).value = subject
        self.query_one("#body_field", TextArea).load_text(body)
