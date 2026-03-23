from __future__ import annotations
from typing import Optional
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from textual.containers import Vertical, Horizontal, VerticalScroll
from open_packet.store.database import Database
from open_packet.store.models import Operator


class OperatorManageScreen(ModalScreen):
    DEFAULT_CSS = """
    OperatorManageScreen {
        align: center middle;
    }
    OperatorManageScreen > Vertical {
        width: 60;
        height: auto;
        max-height: 80%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    OperatorManageScreen VerticalScroll {
        height: auto;
        max-height: 20;
    }
    OperatorManageScreen .row {
        height: 3;
    }
    OperatorManageScreen .row-label {
        width: 1fr;
        content-align: left middle;
    }
    OperatorManageScreen .active-badge {
        color: $success;
        width: auto;
        content-align: center middle;
        margin: 0 1;
    }
    OperatorManageScreen .row Button {
        width: auto;
        min-width: 12;
        margin: 0 0 0 1;
    }
    OperatorManageScreen .footer-row {
        height: 3;
        margin-top: 1;
        align: right middle;
    }
    OperatorManageScreen .footer-row Button {
        width: auto;
        min-width: 12;
        margin: 0 0 0 1;
    }
    """

    def __init__(self, db: Database, **kwargs):
        super().__init__(**kwargs)
        self._db = db
        self._needs_restart = False

    def compose(self) -> ComposeResult:
        operators = self._db.list_operators()
        with Vertical():
            yield Label("Operators")
            with VerticalScroll(id="operator_list"):
                if operators:
                    for op in operators:
                        label_text = f"{op.callsign}-{op.ssid}  \"{op.label}\""
                        with Horizontal(classes="row", id=f"row_{op.id}"):
                            yield Label(label_text, classes="row-label")
                            if op.is_default:
                                yield Label("★ Active", classes="active-badge")
                            else:
                                yield Button("Set Active", id=f"set_active_{op.id}")
                            yield Button("Edit", id=f"edit_{op.id}")
                else:
                    yield Label("No operators configured.")
            with Horizontal(classes="footer-row"):
                yield Button("Add New", id="add_btn", variant="primary")
                yield Button("Close", id="close_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "add_btn":
            from open_packet.ui.tui.screens.setup_operator import OperatorSetupScreen
            self.app.push_screen(OperatorSetupScreen(), callback=self._on_add)
        elif btn_id == "close_btn":
            self.dismiss(self._needs_restart)
        elif btn_id.startswith("set_active_"):
            op_id = int(btn_id.split("_")[-1])
            self._set_active(op_id)
        elif btn_id.startswith("edit_"):
            op_id = int(btn_id.split("_")[-1])
            self._edit(op_id)

    def _set_active(self, op_id: int) -> None:
        self._db.clear_default_operator()
        op = self._db.get_operator(op_id)
        if op:
            op.is_default = True
            self._db.update_operator(op)
        self._needs_restart = True
        self.call_later(self.recompose)

    def _edit(self, op_id: int) -> None:
        op = self._db.get_operator(op_id)
        if op:
            from open_packet.ui.tui.screens.setup_operator import OperatorSetupScreen
            self.app.push_screen(OperatorSetupScreen(op),
                                 callback=lambda result: self._on_edit(result))

    def _on_add(self, result: Optional[Operator]) -> None:
        if result is None:
            return
        if result.is_default:
            self._db.clear_default_operator()
        self._db.insert_operator(result)
        self._needs_restart = True
        self.recompose()

    def _on_edit(self, result: Optional[Operator]) -> None:
        if result is None:
            return
        if result.is_default:
            self._db.clear_default_operator()
        self._db.update_operator(result)
        self._needs_restart = True
        self.recompose()

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(self._needs_restart)
