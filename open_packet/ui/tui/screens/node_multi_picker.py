from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Label
from textual.containers import Vertical, Horizontal, VerticalScroll
from open_packet.store.models import Node


class NodeMultiPickerScreen(ModalScreen):
    """Modal screen for selecting one or more nodes.

    Dismisses with a list[int] of selected node IDs, or None if cancelled.
    Requires at least one selection to confirm.
    """

    DEFAULT_CSS = """
    NodeMultiPickerScreen {
        align: center middle;
    }
    NodeMultiPickerScreen > Vertical {
        width: 80%;
        height: auto;
        max-height: 80%;
        overflow-y: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    NodeMultiPickerScreen VerticalScroll {
        height: auto;
        max-height: 20;
    }
    NodeMultiPickerScreen .error-label {
        color: $error;
        height: 1;
    }
    NodeMultiPickerScreen .footer-row {
        height: 3;
        margin-top: 1;
        align: right middle;
    }
    NodeMultiPickerScreen .footer-row Button {
        width: auto;
        min-width: 12;
        margin: 0 0 0 1;
    }
    """

    def __init__(self, nodes: list[Node], title: str = "Select Node(s)", **kwargs):
        super().__init__(**kwargs)
        self._node_list = nodes
        self._title = title

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title)
            with VerticalScroll():
                for node in self._node_list:
                    label_text = f"{node.label}  ({node.callsign}-{node.ssid})"
                    yield Checkbox(label_text, id=f"node_{node.id}", value=False)
            yield Label("", id="error_label", classes="error-label")
            with Horizontal(classes="footer-row"):
                yield Button("Confirm", variant="primary", id="confirm_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.dismiss(None)
        elif event.button.id == "confirm_btn":
            selected = [
                node.id
                for node in self._node_list
                if node.id is not None
                and self.query_one(f"#node_{node.id}", Checkbox).value
            ]
            if not selected:
                self.query_one("#error_label", Label).update("Please select at least one node.")
                return
            self.dismiss(selected)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
