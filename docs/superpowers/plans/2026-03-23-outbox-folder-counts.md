# Outbox Folder & Folder Counts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two message bugs (compose messages silently dropped, received messages re-transmitted) and add an Outbox folder with live count badges to the TUI.

**Architecture:** Add a `queued` boolean to the `messages` table to distinguish composed-but-unsent messages from received ones. Store gains `list_outbox()` and `count_folder_stats()`. Engine emits a `MessageQueuedEvent` after compose. `FolderTree` gains `update_counts()` which renders count badges using Rich `Text`.

**Tech Stack:** Python, SQLite (via `sqlite3`), Textual TUI, Rich

---

## File Map

| File | Change |
|------|--------|
| `open_packet/store/models.py` | Add `queued: bool = False` to `Message` |
| `open_packet/store/database.py` | Add `queued` column to schema; add ALTER TABLE migration in `initialize()` |
| `open_packet/store/store.py` | Fix `_row_to_message()`, fix `save_message()` dedup+INSERT, add `list_outbox()`, add `count_folder_stats()` |
| `open_packet/engine/events.py` | Add `MessageQueuedEvent`; update `Event` union |
| `open_packet/engine/engine.py` | Add import; fix `_do_send_message()`; fix `_do_check_mail()` outbound loop |
| `open_packet/ui/tui/widgets/folder_tree.py` | Rewrite `on_mount()` + `on_tree_node_selected()`; add `update_counts()` |
| `open_packet/ui/tui/app.py` | Add import; fix `_handle_event()`; fix `_refresh_message_list()` |
| `tests/test_store/test_store.py` | New tests for `queued` field, `list_outbox()`, `count_folder_stats()`, dedup bypass |
| `tests/test_engine/test_engine.py` | New tests for `MessageQueuedEvent`, outbox send loop |
| `tests/test_ui/test_tui.py` | New tests for `update_counts()` label rendering |

---

## Task 1: `queued` field in model and schema

**Files:**
- Modify: `open_packet/store/models.py`
- Modify: `open_packet/store/database.py`
- Test: `tests/test_store/test_store.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_store/test_store.py`:

```python
def test_message_model_queued_defaults_false():
    from datetime import datetime, timezone
    msg = Message(
        operator_id=1, node_id=1, bbs_id="x",
        from_call="W0A", to_call="W0B",
        subject="s", body="b",
        timestamp=datetime.now(timezone.utc),
    )
    assert msg.queued is False


def test_database_schema_has_queued_column(db):
    cols = [row[1] for row in db._conn.execute("PRAGMA table_info(messages)").fetchall()]
    assert "queued" in cols


def test_migration_adds_queued_column_to_existing_db():
    """Simulates an old DB that lacks the queued column."""
    import tempfile, os, sqlite3 as _sqlite3
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    # Create old-style schema without queued
    old_conn = _sqlite3.connect(f.name)
    old_conn.executescript("""
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator_id INTEGER NOT NULL,
            node_id INTEGER NOT NULL,
            bbs_id TEXT NOT NULL,
            from_call TEXT NOT NULL,
            to_call TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            read INTEGER NOT NULL DEFAULT 0,
            sent INTEGER NOT NULL DEFAULT 0,
            deleted INTEGER NOT NULL DEFAULT 0,
            synced_at TEXT
        );
        CREATE TABLE operators (id INTEGER PRIMARY KEY, callsign TEXT, ssid INTEGER, label TEXT, is_default INTEGER, created_at TEXT);
        CREATE TABLE nodes (id INTEGER PRIMARY KEY, label TEXT, callsign TEXT, ssid INTEGER, node_type TEXT, is_default INTEGER, created_at TEXT);
        CREATE TABLE bulletins (id INTEGER PRIMARY KEY, operator_id INTEGER, node_id INTEGER, bbs_id TEXT, category TEXT, from_call TEXT, subject TEXT, body TEXT, timestamp TEXT, read INTEGER, synced_at TEXT);
    """)
    old_conn.close()
    # Now open with Database — should migrate transparently
    from open_packet.store.database import Database
    db2 = Database(f.name)
    db2.initialize()
    cols = [row[1] for row in db2._conn.execute("PRAGMA table_info(messages)").fetchall()]
    db2.close()
    os.unlink(f.name)
    assert "queued" in cols
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_store/test_store.py::test_message_model_queued_defaults_false tests/test_store/test_store.py::test_database_schema_has_queued_column tests/test_store/test_store.py::test_migration_adds_queued_column_to_existing_db -v
```

