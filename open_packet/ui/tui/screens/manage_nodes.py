from __future__ import annotations
from typing import Optional
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from textual.containers import Vertical, Horizontal, VerticalScroll
from open_packet.store.database import Database
from open_packet.store.models import Node, NodeGroup


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
    NodeManageScreen .section-header {
        margin-top: 1;
        color: $accent;
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
        groups = self._db.list_node_groups()

        with Vertical():
            # --- Individual Nodes section ---
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

            with Horizontal(id="node_footer", classes="footer-row"):
                yield Button("Add Node", id="add_btn", variant="primary")

            # --- Node Groups section ---
            yield Label("Node Groups", classes="section-header")
            with VerticalScroll(id="group_list"):
                if groups:
                    node_map = {n.id: n.label for n in nodes}
                    for group in groups:
                        member_labels = ", ".join(
                            node_map.get(nid, f"#{nid}") for nid in group.node_ids
                        )
                        label_text = f"{group.name}  [{member_labels}]"
                        with Horizontal(classes="row", id=f"group_row_{group.id}"):
                            yield Label(label_text, classes="row-label")
                            yield Button("Sync", id=f"sync_group_{group.id}")
                            yield Button("Edit", id=f"edit_group_{group.id}")
                            yield Button("Delete", id=f"delete_group_{group.id}", variant="error")
                else:
                    yield Label("No node groups configured.")

            with Horizontal(classes="footer-row"):
                yield Button("Add Group", id="add_group_btn", variant="primary")
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
        elif btn_id == "add_group_btn":
            self._add_group()
        elif btn_id.startswith("set_active_"):
            node_id = int(btn_id.split("_")[-1])
            self._set_active(node_id)
        elif btn_id.startswith("edit_") and not btn_id.startswith("edit_group_"):
            node_id = int(btn_id.split("_")[-1])
            self._edit(node_id)
        elif btn_id.startswith("delete_") and not btn_id.startswith("delete_group_"):
            node_id = int(btn_id.split("_")[-1])
            self._confirm_delete(node_id)
        elif btn_id.startswith("edit_group_"):
            group_id = int(btn_id.split("_")[-1])
            self._edit_group(group_id)
        elif btn_id.startswith("delete_group_"):
            group_id = int(btn_id.split("_")[-1])
            self._confirm_delete_group(group_id)
        elif btn_id.startswith("sync_group_"):
            group_id = int(btn_id.split("_")[-1])
            self._sync_group(group_id)

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

    # --- Group management ---

    def _add_group(self) -> None:
        from open_packet.ui.tui.screens.setup_node_group import NodeGroupSetupScreen
        self.app.push_screen(
            NodeGroupSetupScreen(db=self._db),
            callback=self._on_add_group,
        )

    def _on_add_group(self, result: Optional[NodeGroup]) -> None:
        if result is None:
            return
        self._db.insert_node_group(result)
        self.recompose()

    def _edit_group(self, group_id: int) -> None:
        group = self._db.get_node_group(group_id)
        if group is None:
            return
        from open_packet.ui.tui.screens.setup_node_group import NodeGroupSetupScreen
        self.app.push_screen(
            NodeGroupSetupScreen(db=self._db, group=group),
            callback=lambda result: self._on_edit_group(result),
        )

    def _on_edit_group(self, result: Optional[NodeGroup]) -> None:
        if result is None:
            return
        self._db.update_node_group(result)
        self.recompose()

    def _confirm_delete_group(self, group_id: int) -> None:
        group = self._db.get_node_group(group_id)
        if group is None:
            return
        from open_packet.ui.tui.screens.delete_confirm import DeleteConfirmScreen
        self.app.push_screen(
            DeleteConfirmScreen(
                f"Delete group \"{group.name}\"?",
                "This will remove the group configuration. Node records are not affected.",
            ),
            callback=lambda confirmed, gid=group_id: self._on_delete_group_confirmed(confirmed, gid),
        )

    def _on_delete_group_confirmed(self, confirmed: bool, group_id: int) -> None:
        if not confirmed:
            return
        self._db.soft_delete_node_group(group_id)
        self.recompose()

    def _sync_group(self, group_id: int) -> None:
        """Trigger a group sync via the app."""
        self.dismiss(self._needs_restart)
        self.app.call_after_refresh(
            lambda: self.app.sync_node_group(group_id)
        )

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(self._needs_restart)
