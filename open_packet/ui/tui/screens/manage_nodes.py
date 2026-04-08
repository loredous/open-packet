from __future__ import annotations
from typing import Optional
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from textual.containers import Vertical, Horizontal, VerticalScroll
from open_packet.store.database import Database
from open_packet.store.models import Node


class NodeManageScreen(ModalScreen):
    DEFAULT_CSS = """
    NodeManageScreen {
        align: center middle;
    }
    NodeManageScreen > Vertical {
        width: 90%;
        height: auto;
        max-height: 90%;
        overflow-y: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    NodeManageScreen VerticalScroll {
        height: auto;
    }
    NodeManageScreen .row {
        height: 3;
    }
    NodeManageScreen .row-label {
        width: 1fr;
        content-align: left middle;
    }
    NodeManageScreen .active-badge {
        color: $success;
        width: auto;
        content-align: center middle;
        margin: 0 1;
    }
    NodeManageScreen .row Button {
        width: auto;
        min-width: 12;
        margin: 0 0 0 1;
    }
    NodeManageScreen .footer-row {
        height: 3;
        margin-top: 1;
        align: right middle;
    }
    NodeManageScreen .footer-row Button {
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
        nodes = self._db.list_nodes()
        with Vertical():
            yield Label("Nodes")
            with VerticalScroll(id="node_list"):
                if nodes:
                    for node in nodes:
                        label_text = f"{node.callsign}-{node.ssid}  \"{node.label}\""
                        with Horizontal(classes="row", id=f"row_{node.id}"):
                            yield Label(label_text, classes="row-label")
                            if node.is_default:
                                yield Label("★ Active", classes="active-badge")
                            else:
                                yield Button("Set Active", id=f"set_active_{node.id}")
                            yield Button("Edit", id=f"edit_{node.id}")
                            if not node.is_default:
                                yield Button("Delete", id=f"delete_{node.id}", variant="error")
                else:
                    yield Label("No nodes configured.")
            with Horizontal(classes="footer-row"):
                yield Button("Add New", id="add_btn", variant="primary")
                yield Button("Close", id="close_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "add_btn":
            from open_packet.ui.tui.screens.setup_node import NodeSetupScreen
            self.app.push_screen(
                NodeSetupScreen(interfaces=self._db.list_interfaces(), db=self._db),
                callback=self._on_add,
            )
        elif btn_id == "close_btn":
            self.dismiss(self._needs_restart)
        elif btn_id.startswith("set_active_"):
            node_id = int(btn_id.split("_")[-1])
            self._set_active(node_id)
        elif btn_id.startswith("edit_"):
            node_id = int(btn_id.split("_")[-1])
            self._edit(node_id)
        elif btn_id.startswith("delete_"):
            node_id = int(btn_id.split("_")[-1])
            self._confirm_delete(node_id)

    def _set_active(self, node_id: int) -> None:
        self._db.clear_default_node()
        node = self._db.get_node(node_id)
        if node:
            node.is_default = True
            self._db.update_node(node)
        self._needs_restart = True
        self.call_later(self.recompose)

    def _edit(self, node_id: int) -> None:
        node = self._db.get_node(node_id)
        if node:
            from open_packet.ui.tui.screens.setup_node import NodeSetupScreen
            self.app.push_screen(
                NodeSetupScreen(node, interfaces=self._db.list_interfaces(), db=self._db),
                callback=lambda result: self._on_edit(result),
            )

    def _confirm_delete(self, node_id: int) -> None:
        node = self._db.get_node(node_id)
        if node is None:
            return
        messages, bulletins = self._db.count_node_dependents(node_id)
        label = node.label
        body = (
            f"Deleting {label} will hide {messages} message(s) and "
            f"{bulletins} bulletin(s). This cannot be undone."
        )
        from open_packet.ui.tui.screens.delete_confirm import DeleteConfirmScreen
        self.app.push_screen(
            DeleteConfirmScreen(f"Delete {label}?", body),
            callback=lambda confirmed, nid=node_id: self._on_delete_confirmed(confirmed, nid),
        )

    def _on_delete_confirmed(self, confirmed: bool, node_id: int) -> None:
        if not confirmed:
            return
        self._db.soft_delete_node(node_id)
        self._needs_restart = True
        self.call_later(self.recompose)

    def _on_add(self, result: Optional[Node]) -> None:
        if result is None:
            return
        if result.is_default:
            self._db.clear_default_node()
        self._db.insert_node(result)
        self._needs_restart = True
        self.recompose()

    def _on_edit(self, result: Optional[Node]) -> None:
        if result is None:
            return
        if result.is_default:
            self._db.clear_default_node()
        self._db.update_node(result)
        self._needs_restart = True
        self.recompose()

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(self._needs_restart)
