from __future__ import annotations
from typing import Optional
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from textual.containers import Vertical, Horizontal, VerticalScroll
from open_packet.store.database import Database
from open_packet.store.models import Node


class NodePickerScreen(ModalScreen):
    DEFAULT_CSS = """
    NodePickerScreen {
        align: center middle;
    }
    NodePickerScreen > Vertical {
        width: 60;
        height: auto;
        max-height: 80%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    NodePickerScreen VerticalScroll {
        height: auto;
        max-height: 20;
    }
    NodePickerScreen .row {
        height: 3;
    }
    NodePickerScreen .row-label {
        width: 1fr;
        content-align: left middle;
    }
    NodePickerScreen .row Button {
        width: auto;
        min-width: 12;
        margin: 0 0 0 1;
    }
    NodePickerScreen .footer-row {
        height: 3;
        margin-top: 1;
        align: right middle;
    }
    NodePickerScreen .footer-row Button {
        width: auto;
        min-width: 12;
        margin: 0 0 0 1;
    }
    """

    def __init__(self, db: Database, **kwargs):
        super().__init__(**kwargs)
        self._db = db

    def compose(self) -> ComposeResult:
        nodes = self._db.list_nodes()
        with Vertical():
            yield Label("Select Node")
            with VerticalScroll():
                if nodes:
                    for node in nodes:
                        label_text = f"{node.callsign}-{node.ssid}  \"{node.label}\""
                        with Horizontal(classes="row"):
                            yield Label(label_text, classes="row-label")
                            yield Button("Select", id=f"select_{node.id}", variant="primary")
                else:
                    yield Label("No nodes configured.")
            with Horizontal(classes="footer-row"):
                yield Button("Add New", id="add_btn", variant="primary")
                yield Button("Close", id="close_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "close_btn":
            self.dismiss(False)
        elif btn_id == "add_btn":
            from open_packet.ui.tui.screens.setup_node import NodeSetupScreen
            self.app.push_screen(
                NodeSetupScreen(interfaces=self._db.list_interfaces(), db=self._db),
                callback=self._on_add,
            )
        elif btn_id.startswith("select_"):
            node_id = int(btn_id.split("_")[-1])
            self._select(node_id)

    def _select(self, node_id: int) -> None:
        self._db.clear_default_node()
        node = self._db.get_node(node_id)
        if node:
            node.is_default = True
            self._db.update_node(node)
        self.dismiss(True)

    def _on_add(self, result: Optional[Node]) -> None:
        if result is None:
            return
        if result.is_default:
            self._db.clear_default_node()
        self._db.insert_node(result)
        self.call_later(self.recompose)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)
