from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Tree
from textual.containers import Vertical

from open_packet.forms.loader import FormDefinition


class FormPickerScreen(ModalScreen):
    DEFAULT_CSS = """
    FormPickerScreen {
        align: center middle;
    }
    FormPickerScreen Vertical {
        width: 90%;
        height: auto;
        max-height: 90%;
        overflow-y: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    FormPickerScreen Tree {
        height: auto;
    }
    """

    def __init__(self, forms: list[FormDefinition], **kwargs):
        super().__init__(**kwargs)
        self._forms = forms

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Select a Form", id="picker_title")
            if not self._forms:
                yield Label(
                    "No forms found. Create .yaml files in\n"
                    "~/.config/open-packet/forms/"
                )
                yield Button("Close", id="close_btn")
                return

            tree: Tree[FormDefinition] = Tree("Forms", id="form_tree")
            tree.root.expand()

            categories: dict[str, list[FormDefinition]] = {}
            for form in self._forms:
                categories.setdefault(form.category, []).append(form)

            for category in sorted(categories):
                cat_node = tree.root.add(category, expand=True)
                for form in sorted(categories[category], key=lambda f: f.name):
                    cat_node.add_leaf(form.name, data=form)

            yield tree
            yield Button("Cancel", id="cancel_btn")

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        if event.node.data is not None:
            self.dismiss(event.node.data)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
