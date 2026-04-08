from __future__ import annotations
from datetime import datetime
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, TextArea
from textual.containers import Horizontal, Vertical

from open_packet.forms.loader import FormDefinition
from open_packet.forms.renderer import FormRenderError, render
from open_packet.forms.validator import validate_form


class _BypassConfirmScreen(ModalScreen):
    DEFAULT_CSS = """
    _BypassConfirmScreen { align: center middle; }
    _BypassConfirmScreen Vertical {
        width: 50; height: auto; border: solid $warning;
        background: $surface; padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[b]Warning:[/b] Some fields have validation errors.")
            yield Label("Submit anyway?")
            with Horizontal():
                yield Button("Submit Anyway", variant="warning", id="confirm_btn")
                yield Button("Go Back", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm_btn")

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)


class FormFillScreen(ModalScreen):
    DEFAULT_CSS = """
    FormFillScreen {
        align: center middle;
    }
    FormFillScreen Vertical {
        width: 70;
        height: auto;
        max-height: 40;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    FormFillScreen TextArea {
        height: 6;
    }
    FormFillScreen .field-desc {
        color: $text-muted;
    }
    FormFillScreen .field-error {
        color: $error;
    }
    """

    def __init__(self, form: FormDefinition, **kwargs):
        super().__init__(**kwargs)
        self._form = form

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"[b]{self._form.name}[/b]", id="form_title")
            for f in self._form.fields:
                yield Label(f.label)
                if f.description:
                    yield Label(f.description, classes="field-desc")
                if f.choices:
                    opts = [(c, c) for c in f.choices]
                    yield Select(opts, allow_blank=True, id=f"field_{f.name}")
                elif f.type == "textarea":
                    yield TextArea(id=f"field_{f.name}")
                else:
                    initial = ""
                    if f.type == "datetime" and f.auto_populate and f.format:
                        initial = datetime.now().strftime(f.format)
                    yield Input(value=initial, id=f"field_{f.name}")
                yield Label("", id=f"error_{f.name}", classes="field-error")
            yield Label("", id="render_error", classes="field-error")
            with Horizontal():
                yield Button("Submit", variant="primary", id="submit_btn")
                yield Button("Submit Anyway", id="bypass_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_mount(self) -> None:
        self._run_validation()

    def _get_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for f in self._form.fields:
            fid = f"#field_{f.name}"
            if f.choices:
                widget = self.query_one(fid, Select)
                val = widget.value
                values[f.name] = "" if val is Select.BLANK else str(val)
            elif f.type == "textarea":
                values[f.name] = self.query_one(fid, TextArea).text
            else:
                values[f.name] = self.query_one(fid, Input).value
        return values

    def _run_validation(self) -> bool:
        values = self._get_values()
        errors = validate_form(self._form, values)
        has_errors = False
        for f in self._form.fields:
            field_errors = errors.get(f.name, [])
            self.query_one(f"#error_{f.name}", Label).update(
                field_errors[0] if field_errors else ""
            )
            if field_errors:
                has_errors = True
        self.query_one("#submit_btn", Button).disabled = has_errors
        return not has_errors

    def on_input_changed(self, event: Input.Changed) -> None:
        self._run_validation()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self._run_validation()

    def on_select_changed(self, event: Select.Changed) -> None:
        self._run_validation()

    def _do_submit(self) -> None:
        values = self._get_values()
        try:
            subject, body = render(self._form, values)
            self.dismiss((subject, body))
        except FormRenderError as e:
            self.query_one("#render_error", Label).update(f"Template error: {e}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.dismiss(None)
        elif event.button.id == "submit_btn":
            if self._run_validation():
                self._do_submit()
        elif event.button.id == "bypass_btn":
            self.app.push_screen(_BypassConfirmScreen(), callback=self._on_bypass_confirmed)

    def _on_bypass_confirmed(self, confirmed: bool) -> None:
        if confirmed:
            self._do_submit()

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
