# Folder Pane & Message List Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the folder pane dynamically resize between 18–32 columns, clear the unread indicator in-place when a message is selected, and add separate "Sent" and "Retrieved" date columns to the message list.

**Architecture:** Three independent changes: (1) `FolderTree` computes its own width after each label update; (2) `MessageList` gains a `mark_row_read()` method that surgically updates one DataTable cell; (3) `OpenPacketApp` calls `mark_row_read()` after persisting read state. A one-line store fix also ensures `Message._row_to_message` populates `synced_at`, matching the existing `_row_to_bulletin` behaviour.

**Tech Stack:** Python 3.11+, Textual (DataTable, Tree, styles.width), SQLite via existing Store layer, pytest-asyncio.

---

## Task 1: Fix `_row_to_message` to populate `synced_at`

`Bulletin` objects already carry a `synced_at` date retrieved from their DB row; `Message` objects silently drop it. Fix this before wiring up the UI column so the "Retrieved" date appears for messages too.

**Files:**
- Modify: `open_packet/store/store.py`
- Modify: `tests/test_store/test_store.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_store/test_store.py`:

```python
def test_row_to_message_populates_synced_at(tmp_path):
    """Messages retrieved from DB carry synced_at, matching bulletin behaviour."""
    from open_packet.store.database import Database
    from open_packet.store.store import Store
    from open_packet.store.models import Message
    from datetime import datetime, timezone

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    store = Store(db)

    msg = store.save_message(Message(
        operator_id=1, node_id=1, bbs_id="001",
        from_call="W0TEST", to_call="KD9ABC",
        subject="Hello", body="Body",
        timestamp=datetime.now(timezone.utc),
    ))
    assert msg.synced_at is not None, "synced_at must be set on retrieval"
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
uv run pytest tests/test_store/test_store.py::test_row_to_message_populates_synced_at -v
```

Expected: FAIL — `AssertionError: synced_at must be set on retrieval`

- [ ] **Step 3: Fix `_row_to_message` in `open_packet/store/store.py`**

Find `_row_to_message` (around line 196). It currently ends with `queued=bool(row["queued"]),`. Add `synced_at`:

```python
def _row_to_message(self, row) -> Message:
    return Message(
        id=row["id"], operator_id=row["operator_id"], node_id=row["node_id"],
        bbs_id=row["bbs_id"], from_call=row["from_call"], to_call=row["to_call"],
        subject=row["subject"], body=row["body"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        read=bool(row["read"]), sent=bool(row["sent"]), deleted=bool(row["deleted"]),
        queued=bool(row["queued"]),
        synced_at=datetime.fromisoformat(row["synced_at"]) if row["synced_at"] else None,
    )
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
uv run pytest tests/test_store/test_store.py::test_row_to_message_populates_synced_at -v
```

Expected: PASS

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add open_packet/store/store.py tests/test_store/test_store.py
git commit -m "fix: populate synced_at on Message objects retrieved from DB"
```

---

## Task 2: MessageList — dual date columns and `mark_row_read()`

Replace the single "Date" column with "Sent" and "Retrieved", and add a method to clear the unread indicator for a specific row without reloading the table.

**Files:**
- Modify: `open_packet/ui/tui/widgets/message_list.py`
- Modify: `tests/test_ui/test_tui.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ui/test_tui.py` (use the existing `app_config` fixture and DB setup pattern from `test_app_mounts`):

```python
@pytest.mark.asyncio
async def test_message_list_has_sent_and_retrieved_columns(app_config, tmp_path):
    """MessageList must expose 'Sent' and 'Retrieved' columns (not 'Date')."""
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node, Interface

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    iface = db.insert_interface(Interface(label="Test", iface_type="kiss_tcp", host="localhost", port=8910))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        msg_list = app.query_one("MessageList")
        col_names = [col.label.plain.strip() for col in msg_list.columns.values()]
        assert "Sent" in col_names
        assert "Retrieved" in col_names
        assert "Date" not in col_names


