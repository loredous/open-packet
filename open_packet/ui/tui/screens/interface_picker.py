from __future__ import annotations
from typing import Optional
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from textual.containers import Vertical, Horizontal, VerticalScroll
from open_packet.store.database import Database
from open_packet.store.models import Interface, Node


class InterfacePickerScreen(ModalScreen):
    DEFAULT_CSS = """
    InterfacePickerScreen {
        align: center middle;
    }
    InterfacePickerScreen > Vertical {
        width: 90%;
        height: auto;
        max-height: 90%;
        overflow-y: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    InterfacePickerScreen VerticalScroll {
        height: auto;
    }
    InterfacePickerScreen .row {
        height: 3;
    }
    InterfacePickerScreen .row-label {
        width: 1fr;
        content-align: left middle;
    }
    InterfacePickerScreen .row Button {
        width: auto;
        min-width: 12;
        margin: 0 0 0 1;
    }
    InterfacePickerScreen .footer-row {
        height: 3;
        margin-top: 1;
        align: right middle;
    }
    InterfacePickerScreen .footer-row Button {
        width: auto;
        min-width: 12;
        margin: 0 0 0 1;
    }
    """

    def __init__(self, db: Database, active_node: Node, **kwargs):
        super().__init__(**kwargs)
        self._db = db
        self._active_node = active_node

    def compose(self) -> ComposeResult:
        interfaces = self._db.list_interfaces()
        with Vertical():
            yield Label("Select Interface")
            with VerticalScroll():
                if interfaces:
                    for iface in interfaces:
                        summary = f"{iface.label}  [{iface.iface_type}]"
                        if iface.host:
                            summary += f"  {iface.host}:{iface.port}"
                        elif iface.device:
                            summary += f"  {iface.device}"
                        with Horizontal(classes="row"):
                            yield Label(summary, classes="row-label")
                            yield Button("Select", id=f"select_{iface.id}", variant="primary")
                else:
                    yield Label("No interfaces configured.")
            with Horizontal(classes="footer-row"):
                yield Button("Add New", id="add_btn", variant="primary")
                yield Button("Close", id="close_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "close_btn":
            self.dismiss(False)
        elif btn_id == "add_btn":
            from open_packet.ui.tui.screens.setup_interface import InterfaceSetupScreen
            self.app.push_screen(InterfaceSetupScreen(), callback=self._on_add)
        elif btn_id.startswith("select_"):
            iface_id = int(btn_id.split("_")[-1])
            self._select(iface_id)

    def _select(self, iface_id: int) -> None:
        self._active_node.interface_id = iface_id
        self._db.update_node(self._active_node)
        self.dismiss(True)

    def _on_add(self, result: Optional[Interface]) -> None:
        if result is None:
            return
        self._db.insert_interface(result)
        self.call_later(self.recompose)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)
