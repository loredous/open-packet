# open_packet/ui/tui/screens/manage_interfaces.py
from __future__ import annotations
from typing import Optional
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from textual.containers import Vertical, Horizontal, VerticalScroll
from open_packet.store.database import Database
from open_packet.store.models import Interface


class InterfaceManageScreen(ModalScreen):
    DEFAULT_CSS = """
    InterfaceManageScreen {
        align: center middle;
    }
    InterfaceManageScreen > Vertical {
        width: 70;
        height: auto;
        max-height: 80%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    InterfaceManageScreen VerticalScroll {
        height: auto;
        max-height: 20;
    }
    InterfaceManageScreen .row {
        height: 3;
    }
    InterfaceManageScreen .row-label {
        width: 1fr;
        content-align: left middle;
    }
    InterfaceManageScreen .row Button {
        width: auto;
        min-width: 10;
        margin: 0 0 0 1;
    }
    InterfaceManageScreen .footer-row {
        height: 3;
        margin-top: 1;
        align: right middle;
    }
    InterfaceManageScreen .footer-row Button {
        width: auto;
        min-width: 10;
        margin: 0 0 0 1;
    }
    """

    def __init__(self, db: Database, **kwargs):
        super().__init__(**kwargs)
        self._db = db
        self._needs_restart = False

    def compose(self) -> ComposeResult:
        interfaces = self._db.list_interfaces()
        with Vertical():
            yield Label("Interfaces")
            with VerticalScroll(id="iface_list"):
                if interfaces:
                    for iface in interfaces:
                        summary = f"{iface.label}  [{iface.iface_type}]"
                        if iface.host:
                            summary += f"  {iface.host}:{iface.port}"
                        elif iface.device:
                            summary += f"  {iface.device}"
                        with Horizontal(classes="row", id=f"row_{iface.id}"):
                            yield Label(summary, classes="row-label")
                            yield Button("Edit", id=f"edit_{iface.id}")
                            yield Button("Delete", id=f"delete_{iface.id}",
                                         variant="error")
                else:
                    yield Label("No interfaces configured.")
            with Horizontal(classes="footer-row"):
                yield Button("Add New", id="add_btn", variant="primary")
                yield Button("Close", id="close_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "add_btn":
            from open_packet.ui.tui.screens.setup_interface import InterfaceSetupScreen
            self.app.push_screen(InterfaceSetupScreen(), callback=self._on_add)
        elif btn_id == "close_btn":
            self.dismiss(self._needs_restart)
        elif btn_id.startswith("edit_"):
            iface_id = int(btn_id.split("_")[-1])
            self._edit(iface_id)
        elif btn_id.startswith("delete_"):
            iface_id = int(btn_id.split("_")[-1])
            try:
                self._db.delete_interface(iface_id)
            except ValueError as e:
                self.app.notify(str(e), severity="error")
                return
            self._needs_restart = True
            self.call_later(self.recompose)

    def _edit(self, iface_id: int) -> None:
        iface = self._db.get_interface(iface_id)
        if iface:
            from open_packet.ui.tui.screens.setup_interface import InterfaceSetupScreen
            self.app.push_screen(
                InterfaceSetupScreen(iface),
                callback=lambda result: self._on_edit(result),
            )

    def _on_add(self, result: Optional[Interface]) -> None:
        if result is None:
            return
        self._db.insert_interface(result)
        self._needs_restart = True
        self.recompose()

    def _on_edit(self, result: Optional[Interface]) -> None:
        if result is None:
            return
        self._db.update_interface(result)
        self._needs_restart = True
        self.recompose()

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(self._needs_restart)
