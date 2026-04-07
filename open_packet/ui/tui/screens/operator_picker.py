from __future__ import annotations
from typing import Optional
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from textual.containers import Vertical, Horizontal, VerticalScroll
from open_packet.store.database import Database
from open_packet.store.models import Operator


class OperatorPickerScreen(ModalScreen):
    DEFAULT_CSS = """
    OperatorPickerScreen {
        align: center middle;
    }
    OperatorPickerScreen > Vertical {
        width: 60;
        height: auto;
        max-height: 80%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    OperatorPickerScreen VerticalScroll {
        height: auto;
        max-height: 20;
    }
    OperatorPickerScreen .row {
        height: 3;
    }
    OperatorPickerScreen .row-label {
        width: 1fr;
        content-align: left middle;
    }
    OperatorPickerScreen .row Button {
        width: auto;
        min-width: 12;
        margin: 0 0 0 1;
    }
    OperatorPickerScreen .footer-row {
        height: 3;
        margin-top: 1;
        align: right middle;
    }
    OperatorPickerScreen .footer-row Button {
        width: auto;
        min-width: 12;
        margin: 0 0 0 1;
    }
    """

    def __init__(self, db: Database, **kwargs):
        super().__init__(**kwargs)
        self._db = db

    def compose(self) -> ComposeResult:
        operators = self._db.list_operators()
        with Vertical():
            yield Label("Select Operator")
            with VerticalScroll():
                if operators:
                    for op in operators:
                        label_text = f"{op.callsign}-{op.ssid}  \"{op.label}\"" if op.ssid != 0 else f"{op.callsign}  \"{op.label}\""
                        with Horizontal(classes="row"):
                            yield Label(label_text, classes="row-label")
                            yield Button("Select", id=f"select_{op.id}", variant="primary")
                else:
                    yield Label("No operators configured.")
            with Horizontal(classes="footer-row"):
                yield Button("Add New", id="add_btn", variant="primary")
                yield Button("Close", id="close_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "close_btn":
            self.dismiss(False)
        elif btn_id == "add_btn":
            from open_packet.ui.tui.screens.setup_operator import OperatorSetupScreen
            self.app.push_screen(OperatorSetupScreen(), callback=self._on_add)
        elif btn_id.startswith("select_"):
            op_id = int(btn_id.split("_")[-1])
            self._select(op_id)

    def _select(self, op_id: int) -> None:
        self._db.clear_default_operator()
        op = self._db.get_operator(op_id)
        if op:
            op.is_default = True
            self._db.update_operator(op)
        self.dismiss(True)

    def _on_add(self, result: Optional[Operator]) -> None:
        if result is None:
            return
        if result.is_default:
            self._db.clear_default_operator()
        self._db.insert_operator(result)
        self.call_later(self.recompose)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)
