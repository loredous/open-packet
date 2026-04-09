# open_packet/ui/tui/widgets/folder_tree.py
from __future__ import annotations
from rich.style import Style
from rich.text import Text
from textual.widgets import Tree
from textual.widgets.tree import TreeNode
from textual.message import Message as TMessage


def _session_label(session) -> Text:
    if session.status == "connecting":
        prefix, color = "⟳ ", "yellow"
    elif session.status == "connected" and session.has_unread:
        prefix, color = "◉ ", "cyan"
    elif session.status == "connected":
        prefix, color = "● ", "green"
    elif session.status == "error":
        prefix, color = "✕ ", "red"
    else:  # disconnected or unknown
        prefix, color = "○ ", "dim"
    return Text.assemble((prefix, color), session.label)


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

    class SessionSelected(TMessage):
        def __init__(self, session_idx: int) -> None:
            self.session_idx = session_idx
            super().__init__()

    def on_mount(self) -> None:
        self.root.expand()
        self._inbox_node     = self.root.add_leaf("Inbox",  data="Inbox")
        self._outbox_node    = self.root.add_leaf("Outbox", data="Outbox")
        self._sent_node      = self.root.add_leaf("Sent",   data="Sent")
        self._bulletins_node = self.root.add("Bulletins", data="Bulletins")
        self._bulletin_nodes: dict[str, TreeNode] = {}
        self._files_node = self.root.add("Files", data="Files")
        self._file_dir_nodes: dict[str, TreeNode] = {}
        self._sessions_node  = self.root.add("Sessions", data="__sessions__")
        self._session_nodes: list[TreeNode] = []

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data or str(event.node.label)
        if isinstance(data, str) and data.startswith("__session_item_"):
            idx = int(data[len("__session_item_"):-2])
            self.post_message(self.SessionSelected(idx))
            return
        parent = event.node.parent
        if parent and parent.data == "Bulletins":
            self.post_message(self.FolderSelected("Bulletins", category=data))
        elif parent and parent.data == "Files":
            self.post_message(self.FolderSelected("Files", category=data))
        else:
            self.post_message(self.FolderSelected(data))

    def update_counts(self, stats: dict) -> None:
        if not hasattr(self, "_inbox_node"):
            return
        inbox_total, inbox_unread = stats.get("Inbox", (0, 0))
        (sent_total,)  = stats.get("Sent",   (0,))
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

        bulletin_stats: dict[str, tuple[int, int]] = stats.get("Bulletins", {})
        for category, (total, unread) in bulletin_stats.items():
            if category not in self._bulletin_nodes:
                node = self._bulletins_node.add_leaf(category, data=category)
                self._bulletin_nodes[category] = node
            node = self._bulletin_nodes[category]
            if total == 0 and unread == 0:
                node.set_label(category)
            elif unread == 0:
                node.set_label(f"{category} ({total})")
            else:
                node.set_label(f"{category} ({total}/{unread} new)")

        for category in list(self._bulletin_nodes):
            if category not in bulletin_stats:
                self._bulletin_nodes[category].remove()
                del self._bulletin_nodes[category]

        file_stats: dict[str, int] = stats.get("Files", {})
        for directory, count in sorted(file_stats.items()):
            if directory not in self._file_dir_nodes:
                node = self._files_node.add_leaf(directory, data=directory)
                self._file_dir_nodes[directory] = node
            node = self._file_dir_nodes[directory]
            node.set_label(f"{directory} ({count})" if count > 0 else directory)

        for directory in list(self._file_dir_nodes):
            if directory not in file_stats:
                self._file_dir_nodes[directory].remove()
                del self._file_dir_nodes[directory]

        self._recompute_width()

    def update_sessions(self, sessions: list) -> None:
        if not hasattr(self, "_sessions_node"):
            return
        for node in list(self._session_nodes):
            node.remove()
        self._session_nodes.clear()

        for i, session in enumerate(sessions):
            label = _session_label(session)
            node = self._sessions_node.add_leaf(label, data=f"__session_item_{i}__")
            self._session_nodes.append(node)

        if sessions:
            self._sessions_node.expand()

        self._recompute_width()

    def _recompute_width(self) -> None:
        """Set width to fit the longest visible label, clamped to [18, 32].

        Depth-1 nodes (Inbox, Outbox, Sent) get +4 for tree indent.
        Depth-2 nodes (bulletin categories, sessions) get +8.
        """
        def _plain(label) -> str:
            return label.plain if hasattr(label, "plain") else str(label)

        depth1: list[str] = []
        depth2: list[str] = []

        if hasattr(self, "_inbox_node"):
            depth1.append(_plain(self._inbox_node.label))
            depth1.append(_plain(self._outbox_node.label))
            depth1.append(_plain(self._sent_node.label))
            for node in self._bulletin_nodes.values():
                depth2.append(_plain(node.label))
            for node in self._file_dir_nodes.values():
                depth2.append(_plain(node.label))

        if hasattr(self, "_session_nodes"):
            for node in self._session_nodes:
                depth2.append(_plain(node.label))

        max1 = max((len(s) for s in depth1), default=0)
        max2 = max((len(s) for s in depth2), default=0)
        needed = max(max1 + 4, max2 + 8)
        self.styles.width = max(18, min(32, needed))
