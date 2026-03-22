# open_packet/ui/tui/widgets/folder_tree.py
from __future__ import annotations
from textual.widgets import Tree
from textual.widgets.tree import TreeNode
from textual.message import Message as TMessage


class FolderTree(Tree):
    DEFAULT_CSS = """
    FolderTree {
        width: 18;
        border-right: solid $primary;
    }
    """

    class FolderSelected(TMessage):
        def __init__(self, folder: str, category: str = "") -> None:
            self.folder = folder
            self.category = category
            super().__init__()

    def on_mount(self) -> None:
        self.root.expand()
        self.root.add_leaf("Inbox")
        self.root.add_leaf("Sent")
        bulletins = self.root.add("Bulletins")
        bulletins.add_leaf("WX")
        bulletins.add_leaf("NTS")
        bulletins.add_leaf("ALL")

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        label = str(event.node.label)
        parent = event.node.parent
        if parent and str(parent.label) == "Bulletins":
            self.post_message(self.FolderSelected("Bulletins", category=label))
        else:
            self.post_message(self.FolderSelected(label))
