# open_packet/ui/tui/widgets/folder_tree.py
from __future__ import annotations
from rich.style import Style
from rich.text import Text
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
        self._inbox_node  = self.root.add_leaf("Inbox",  data="Inbox")
        self._outbox_node = self.root.add_leaf("Outbox", data="Outbox")
        self._sent_node   = self.root.add_leaf("Sent",   data="Sent")
        bulletins = self.root.add("Bulletins", data="Bulletins")
        bulletins.add_leaf("WX",  data="WX")
        bulletins.add_leaf("NTS", data="NTS")
        bulletins.add_leaf("ALL", data="ALL")

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        folder = event.node.data or str(event.node.label)
        parent = event.node.parent
        if parent and parent.data == "Bulletins":
            self.post_message(self.FolderSelected("Bulletins", category=folder))
        else:
            self.post_message(self.FolderSelected(folder))

    def update_counts(self, stats: dict[str, tuple[int, ...]]) -> None:
        if not hasattr(self, "_inbox_node"):
            return  # called before on_mount(); nodes not yet created
        inbox_total, inbox_unread = stats.get("Inbox", (0, 0))
        (sent_total,) = stats.get("Sent", (0,))
        (outbox_count,) = stats.get("Outbox", (0,))

        if inbox_total == 0:
            self._inbox_node.set_label("Inbox")
        elif inbox_unread == 0:
            self._inbox_node.set_label(f"Inbox ({inbox_total})")
        else:
            self._inbox_node.set_label(
                Text.assemble("Inbox (", str(inbox_total), "/", (str(inbox_unread), "bold"), ")")
            )

        if outbox_count > 0:
            self._outbox_node.set_label(
                Text(f"Outbox ({outbox_count})", style=Style(bgcolor="dark_goldenrod"))
            )
        else:
            self._outbox_node.set_label(Text("Outbox", style=Style()))

        self._sent_node.set_label(f"Sent ({sent_total})" if sent_total > 0 else "Sent")