@pytest.mark.asyncio
async def test_message_list_shows_retrieved_date_and_dash_for_none(app_config, tmp_path):
    """Rows show formatted synced_at in Retrieved col; '—' when synced_at is None."""
    from open_packet.store.database import Database
    from open_packet.store.store import Store
    from open_packet.store.models import Operator, Node, Message, Bulletin
    from datetime import datetime, timezone
    from textual.coordinate import Coordinate

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    store = Store(db)

    # Non-queued message: synced_at is set by store on save
    msg = store.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="001",
        from_call="W0TEST", to_call="KD9ABC",
        subject="Hello", body="Body",
        timestamp=datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc),
    ))
    assert msg.synced_at is not None

    app_config.store.db_path = str(tmp_path / "test.db")
    app = OpenPacketApp(config=app_config)
    app._store = store
    app._active_operator = op
    app._active_folder = "Inbox"
    app._active_category = ""

    async with app.run_test() as pilot:
        app._refresh_message_list()
        await pilot.pause()
        msg_list = app.query_one("MessageList")
        assert msg_list.row_count == 1

        # Sent column (index 3): timestamp formatted as %m/%d %H:%M
        sent_val = msg_list.get_cell_at(Coordinate(0, 3))
        assert sent_val == "06/01 12:00"

        # Retrieved column (index 4): synced_at formatted
        retrieved_val = msg_list.get_cell_at(Coordinate(0, 4))
        assert retrieved_val != "—", "non-queued message must show a retrieved date"

    # Test queued (outbox) message: synced_at is None
    queued_msg = store.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="",
        from_call="KD9ABC", to_call="W0TEST",
        subject="Queued", body="Draft",
        timestamp=datetime(2025, 6, 2, 9, 0, tzinfo=timezone.utc),
        queued=True,
    ))
    assert queued_msg.synced_at is None

    app2 = OpenPacketApp(config=app_config)
    app2._store = store
    app2._active_operator = op
    app2._active_folder = "Outbox"
    app2._active_category = ""

    async with app2.run_test() as pilot2:
        app2._refresh_message_list()
        await pilot2.pause()
        msg_list2 = app2.query_one("MessageList")
        assert msg_list2.row_count == 1
        retrieved_val2 = msg_list2.get_cell_at(Coordinate(0, 4))
        assert retrieved_val2 == "—"


@pytest.mark.asyncio
async def test_mark_row_read_clears_unread_indicator(app_config, tmp_path):
    """mark_row_read(0) replaces '●' with ' ' in column 0 of the given row."""
    from open_packet.store.database import Database
    from open_packet.store.store import Store
    from open_packet.store.models import Operator, Node, Message
    from datetime import datetime, timezone
    from textual.coordinate import Coordinate

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    store = Store(db)
    store.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="001",
        from_call="W0TEST", to_call="KD9ABC",
        subject="Unread", body="Body",
        timestamp=datetime.now(timezone.utc),
        read=False,
    ))

    app_config.store.db_path = str(tmp_path / "test.db")
    app = OpenPacketApp(config=app_config)
    app._store = store
    app._active_operator = op
    app._active_folder = "Inbox"

    async with app.run_test() as pilot:
        app._refresh_message_list()
        await pilot.pause()
        msg_list = app.query_one("MessageList")

        # Unread message shows bullet
        assert msg_list.get_cell_at(Coordinate(0, 0)) == "●"

        # mark_row_read clears it
        msg_list.mark_row_read(0)
        assert msg_list.get_cell_at(Coordinate(0, 0)) == " "
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
uv run pytest tests/test_ui/test_tui.py::test_message_list_has_sent_and_retrieved_columns tests/test_ui/test_tui.py::test_message_list_shows_retrieved_date_and_dash_for_none tests/test_ui/test_tui.py::test_mark_row_read_clears_unread_indicator -v
```

Expected: all three FAIL.

- [ ] **Step 3: Update `MessageList` in `open_packet/ui/tui/widgets/message_list.py`**

Replace the entire file contents with:

```python
# open_packet/ui/tui/widgets/message_list.py
from __future__ import annotations
from textual.coordinate import Coordinate
from textual.widgets import DataTable
from textual.message import Message as TMessage
from open_packet.store.models import Message, Bulletin


