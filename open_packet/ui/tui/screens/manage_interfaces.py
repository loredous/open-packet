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
        width: 90%;
        height: auto;
        max-height: 90%;
        overflow-y: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    InterfaceManageScreen VerticalScroll {
        height: auto;
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
            self._confirm_delete(iface_id)

    def _confirm_delete(self, iface_id: int) -> None:
        iface = self._db.get_interface(iface_id)
        if iface is None:
            return
        node_count = self._db._conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE interface_id=? AND deleted=0", (iface_id,)
        ).fetchone()[0]
        if node_count > 0:
            self.app.notify(
                f"Cannot delete: {node_count} node(s) still use this interface.",
                severity="error",
            )
            return
        body = f"Delete interface \"{iface.label}\"? This cannot be undone."
        from open_packet.ui.tui.screens.delete_confirm import DeleteConfirmScreen
        self.app.push_screen(
            DeleteConfirmScreen(f"Delete {iface.label}?", body),
            callback=lambda confirmed, iid=iface_id: self._on_delete_confirmed(confirmed, iid),
        )

    def _on_delete_confirmed(self, confirmed: bool, iface_id: int) -> None:
        if not confirmed:
            return
        self._db.soft_delete_interface(iface_id)
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
