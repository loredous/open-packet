from __future__ import annotations
from typing import Optional
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label
from textual.containers import Vertical, Horizontal, VerticalScroll
from open_packet.store.database import Database
from open_packet.store.models import Node, NodeGroup


class NodeGroupSetupScreen(ModalScreen):
    """Screen for creating or editing a node group."""

    DEFAULT_CSS = """
    NodeGroupSetupScreen {
        align: center middle;
    }
    NodeGroupSetupScreen > Vertical {
        width: 70%;
        height: auto;
        max-height: 90%;
        overflow-y: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    NodeGroupSetupScreen .error {
        color: $error;
        height: 1;
    }
    NodeGroupSetupScreen .node-row {
        height: 3;
    }
    NodeGroupSetupScreen .footer-row {
        height: 3;
        margin-top: 1;
        align: right middle;
    }
    NodeGroupSetupScreen .footer-row Button {
        width: auto;
        min-width: 12;
        margin: 0 0 0 1;
    }
    """

    def __init__(
        self,
        db: Database,
        group: Optional[NodeGroup] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._db = db
        self._group = group

    def compose(self) -> ComposeResult:
        nodes = self._db.list_nodes()
        group = self._group
        title = "Edit Node Group" if group else "New Node Group"
        selected_ids = set(group.node_ids) if group else set()

        with Vertical():
            yield Label(title)
            yield Label("Group Name:")
            yield Input(
                placeholder="e.g. Morning Check-in",
                id="name_field",
                value=group.name if group else "",
            )
            yield Label("", id="name_error", classes="error")

            yield Label("Nodes (checked nodes will be synced in order):")
            with VerticalScroll(id="node_checkboxes"):
                if nodes:
                    for node in nodes:
                        label = f"{node.callsign}-{node.ssid}  \"{node.label}\""
                        yield Checkbox(
                            label,
                            value=(node.id in selected_ids),
                            id=f"node_{node.id}",
                        )
                else:
                    yield Label("No nodes configured.")
            yield Label("", id="nodes_error", classes="error")

            with Horizontal(classes="footer-row"):
                yield Button("Save", variant="primary", id="save_btn")
                yield Button("Cancel", id="cancel_btn")

    def _validate(self) -> bool:
        valid = True
        name = self.query_one("#name_field", Input).value.strip()
        if not name:
            self.query_one("#name_error", Label).update("Group name is required")
            valid = False
        else:
            self.query_one("#name_error", Label).update("")

        selected = self._get_selected_node_ids()
        if len(selected) < 2:
            self.query_one("#nodes_error", Label).update("Select at least 2 nodes")
            valid = False
        else:
            self.query_one("#nodes_error", Label).update("")

        return valid

    def _get_selected_node_ids(self) -> list[int]:
        """Return IDs of checked nodes in their original order."""
        nodes = self._db.list_nodes()
        selected = []
        for node in nodes:
            try:
                cb = self.query_one(f"#node_{node.id}", Checkbox)
                if cb.value:
                    selected.append(node.id)
            except Exception:
                pass
        return selected

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.dismiss(None)
        elif event.button.id == "save_btn":
            if not self._validate():
                return
            name = self.query_one("#name_field", Input).value.strip()
            node_ids = self._get_selected_node_ids()
            group = NodeGroup(
                id=self._group.id if self._group else None,
                name=name,
                node_ids=node_ids,
            )
            self.dismiss(group)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