class MessageList(DataTable):
    DEFAULT_CSS = """
    MessageList {
        height: 1fr;
    }
    """

    class MessageSelected(TMessage):
        def __init__(self, message: Message | Bulletin, row_index: int) -> None:
            self.message = message
            self.row_index = row_index
            super().__init__()

    def on_mount(self) -> None:
        self.add_columns("  ", "Subject", "From", "Sent", "Retrieved")
        self.cursor_type = "row"

    def load_messages(self, messages: list[Message | Bulletin]) -> None:
        self.clear()
        self._messages = messages
        for msg in messages:
            read_marker = " " if msg.read else "●"
            sent_str = msg.timestamp.strftime("%m/%d %H:%M") if msg.timestamp else "—"
            retrieved_str = msg.synced_at.strftime("%m/%d %H:%M") if msg.synced_at else "—"
            self.add_row(read_marker, msg.subject[:40], msg.from_call, sent_str, retrieved_str)

    def mark_row_read(self, row_index: int) -> None:
        self.update_cell_at(Coordinate(row_index, 0), " ")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if hasattr(self, "_messages") and event.cursor_row < len(self._messages):
            self.post_message(self.MessageSelected(self._messages[event.cursor_row], event.cursor_row))
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
uv run pytest tests/test_ui/test_tui.py::test_message_list_has_sent_and_retrieved_columns tests/test_ui/test_tui.py::test_message_list_shows_retrieved_date_and_dash_for_none tests/test_ui/test_tui.py::test_mark_row_read_clears_unread_indicator -v
```

Expected: all three PASS.

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add open_packet/ui/tui/widgets/message_list.py tests/test_ui/test_tui.py
git commit -m "feat: replace Date column with Sent/Retrieved in MessageList; add mark_row_read()"
```

---

## Task 3: FolderTree — dynamic width (min 18, max 32)

Add `_recompute_width()` to `FolderTree` and call it at the end of `update_counts()` and `update_sessions()`. Width accounts for tree indentation: depth-1 nodes (Inbox, Outbox, Sent) get +4 padding; depth-2 nodes (bulletin categories, sessions) get +8.

**Files:**
- Modify: `open_packet/ui/tui/widgets/folder_tree.py`
- Modify: `tests/test_ui/test_tui.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ui/test_tui.py`:

```python
@pytest.mark.asyncio
async def test_folder_tree_width_minimum_when_no_content(app_config, tmp_path):
    """Width stays at 18 (minimum) when all labels are short."""
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node, Interface

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    iface = db.insert_interface(Interface(label="Test", iface_type="kiss_tcp", host="localhost", port=8910))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        tree = app.query_one("FolderTree")
        tree.update_counts({"Inbox": (0, 0), "Sent": (0,), "Outbox": (0,)})
        assert tree.styles.width.value == 18


@pytest.mark.asyncio
async def test_folder_tree_width_expands_for_long_bulletin_category(app_config, tmp_path):
    """Width grows to fit long bulletin category labels (depth-2 nodes need +8 indent)."""
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node, Interface

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    iface = db.insert_interface(Interface(label="Test", iface_type="kiss_tcp", host="localhost", port=8910))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        tree = app.query_one("FolderTree")
        # "LONGNEWSCAT (5/2 new)" = 21 chars; depth-2 needs 21 + 8 = 29
        tree.update_counts({
            "Inbox": (0, 0), "Sent": (0,), "Outbox": (0,),
            "Bulletins": {"LONGNEWSCAT": (5, 2)},
        })
        assert tree.styles.width.value == 29


@pytest.mark.asyncio
async def test_folder_tree_width_capped_at_32(app_config, tmp_path):
    """Width never exceeds 32 regardless of label length."""
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node, Interface

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    iface = db.insert_interface(Interface(label="Test", iface_type="kiss_tcp", host="localhost", port=8910))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        tree = app.query_one("FolderTree")
        # "AVERYLONGCATEGORYNAME (100/50 new)" = 34 chars; 34 + 8 = 42 → capped at 32
        tree.update_counts({
            "Inbox": (0, 0), "Sent": (0,), "Outbox": (0,),
            "Bulletins": {"AVERYLONGCATEGORYNAME": (100, 50)},
        })
        assert tree.styles.width.value == 32
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
uv run pytest tests/test_ui/test_tui.py::test_folder_tree_width_minimum_when_no_content tests/test_ui/test_tui.py::test_folder_tree_width_expands_for_long_bulletin_category tests/test_ui/test_tui.py::test_folder_tree_width_capped_at_32 -v
```