Expected: all three FAIL (field doesn't exist yet).

- [ ] **Step 3: Add `queued` to `Message` model**

In `open_packet/store/models.py`, add after `deleted: bool = False`:
```python
queued: bool = False
```

- [ ] **Step 4: Add `queued` column to schema and migration**

In `open_packet/store/database.py`, in `_create_schema()` inside the `messages` CREATE TABLE, add after `deleted INTEGER NOT NULL DEFAULT 0,`:
```sql
queued INTEGER NOT NULL DEFAULT 0,
```

In `Database.initialize()`, after the `self._create_schema()` call, add:
```python
try:
    self._conn.execute(
        "ALTER TABLE messages ADD COLUMN queued INTEGER NOT NULL DEFAULT 0"
    )
    self._conn.commit()
except sqlite3.OperationalError:
    pass  # column already exists
```

`sqlite3` is already imported at the top of `database.py`.

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_store/test_store.py::test_message_model_queued_defaults_false tests/test_store/test_store.py::test_database_schema_has_queued_column tests/test_store/test_store.py::test_migration_adds_queued_column_to_existing_db -v
```

Expected: all three PASS.

- [ ] **Step 6: Run full test suite to catch regressions**

```bash
python -m pytest tests/ -q
```

Expected: all existing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add open_packet/store/models.py open_packet/store/database.py tests/test_store/test_store.py
git commit -m "feat: add queued column to messages table and model"
```

---

## Task 2: Store — fix `_row_to_message()`, fix `save_message()`, add `list_outbox()` and `count_folder_stats()`

**Files:**
- Modify: `open_packet/store/store.py`
- Test: `tests/test_store/test_store.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_store/test_store.py`:

```python
def test_row_to_message_preserves_queued_flag(store):
    s, op, node = store
    msg = Message(
        operator_id=op.id, node_id=node.id, bbs_id="",
        from_call="KD9ABC-1", to_call="W0TEST",
        subject="Queued", body="Body",
        timestamp=datetime.now(timezone.utc),
        queued=True,
    )
    saved = s.save_message(msg)
    fetched = s.get_message(saved.id)
    assert fetched.queued is True


def test_multiple_queued_messages_all_saved(store):
    """Each compose action must produce its own row (dedup bypass for queued=True)."""
    s, op, node = store
    for i in range(3):
        s.save_message(Message(
            operator_id=op.id, node_id=node.id, bbs_id="",
            from_call="KD9ABC-1", to_call="W0TEST",
            subject=f"Msg {i}", body="Body",
            timestamp=datetime.now(timezone.utc),
            queued=True,
        ))
    outbox = s.list_outbox(op.id)
    assert len(outbox) == 3


def test_received_messages_still_deduplicated(store):
    s, op, node = store
    msg = Message(
        operator_id=op.id, node_id=node.id, bbs_id="007",
        from_call="W0TEST", to_call="KD9ABC",
        subject="Dupe", body="Body",
        timestamp=datetime.now(timezone.utc),
    )
    s.save_message(msg)
    s.save_message(msg)
    messages = s.list_messages(op.id)
    assert len([m for m in messages if m.bbs_id == "007"]) == 1


def test_list_outbox_excludes_sent_and_deleted(store):
    s, op, node = store
    # queued + sent (transmitted) — should NOT appear
    transmitted = s.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="",
        from_call="KD9ABC-1", to_call="W0TEST",
        subject="Sent", body="Body",
        timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    s.mark_message_sent(transmitted.id)
    # queued + deleted — should NOT appear
    deleted = s.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="",
        from_call="KD9ABC-1", to_call="W0TEST",
        subject="Deleted", body="Body",
        timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    s.delete_message(deleted.id)
    # queued + pending — SHOULD appear
    s.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="",
        from_call="KD9ABC-1", to_call="W0TEST",
        subject="Pending", body="Body",
        timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    outbox = s.list_outbox(op.id)
    assert len(outbox) == 1
    assert outbox[0].subject == "Pending"


def test_count_folder_stats_empty_db(store):
    s, op, node = store
    stats = s.count_folder_stats(op.id)
    assert stats["Inbox"] == (0, 0)
    assert stats["Sent"] == (0,)
    assert stats["Outbox"] == (0,)


def test_count_folder_stats_counts_correctly(store):
    s, op, node = store
    now = datetime.now(timezone.utc)
    # 2 received, 1 unread
    m1 = s.save_message(Message(operator_id=op.id, node_id=node.id, bbs_id="A1",
        from_call="W0A", to_call="KD9ABC", subject="s", body="b", timestamp=now))
    m2 = s.save_message(Message(operator_id=op.id, node_id=node.id, bbs_id="A2",
        from_call="W0A", to_call="KD9ABC", subject="s", body="b", timestamp=now))
    s.mark_message_read(m1.id)
    # 1 queued (outbox)
    s.save_message(Message(operator_id=op.id, node_id=node.id, bbs_id="",
        from_call="KD9ABC-1", to_call="W0A", subject="s", body="b",
        timestamp=now, queued=True))
    # 1 transmitted (queued+sent → appears in Sent)
    tx = s.save_message(Message(operator_id=op.id, node_id=node.id, bbs_id="",
        from_call="KD9ABC-1", to_call="W0B", subject="s", body="b",
        timestamp=now, queued=True))
    s.mark_message_sent(tx.id)

    stats = s.count_folder_stats(op.id)
    assert stats["Inbox"] == (2, 1)    # 2 total, 1 unread
    assert stats["Outbox"] == (1,)     # 1 pending
    assert stats["Sent"] == (1,)       # 1 transmitted
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_store/test_store.py::test_row_to_message_preserves_queued_flag tests/test_store/test_store.py::test_multiple_queued_messages_all_saved tests/test_store/test_store.py::test_received_messages_still_deduplicated tests/test_store/test_store.py::test_list_outbox_excludes_sent_and_deleted tests/test_store/test_store.py::test_count_folder_stats_empty_db tests/test_store/test_store.py::test_count_folder_stats_counts_correctly -v
```

Expected: all FAIL.

- [ ] **Step 3: Fix `_row_to_message()`**

In `open_packet/store/store.py`, in `_row_to_message()`, add `queued=bool(row["queued"])` to the `Message(...)` call. Place it after `deleted=bool(row["deleted"])`.

- [ ] **Step 4: Fix `save_message()` — dedup bypass and INSERT**

In `open_packet/store/store.py`, in `save_message()`:

Replace the existing dedup block:
```python
existing = self._conn.execute(
    "SELECT id FROM messages WHERE bbs_id=? AND node_id=?",
    (msg.bbs_id, msg.node_id),
).fetchone()
if existing:
    return self.get_message(existing["id"])  # type: ignore
```

With:
```python
if not msg.queued:
    existing = self._conn.execute(
        "SELECT id FROM messages WHERE bbs_id=? AND node_id=?",
        (msg.bbs_id, msg.node_id),
    ).fetchone()
    if existing:
        return self.get_message(existing["id"])  # type: ignore
```

Replace the existing INSERT with:
```python
cur = self._conn.execute(
    """INSERT INTO messages
       (operator_id, node_id, bbs_id, from_call, to_call, subject, body,
        timestamp, read, sent, deleted, queued, synced_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
    (
        msg.operator_id, msg.node_id, msg.bbs_id, msg.from_call,
        msg.to_call, msg.subject, msg.body,
        msg.timestamp.isoformat(),
        int(msg.read), int(msg.sent), int(msg.deleted), int(msg.queued),
        None if msg.queued else datetime.now(timezone.utc).isoformat(),
    ),
)
self._conn.commit()
```

- [ ] **Step 5: Add `list_outbox()`**

Add to `Store` after `list_messages()`:
```python
def list_outbox(self, operator_id: int) -> list[Message]:
    assert self._conn
    rows = self._conn.execute(
        "SELECT * FROM messages WHERE operator_id=? AND queued=1 AND sent=0 AND deleted=0 ORDER BY timestamp ASC",
        (operator_id,),
    ).fetchall()
    return [self._row_to_message(r) for r in rows]
```

- [ ] **Step 6: Add `count_folder_stats()`**

Add to `Store` after `list_outbox()`:
```python
def count_folder_stats(self, operator_id: int) -> dict[str, tuple[int, ...]]:
    assert self._conn
    row = self._conn.execute(
        """SELECT
               COALESCE(SUM(CASE WHEN queued=0 AND sent=0 AND deleted=0            THEN 1 ELSE 0 END), 0) AS inbox_total,
               COALESCE(SUM(CASE WHEN queued=0 AND sent=0 AND deleted=0 AND read=0 THEN 1 ELSE 0 END), 0) AS inbox_unread,
               COALESCE(SUM(CASE WHEN sent=1 AND deleted=0                         THEN 1 ELSE 0 END), 0) AS sent_total,
               COALESCE(SUM(CASE WHEN queued=1 AND sent=0 AND deleted=0            THEN 1 ELSE 0 END), 0) AS outbox_count
           FROM messages WHERE operator_id=?""",
        (operator_id,),
    ).fetchone()
    return {
        "Inbox":  (row["inbox_total"], row["inbox_unread"]),
        "Sent":   (row["sent_total"],),
        "Outbox": (row["outbox_count"],),
    }
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
python -m pytest tests/test_store/test_store.py -v
```

Expected: all PASS.

- [ ] **Step 8: Run full test suite**

```bash
python -m pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add open_packet/store/store.py tests/test_store/test_store.py
git commit -m "feat: fix save_message dedup for queued msgs; add list_outbox and count_folder_stats"
```

---

## Task 3: Engine — `MessageQueuedEvent`, fix `_do_send_message()`, fix `_do_check_mail()`

**Files:**
- Modify: `open_packet/engine/events.py`
- Modify: `open_packet/engine/engine.py`
- Test: `tests/test_engine/test_engine.py`

- [ ] **Step 1: Write the failing tests**

First, update the module-level imports at the top of `tests/test_engine/test_engine.py`:

- `CheckMailCommand` is **already imported** on the `from open_packet.engine.commands import` line — no change needed there.
- Add `SendMessageCommand` to the existing commands import line:
  ```python
  from open_packet.engine.commands import CheckMailCommand, DisconnectCommand, SendMessageCommand
  ```
- Add `MessageQueuedEvent` to the existing events import block (replace the existing block):
  ```python
  from open_packet.engine.events import (
      ConnectionStatusEvent, SyncCompleteEvent, ErrorEvent, ConnectionStatus,
      MessageQueuedEvent,
  )
  ```

Then add the following test functions to `tests/test_engine/test_engine.py`:

```python


def test_send_message_command_saves_to_outbox(db_and_store):
    """SendMessageCommand saves a queued message; does NOT transmit immediately."""
    db, store, op, node_record = db_and_store
    mock_node = make_mock_node()
    mock_connection = MagicMock()

    cmd_queue = queue.Queue()
    evt_queue = queue.Queue()

    engine = Engine(
        command_queue=cmd_queue, event_queue=evt_queue,
        store=store, operator=op, node_record=node_record,
        connection=mock_connection, node=mock_node,
    )
    engine.start()
    cmd_queue.put(SendMessageCommand(to_call="W0TEST", subject="Hi", body="Body"))

    events = []
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        try:
            events.append(evt_queue.get(timeout=0.3))
        except queue.Empty:
            break

    engine.stop()

    # MessageQueuedEvent must be emitted
    assert any(isinstance(e, MessageQueuedEvent) for e in events)
    # Message must be in the outbox
    outbox = store.list_outbox(op.id)
    assert len(outbox) == 1
    assert outbox[0].to_call == "W0TEST"
    # Node send_message must NOT have been called (not a sync)
    mock_node.send_message.assert_not_called()


def test_check_mail_sends_only_queued_messages(db_and_store):
    """Only outbox messages are transmitted during sync; received messages are never re-sent."""
    db, store, op, node_record = db_and_store
    from datetime import datetime, timezone

    # Pre-populate: one received inbox message (queued=False)
    store.save_message(Message(
        operator_id=op.id, node_id=node_record.id, bbs_id="RX1",
        from_call="W0A", to_call="KD9ABC",
        subject="Received", body="body",
        timestamp=datetime.now(timezone.utc),
    ))
    # Pre-populate: one outbox message (queued=True)
    store.save_message(Message(
        operator_id=op.id, node_id=node_record.id, bbs_id="",
        from_call="KD9ABC-1", to_call="W0B",
        subject="Outgoing", body="body",
        timestamp=datetime.now(timezone.utc),
        queued=True,
    ))

    mock_node = make_mock_node()
    mock_connection = MagicMock()
    cmd_queue = queue.Queue()
    evt_queue = queue.Queue()

    engine = Engine(
        command_queue=cmd_queue, event_queue=evt_queue,
        store=store, operator=op, node_record=node_record,
        connection=mock_connection, node=mock_node,
    )
    engine.start()
    cmd_queue.put(CheckMailCommand())

    events = []
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            events.append(evt_queue.get(timeout=0.5))
        except queue.Empty:
            break

    engine.stop()

    sync_events = [e for e in events if isinstance(e, SyncCompleteEvent)]
    assert len(sync_events) == 1
    assert sync_events[0].messages_sent == 1   # only the queued message
    # send_message called exactly once, with outgoing subject
    mock_node.send_message.assert_called_once()
    call_args = mock_node.send_message.call_args
    assert call_args[0][1] == "Outgoing"  # subject is second positional arg


def test_multiple_compose_actions_each_queued(db_and_store):
    """Composing three messages results in three outbox rows."""
    db, store, op, node_record = db_and_store
    mock_node = make_mock_node()
    mock_connection = MagicMock()
    cmd_queue = queue.Queue()
    evt_queue = queue.Queue()

    engine = Engine(
        command_queue=cmd_queue, event_queue=evt_queue,
        store=store, operator=op, node_record=node_record,
        connection=mock_connection, node=mock_node,
    )
    engine.start()
    for i in range(3):
        cmd_queue.put(SendMessageCommand(to_call="W0TEST", subject=f"Msg {i}", body="b"))

    # Drain events
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        try:
            evt_queue.get(timeout=0.2)
        except queue.Empty:
            break

    engine.stop()
    assert len(store.list_outbox(op.id)) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_engine/test_engine.py::test_send_message_command_saves_to_outbox tests/test_engine/test_engine.py::test_check_mail_sends_only_queued_messages tests/test_engine/test_engine.py::test_multiple_compose_actions_each_queued -v
```

Expected: all FAIL.

- [ ] **Step 3: Add `MessageQueuedEvent` to `events.py`**

In `open_packet/engine/events.py`, add after `ErrorEvent`:
```python
@dataclass
class MessageQueuedEvent:
    pass
```

Update the union:
```python
Event = ConnectionStatusEvent | MessageReceivedEvent | SyncCompleteEvent | ErrorEvent | MessageQueuedEvent
```

- [ ] **Step 4: Fix `engine.py` imports and `_do_send_message()`**

In `open_packet/engine/engine.py`, add `MessageQueuedEvent` to the events import line.

Replace `_do_send_message()` body with:
```python
def _do_send_message(self, cmd: SendMessageCommand) -> None:
    now = datetime.now(timezone.utc)
    self._store.save_message(Message(
        operator_id=self._operator.id,
        node_id=self._node_record.id,
        bbs_id="",
        from_call=f"{self._operator.callsign}-{self._operator.ssid}",
        to_call=cmd.to_call,
        subject=cmd.subject,
        body=cmd.body,
        timestamp=now,
        queued=True,
    ))
    self._emit(MessageQueuedEvent())
```

- [ ] **Step 5: Fix `_do_check_mail()` outbound loop**

In `open_packet/engine/engine.py`, in `_do_check_mail()`, find and replace the entire outbound block. In the current source it starts with `sent = 0` and a `# Send any queued outbound messages` comment. Remove that block entirely and replace with:

```python
# Send queued outbound messages
sent = 0
outbound = self._store.list_outbox(self._operator.id)
for m in outbound:
    self._node.send_message(m.to_call, m.subject, m.body)
    self._store.mark_message_sent(m.id)
    sent += 1
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
python -m pytest tests/test_engine/test_engine.py -v
```

Expected: all PASS.

- [ ] **Step 7: Run full test suite**

```bash
python -m pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add open_packet/engine/events.py open_packet/engine/engine.py tests/test_engine/test_engine.py
git commit -m "feat: add MessageQueuedEvent; fix compose save and outbound send loop"
```

---

## Task 4: `FolderTree` — Outbox folder and `update_counts()`

**Files:**
- Modify: `open_packet/ui/tui/widgets/folder_tree.py`
- Test: `tests/test_ui/test_tui.py`

- [ ] **Step 1: Write the failing tests**

`OpenPacketApp` is **already imported** at the top of `tests/test_ui/test_tui.py` — no new imports needed for these tests.

Add to `tests/test_ui/test_tui.py`:

```python
@pytest.mark.asyncio
async def test_update_counts_inbox_labels(app_config, tmp_path):
    """update_counts() sets correct Inbox label variants on the mounted FolderTree."""
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        tree = app.query_one("FolderTree")

        # No messages → plain labels
        tree.update_counts({"Inbox": (0, 0), "Sent": (0,), "Outbox": (0,)})
        await pilot.pause()
        assert str(tree._inbox_node.label) == "Inbox"
        assert str(tree._sent_node.label) == "Sent"
        assert str(tree._outbox_node.label) == "Outbox"

        # Inbox with messages, no unread
        tree.update_counts({"Inbox": (5, 0), "Sent": (2,), "Outbox": (0,)})
        await pilot.pause()
        assert str(tree._inbox_node.label) == "Inbox (5)"
        assert str(tree._sent_node.label) == "Sent (2)"

        # Inbox with unread
        tree.update_counts({"Inbox": (10, 3), "Sent": (0,), "Outbox": (0,)})
        await pilot.pause()
        inbox_label = tree._inbox_node.label
        assert "10" in str(inbox_label)
        assert "3" in str(inbox_label)

        # Outbox with pending messages → gold background
        from rich.text import Text
        tree.update_counts({"Inbox": (0, 0), "Sent": (0,), "Outbox": (4,)})
        await pilot.pause()
        outbox_label = tree._outbox_node.label
        assert isinstance(outbox_label, Text)
        assert "4" in outbox_label.plain
        assert outbox_label.style.bgcolor is not None


@pytest.mark.asyncio
async def test_update_counts_outbox_cleared(app_config, tmp_path):
    """When Outbox count drops to 0, label returns to plain 'Outbox' with no background."""
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node
    from rich.text import Text

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        tree = app.query_one("FolderTree")
        tree.update_counts({"Inbox": (0, 0), "Sent": (0,), "Outbox": (2,)})
        await pilot.pause()
        tree.update_counts({"Inbox": (0, 0), "Sent": (0,), "Outbox": (0,)})
        await pilot.pause()
        label = tree._outbox_node.label
        assert str(label) == "Outbox"
        # No background style on cleared outbox
        if isinstance(label, Text):
            assert label.style.bgcolor is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_ui/test_tui.py::test_update_counts_inbox_labels tests/test_ui/test_tui.py::test_update_counts_outbox_cleared -v
```

Expected: FAIL — `FolderTree` has no `update_counts()` method and no `_inbox_node` attribute yet.

- [ ] **Step 3: Rewrite `FolderTree`**

Replace the entire body of `open_packet/ui/tui/widgets/folder_tree.py` with:

```python
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
            self._outbox_node.set_label("Outbox")

        self._sent_node.set_label(f"Sent ({sent_total})" if sent_total > 0 else "Sent")
```

- [ ] **Step 4: Run the new tests to verify they now pass**

```bash
python -m pytest tests/test_ui/test_tui.py::test_update_counts_inbox_labels tests/test_ui/test_tui.py::test_update_counts_outbox_cleared -v
```

Expected: both PASS.

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add open_packet/ui/tui/widgets/folder_tree.py tests/test_ui/test_tui.py
git commit -m "feat: add Outbox folder and update_counts() to FolderTree"
```

---

## Task 5: App — wire `MessageQueuedEvent`, fix Inbox filter, add Outbox case and count refresh

**Files:**
- Modify: `open_packet/ui/tui/app.py`
- Test: `tests/test_ui/test_tui.py`

- [ ] **Step 1: Write a smoke-check test (expected to already pass after Task 2)**

This test confirms that the `Store` methods needed by `app.py` exist and were added in Task 2. It is not a failing test — it should pass immediately. Its value is catching accidental regressions if this task is re-run out of order.

Add to `tests/test_ui/test_tui.py`:

```python
def test_app_store_has_outbox_methods():
    """Smoke-check: Store has the methods app.py will call for Outbox and folder counts."""
    from open_packet.store.store import Store
    assert hasattr(Store, "list_outbox"), "Store.list_outbox missing — Task 2 not complete"
    assert hasattr(Store, "count_folder_stats"), "Store.count_folder_stats missing — Task 2 not complete"
```

- [ ] **Step 2: Run test to verify it passes** (it should, since Task 2 added the methods)

```bash
python -m pytest tests/test_ui/test_tui.py::test_app_store_has_outbox_methods -v
```

Expected: PASS. If it fails, complete Task 2 first.

- [ ] **Step 3: Update `app.py` imports**

In `open_packet/ui/tui/app.py`, add `MessageQueuedEvent` to the events import:
```python
from open_packet.engine.events import (
    ConnectionStatusEvent, MessageReceivedEvent, SyncCompleteEvent,
    ErrorEvent, ConnectionStatus, MessageQueuedEvent,
)
```

- [ ] **Step 4: Fix `_handle_event()`**

In `open_packet/ui/tui/app.py`, at the top of `_handle_event()`, add before the `try` block:
```python
if isinstance(event, MessageQueuedEvent):
    self._refresh_message_list()
    return
```

- [ ] **Step 5: Fix `_refresh_message_list()`**

In `open_packet/ui/tui/app.py`, inside `_refresh_message_list()`:

1. Change the Inbox filter from `if not m.sent` to `if not m.sent and not m.queued`.

2. Add the Outbox branch before `else: messages = []`:
```python
elif folder == "Outbox":
    messages = self._store.list_outbox(operator_id=operator_id)
```

3. After `msg_list.load_messages(messages)`, add:
```python
stats = self._store.count_folder_stats(operator_id)
self.query_one("FolderTree").update_counts(stats)
```

- [ ] **Step 6: Run full test suite**

```bash
python -m pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 7: Smoke test the TUI manually**

Start the app:
```bash
python -m open_packet.ui.tui.app test.yaml
```

Verify:
- Folder tree shows Inbox, Outbox, Sent, Bulletins in that order
- Inbox count badge appears after check mail
- Compose a message → Outbox shows `(1)` with gold background immediately
- Check mail → outbox message is sent, Outbox returns to plain "Outbox", Sent count increases

- [ ] **Step 8: Commit**

```bash
git add open_packet/ui/tui/app.py tests/test_ui/test_tui.py
git commit -m "feat: wire Outbox folder, folder counts, and MessageQueuedEvent in app"
```

---

## Verification

After all tasks:

```bash
python -m pytest tests/ -v
```

All 123+ tests must pass. Then do the manual smoke test from Task 5 Step 7.