Expected: all three FAIL (no `_recompute_width` method yet).

- [ ] **Step 3: Add `_recompute_width()` to `FolderTree` and wire it up**

Replace `open_packet/ui/tui/widgets/folder_tree.py` with:

```python
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

        if hasattr(self, "_session_nodes"):
            for node in self._session_nodes:
                depth2.append(_plain(node.label))

        max1 = max((len(s) for s in depth1), default=0)
        max2 = max((len(s) for s in depth2), default=0)
        needed = max(max1 + 4, max2 + 8)
        self.styles.width = max(18, min(32, needed))
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
uv run pytest tests/test_ui/test_tui.py::test_folder_tree_width_minimum_when_no_content tests/test_ui/test_tui.py::test_folder_tree_width_expands_for_long_bulletin_category tests/test_ui/test_tui.py::test_folder_tree_width_capped_at_32 -v
```

Expected: all three PASS.

- [ ] **Step 5: Run the full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add open_packet/ui/tui/widgets/folder_tree.py tests/test_ui/test_tui.py
git commit -m "feat: folder tree dynamically resizes between 18–32 columns to fit content"
```

---

## Task 4: App — wire `mark_row_read()` on message selection

When the user selects a message or bulletin that gets marked read, call `mark_row_read()` on the `MessageList` so the `●` clears in-place without reloading the table.

**Files:**
- Modify: `open_packet/ui/tui/app.py`
- Modify: `tests/test_ui/test_tui.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_ui/test_tui.py`:

```python
@pytest.mark.asyncio
async def test_selecting_message_clears_unread_indicator(app_config, tmp_path):
    """Selecting an unread message marks it read in DB and clears '●' in the list row."""
    from open_packet.store.database import Database
    from open_packet.store.store import Store
    from open_packet.store.models import Operator, Node, Message
    from datetime import datetime, timezone
    from textual.coordinate import Coordinate

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    store = Store(db)
    store.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="001",
        from_call="W0TEST", to_call="KD9ABC",
        subject="Unread msg", body="Body",
        timestamp=datetime.now(timezone.utc),
        read=False,
    ))

    app_config.store.db_path = str(tmp_path / "test.db")
    app = OpenPacketApp(config=app_config)
    app._store = store
    app._active_operator = op
    app._active_folder = "Inbox"

    async with app.run_test() as pilot:
        app._refresh_message_list()
        await pilot.pause()
        msg_list = app.query_one("MessageList")

        # Confirm unread
        assert msg_list.get_cell_at(Coordinate(0, 0)) == "●"

        # Post MessageSelected directly (bypasses DataTable; row_index carried in event)
        from open_packet.ui.tui.widgets.message_list import MessageList as MLWidget
        msg_list.post_message(MLWidget.MessageSelected(msg_list._messages[0], row_index=0))
        await pilot.pause()

        # The indicator must now be cleared
        assert msg_list.get_cell_at(Coordinate(0, 0)) == " "
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
uv run pytest tests/test_ui/test_tui.py::test_selecting_message_clears_unread_indicator -v
```

Expected: FAIL — cell still shows `"●"` after selection.

- [ ] **Step 3: Update `on_message_list_message_selected` in `open_packet/ui/tui/app.py`**

Find the method (around line 544). It currently ends with `self._refresh_folder_counts()`. Add the `mark_row_read` call:

```python
def on_message_list_message_selected(self, event) -> None:
    self._selected_message = event.message
    try:
        self.query_one("MessageBody").show_message(event.message)
    except Exception:
        pass
    if self._store and event.message.id is not None and not event.message.read:
        if isinstance(event.message, Message):
            self._store.mark_message_read(event.message.id)
        elif isinstance(event.message, Bulletin):
            self._store.mark_bulletin_read(event.message.id)
        event.message.read = True
        self._refresh_folder_counts()
        try:
            self.query_one("MessageList").mark_row_read(event.row_index)
        except Exception:
            pass
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
uv run pytest tests/test_ui/test_tui.py::test_selecting_message_clears_unread_indicator -v
```

Expected: PASS.

- [ ] **Step 5: Run the full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add open_packet/ui/tui/app.py tests/test_ui/test_tui.py
git commit -m "feat: clear unread indicator in-place when message is selected and marked read"
```
