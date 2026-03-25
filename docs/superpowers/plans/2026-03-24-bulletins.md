# Bulletin Retrieval and Posting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bulletin retrieval (during Check Mail) and posting (via outbox, sent inline with Check Mail), with dynamic per-category counts in the folder tree.

**Architecture:** Extend the `Bulletin` model with `queued`/`sent` state fields (matching the `Message` pattern). Store helpers gate what appears in the category view vs. the outbox. The engine gains two new phases in `_do_check_mail()` (send queued bulletins, then retrieve bulletins) and a `_do_post_bulletin()` handler. The TUI gains a `ComposeBulletinScreen`, a `b` keybinding, and dynamic folder tree nodes driven by `count_folder_stats()`.

**Tech Stack:** Python, SQLite (`sqlite3`), Textual TUI framework, BPQ32 BBS protocol over AX.25/KISS

---

## File Map

| File | Change |
|------|--------|
| `open_packet/store/models.py` | Add `queued: bool = False`, `sent: bool = False` to `Bulletin` |
| `open_packet/store/database.py` | Migration: add `queued`/`sent` columns to `bulletins` table |
| `open_packet/store/store.py` | Update `save_bulletin()`, `_row_to_bulletin()`, `list_bulletins()`; add `list_outbox_messages()`, `list_outbox_bulletins()`, `mark_bulletin_sent()`, `bulletin_exists()`; extend `list_outbox()`, `count_folder_stats()` |
| `open_packet/node/base.py` | Add abstract `post_bulletin()` method |
| `open_packet/node/bpq.py` | Implement `post_bulletin()` |
| `open_packet/engine/commands.py` | Add `PostBulletinCommand`; update `Command` union |
| `open_packet/engine/events.py` | Add `bulletins_retrieved: int = 0` to `SyncCompleteEvent` |
| `open_packet/engine/engine.py` | Add phases 3+4 to `_do_check_mail()`; add `_do_post_bulletin()`; dispatch in `_handle()` |
| `open_packet/ui/tui/screens/compose_bulletin.py` | New `ComposeBulletinScreen` |
| `open_packet/ui/tui/screens/main.py` | Add `b` keybinding and `action_new_bulletin()` |
| `open_packet/ui/tui/app.py` | `open_compose_bulletin()`, `_on_compose_bulletin_result()`, updated sync notification, `delete_selected_message()` guard |
| `open_packet/ui/tui/widgets/message_list.py` | Update type annotations to `Message \| Bulletin` |
| `open_packet/ui/tui/widgets/message_body.py` | Handle `Bulletin` in `show_message()` |
| `open_packet/ui/tui/widgets/folder_tree.py` | Dynamic bulletin category nodes with counts |
| `tests/test_store/test_store.py` | New tests for all store changes |
| `tests/test_ui/test_tui.py` | Tests for `update_counts()` with bulletin data |

---

### Task 1: Extend Bulletin model + DB migration

**Files:**
- Modify: `open_packet/store/models.py`
- Modify: `open_packet/store/database.py`
- Modify: `tests/test_store/test_store.py`

- [ ] **Step 1: Write the failing migration test**

Add to `tests/test_store/test_store.py`:

```python
def test_migration_adds_queued_sent_columns_to_bulletins():
    """DB.initialize() on an existing bulletins table adds queued and sent columns."""
    import tempfile, os, sqlite3
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    try:
        # Create old schema without queued/sent
        conn = sqlite3.connect(f.name)
        conn.execute("""CREATE TABLE bulletins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator_id INTEGER, node_id INTEGER, bbs_id TEXT,
            category TEXT, from_call TEXT, subject TEXT, body TEXT,
            timestamp TEXT, read INTEGER NOT NULL DEFAULT 0,
            synced_at TEXT
        )""")
        conn.commit()
        conn.close()

        db = Database(f.name)
        db.initialize()
        conn2 = sqlite3.connect(f.name)
        cols = [r[1] for r in conn2.execute("PRAGMA table_info(bulletins)").fetchall()]
        conn2.close()
        db.close()
        assert "queued" in cols
        assert "sent" in cols
    finally:
        os.unlink(f.name)
```

- [ ] **Step 2: Run to confirm it fails**

```bash
uv run pytest tests/test_store/test_store.py::test_migration_adds_queued_sent_columns_to_bulletins -v
```

Expected: FAIL (columns don't exist yet)

- [ ] **Step 3: Add `queued`/`sent` fields to `Bulletin` in `models.py`**

In `open_packet/store/models.py`, add two fields after `read`:

```python
@dataclass
class Bulletin:
    operator_id: int
    node_id: int
    bbs_id: str
    category: str
    from_call: str
    subject: str
    body: str
    timestamp: datetime
    read: bool = False
    queued: bool = False
    sent: bool = False
    id: Optional[int] = None
    synced_at: Optional[datetime] = None
```

- [ ] **Step 4: Add migration to `database.py`**

In `open_packet/store/database.py`, in `initialize()` after the existing `nodes` migration block, add:

```python
for sql in [
    "ALTER TABLE bulletins ADD COLUMN queued INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE bulletins ADD COLUMN sent INTEGER NOT NULL DEFAULT 0",
]:
    try:
        self._conn.execute(sql)
        self._conn.commit()
    except sqlite3.OperationalError:
        pass
```

- [ ] **Step 5: Run test to confirm it passes**

```bash
uv run pytest tests/test_store/test_store.py::test_migration_adds_queued_sent_columns_to_bulletins -v
```

Expected: PASS

- [ ] **Step 6: Run full test suite to confirm nothing broke**

```bash
uv run pytest -x
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add open_packet/store/models.py open_packet/store/database.py tests/test_store/test_store.py
git commit -m "feat: add queued/sent fields to Bulletin model and DB migration"
```

---

### Task 2: Update `save_bulletin()` and `_row_to_bulletin()`

**Files:**
- Modify: `open_packet/store/store.py`
- Modify: `tests/test_store/test_store.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_store/test_store.py`:

```python
def test_save_bulletin_queued_skips_dedup(store):
    """Outgoing bulletins (queued=True) are always inserted fresh, not deduped."""
    s, op, node = store
    from datetime import datetime, timezone
    bul = Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="OUT-aabbccdd",
        category="WX", from_call="KD9ABC", subject="WX Report",
        body="Sunny.", timestamp=datetime.now(timezone.utc),
        queued=True, sent=False,
    )
    b1 = s.save_bulletin(bul)
    b2 = s.save_bulletin(bul)   # second save of same bbs_id
    assert b1.id != b2.id       # both inserted (no dedup)
    assert b1.queued is True
    assert b1.sent is False


def test_save_bulletin_received_deduplicates(store):
    """Received bulletins (queued=False) are deduped by bbs_id + node_id."""
    s, op, node = store
    from datetime import datetime, timezone
    bul = Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="BBS-001",
        category="NTS", from_call="W0TEST", subject="NTS msg",
        body="Test.", timestamp=datetime.now(timezone.utc),
    )
    b1 = s.save_bulletin(bul)
    b2 = s.save_bulletin(bul)
    assert b1.id == b2.id   # deduped


def test_row_to_bulletin_maps_queued_sent(store):
    """Bulletins retrieved from DB have queued/sent fields correctly mapped."""
    s, op, node = store
    from datetime import datetime, timezone
    bul = Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="OUT-xyz",
        category="WX", from_call="KD9ABC", subject="Test",
        body="Body.", timestamp=datetime.now(timezone.utc),
        queued=True, sent=False,
    )
    saved = s.save_bulletin(bul)
    fetched = s._get_bulletin(saved.id)
    assert fetched.queued is True
    assert fetched.sent is False
```

- [ ] **Step 2: Run to confirm they fail**

```bash
uv run pytest tests/test_store/test_store.py::test_save_bulletin_queued_skips_dedup tests/test_store/test_store.py::test_save_bulletin_received_deduplicates tests/test_store/test_store.py::test_row_to_bulletin_maps_queued_sent -v
```

Expected: FAIL

- [ ] **Step 3: Update `save_bulletin()` in `store.py`**

Replace the existing `save_bulletin()` method:

```python
def save_bulletin(self, bul: Bulletin) -> Bulletin:
    assert self._conn
    if not bul.queued:
        existing = self._conn.execute(
            "SELECT id FROM bulletins WHERE bbs_id=? AND node_id=?",
            (bul.bbs_id, bul.node_id),
        ).fetchone()
        if existing:
            return self._get_bulletin(existing["id"])  # type: ignore

    cur = self._conn.execute(
        """INSERT INTO bulletins
           (operator_id, node_id, bbs_id, category, from_call, subject, body,
            timestamp, read, queued, sent, synced_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            bul.operator_id, bul.node_id, bul.bbs_id, bul.category,
            bul.from_call, bul.subject, bul.body,
            bul.timestamp.isoformat(), int(bul.read),
            int(bul.queued), int(bul.sent),
            None if bul.queued else datetime.now(timezone.utc).isoformat(),
        ),
    )
    self._conn.commit()
    return self._get_bulletin(cur.lastrowid)  # type: ignore
```

- [ ] **Step 4: Update `_row_to_bulletin()` in `store.py`**

Replace the existing `_row_to_bulletin()`:

```python
def _row_to_bulletin(self, row) -> Bulletin:
    return Bulletin(
        id=row["id"], operator_id=row["operator_id"], node_id=row["node_id"],
        bbs_id=row["bbs_id"], category=row["category"], from_call=row["from_call"],
        subject=row["subject"], body=row["body"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        read=bool(row["read"]),
        queued=bool(row["queued"]),
        sent=bool(row["sent"]),
    )
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
uv run pytest tests/test_store/test_store.py::test_save_bulletin_queued_skips_dedup tests/test_store/test_store.py::test_save_bulletin_received_deduplicates tests/test_store/test_store.py::test_row_to_bulletin_maps_queued_sent -v
```

Expected: all PASS

- [ ] **Step 6: Run full suite**

```bash
uv run pytest -x
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add open_packet/store/store.py tests/test_store/test_store.py
git commit -m "feat: update save_bulletin and _row_to_bulletin for queued/sent"
```

---

### Task 3: Update `list_bulletins()` and `count_folder_stats()`; add outbox helpers

**Files:**
- Modify: `open_packet/store/store.py`
- Modify: `tests/test_store/test_store.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_store/test_store.py`:

```python
def test_list_bulletins_excludes_queued(store):
    """list_bulletins() does not return outgoing (queued) bulletins."""
    s, op, node = store
    from datetime import datetime, timezone
    # Received bulletin — should appear
    s.save_bulletin(Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="BBS-001",
        category="WX", from_call="W0TEST", subject="Received",
        body="Body", timestamp=datetime.now(timezone.utc),
    ))
    # Queued (outgoing) bulletin — should NOT appear
    s.save_bulletin(Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="OUT-aabb",
        category="WX", from_call="KD9ABC", subject="Outgoing",
        body="Body", timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    bulletins = s.list_bulletins(operator_id=op.id)
    assert len(bulletins) == 1
    assert bulletins[0].subject == "Received"


def test_list_outbox_includes_bulletins(store):
    """list_outbox() returns both queued messages and queued bulletins."""
    s, op, node = store
    from datetime import datetime, timezone
    from open_packet.store.models import Message
    # Queued message
    s.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="",
        from_call="KD9ABC", to_call="W0TEST", subject="Msg",
        body="Body", timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    # Queued bulletin
    s.save_bulletin(Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="OUT-aabb",
        category="WX", from_call="KD9ABC", subject="Bul",
        body="Body", timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    outbox = s.list_outbox(operator_id=op.id)
    assert len(outbox) == 2
    subjects = {item.subject for item in outbox}
    assert "Msg" in subjects
    assert "Bul" in subjects


def test_list_outbox_messages_only(store):
    """list_outbox_messages() returns only Message objects."""
    s, op, node = store
    from datetime import datetime, timezone
    from open_packet.store.models import Message
    s.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="",
        from_call="KD9ABC", to_call="W0TEST", subject="Msg",
        body="Body", timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    s.save_bulletin(Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="OUT-aabb",
        category="WX", from_call="KD9ABC", subject="Bul",
        body="Body", timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    msgs = s.list_outbox_messages(operator_id=op.id)
    assert len(msgs) == 1
    assert isinstance(msgs[0], Message)
    assert msgs[0].subject == "Msg"


def test_list_outbox_bulletins_only(store):
    """list_outbox_bulletins() returns only Bulletin objects."""
    s, op, node = store
    from datetime import datetime, timezone
    from open_packet.store.models import Message
    s.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="",
        from_call="KD9ABC", to_call="W0TEST", subject="Msg",
        body="Body", timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    s.save_bulletin(Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="OUT-aabb",
        category="WX", from_call="KD9ABC", subject="Bul",
        body="Body", timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    buls = s.list_outbox_bulletins(operator_id=op.id)
    assert len(buls) == 1
    assert isinstance(buls[0], Bulletin)
    assert buls[0].subject == "Bul"


def test_count_folder_stats_includes_bulletin_counts(store):
    """count_folder_stats() returns per-category bulletin counts under 'Bulletins' key."""
    s, op, node = store
    from datetime import datetime, timezone
    # Two received WX bulletins, one unread
    s.save_bulletin(Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="B001",
        category="WX", from_call="W0TEST", subject="WX1",
        body="Body", timestamp=datetime.now(timezone.utc), read=True,
    ))
    s.save_bulletin(Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="B002",
        category="WX", from_call="W0TEST", subject="WX2",
        body="Body", timestamp=datetime.now(timezone.utc), read=False,
    ))
    # One received NTS bulletin
    s.save_bulletin(Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="B003",
        category="NTS", from_call="W0TEST", subject="NTS1",
        body="Body", timestamp=datetime.now(timezone.utc), read=False,
    ))
    # One queued outgoing bulletin — must NOT appear in Bulletins counts
    s.save_bulletin(Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="OUT-xx",
        category="WX", from_call="KD9ABC", subject="Out",
        body="Body", timestamp=datetime.now(timezone.utc), queued=True,
    ))
    stats = s.count_folder_stats(op.id)
    assert "Bulletins" in stats
    wx = stats["Bulletins"]["WX"]
    nts = stats["Bulletins"]["NTS"]
    assert wx == (2, 1)    # 2 total, 1 unread
    assert nts == (1, 1)   # 1 total, 1 unread


def test_count_folder_stats_outbox_includes_queued_bulletins(store):
    """Outbox count includes both queued messages and queued bulletins."""
    s, op, node = store
    from datetime import datetime, timezone
    from open_packet.store.models import Message
    s.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="",
        from_call="KD9ABC", to_call="W0TEST", subject="Msg",
        body="Body", timestamp=datetime.now(timezone.utc), queued=True,
    ))
    s.save_bulletin(Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="OUT-aabb",
        category="WX", from_call="KD9ABC", subject="Bul",
        body="Body", timestamp=datetime.now(timezone.utc), queued=True,
    ))
    stats = s.count_folder_stats(op.id)
    assert stats["Outbox"] == (2,)
```

- [ ] **Step 2: Run to confirm they fail**

```bash
uv run pytest tests/test_store/test_store.py::test_list_bulletins_excludes_queued tests/test_store/test_store.py::test_list_outbox_includes_bulletins tests/test_store/test_store.py::test_list_outbox_messages_only tests/test_store/test_store.py::test_list_outbox_bulletins_only tests/test_store/test_store.py::test_count_folder_stats_includes_bulletin_counts tests/test_store/test_store.py::test_count_folder_stats_outbox_includes_queued_bulletins -v
```

Expected: all FAIL

- [ ] **Step 3: Update `list_bulletins()` — add `queued=0` filter**

In `store.py`, update `list_bulletins()`:

```python
def list_bulletins(self, operator_id: int, category: Optional[str] = None) -> list[Bulletin]:
    assert self._conn
    query = "SELECT * FROM bulletins WHERE operator_id=? AND queued=0"
    params: list = [operator_id]
    if category:
        query += " AND category=?"
        params.append(category)
    query += " ORDER BY timestamp DESC"
    rows = self._conn.execute(query, params).fetchall()
    return [self._row_to_bulletin(r) for r in rows]
```

- [ ] **Step 4: Update `list_outbox()` — extend to include bulletins**

Replace existing `list_outbox()`:

```python
def list_outbox(self, operator_id: int) -> list[Message | Bulletin]:
    assert self._conn
    msg_rows = self._conn.execute(
        "SELECT * FROM messages WHERE operator_id=? AND queued=1 AND sent=0 AND deleted=0 ORDER BY timestamp ASC",
        (operator_id,),
    ).fetchall()
    bul_rows = self._conn.execute(
        "SELECT * FROM bulletins WHERE operator_id=? AND queued=1 AND sent=0 ORDER BY timestamp ASC",
        (operator_id,),
    ).fetchall()
    messages = [self._row_to_message(r) for r in msg_rows]
    bulletins = [self._row_to_bulletin(r) for r in bul_rows]
    combined: list[Message | Bulletin] = messages + bulletins
    combined.sort(key=lambda x: x.timestamp)
    return combined
```

Add this import at the top of `store.py` if not already present (it already imports `Message` and `Bulletin` from models).

- [ ] **Step 5: Add `list_outbox_messages()` and `list_outbox_bulletins()`**

Add both methods to `Store` after `list_outbox()`:

```python
def list_outbox_messages(self, operator_id: int) -> list[Message]:
    assert self._conn
    rows = self._conn.execute(
        "SELECT * FROM messages WHERE operator_id=? AND queued=1 AND sent=0 AND deleted=0 ORDER BY timestamp ASC",
        (operator_id,),
    ).fetchall()
    return [self._row_to_message(r) for r in rows]

def list_outbox_bulletins(self, operator_id: int) -> list[Bulletin]:
    assert self._conn
    rows = self._conn.execute(
        "SELECT * FROM bulletins WHERE operator_id=? AND queued=1 AND sent=0 ORDER BY timestamp ASC",
        (operator_id,),
    ).fetchall()
    return [self._row_to_bulletin(r) for r in rows]
```

- [ ] **Step 6: Update `count_folder_stats()` — add Bulletins key and fix Outbox count**

Replace existing `count_folder_stats()`:

```python
def count_folder_stats(self, operator_id: int) -> dict[str, tuple | dict]:
    assert self._conn
    row = self._conn.execute(
        """SELECT
               COALESCE(SUM(CASE WHEN queued=0 AND sent=0 AND deleted=0            THEN 1 ELSE 0 END), 0) AS inbox_total,
               COALESCE(SUM(CASE WHEN queued=0 AND sent=0 AND deleted=0 AND read=0 THEN 1 ELSE 0 END), 0) AS inbox_unread,
               COALESCE(SUM(CASE WHEN sent=1 AND deleted=0                         THEN 1 ELSE 0 END), 0) AS sent_total,
               COALESCE(SUM(CASE WHEN queued=1 AND sent=0 AND deleted=0            THEN 1 ELSE 0 END), 0) AS msg_outbox
           FROM messages WHERE operator_id=?""",
        (operator_id,),
    ).fetchone()
    bul_outbox_row = self._conn.execute(
        "SELECT COUNT(*) AS cnt FROM bulletins WHERE operator_id=? AND queued=1 AND sent=0",
        (operator_id,),
    ).fetchone()
    outbox_count = row["msg_outbox"] + bul_outbox_row["cnt"]

    bul_rows = self._conn.execute(
        """SELECT category,
                  COUNT(*) AS total,
                  SUM(CASE WHEN read=0 THEN 1 ELSE 0 END) AS unread
           FROM bulletins WHERE operator_id=? AND queued=0
           GROUP BY category""",
        (operator_id,),
    ).fetchall()
    bulletins: dict[str, tuple[int, int]] = {
        r["category"]: (r["total"], r["unread"]) for r in bul_rows
    }

    return {
        "Inbox":     (row["inbox_total"], row["inbox_unread"]),
        "Sent":      (row["sent_total"],),
        "Outbox":    (outbox_count,),
        "Bulletins": bulletins,
    }
```

- [ ] **Step 7: Run tests to confirm they pass**

```bash
uv run pytest tests/test_store/test_store.py::test_list_bulletins_excludes_queued tests/test_store/test_store.py::test_list_outbox_includes_bulletins tests/test_store/test_store.py::test_list_outbox_messages_only tests/test_store/test_store.py::test_list_outbox_bulletins_only tests/test_store/test_store.py::test_count_folder_stats_includes_bulletin_counts tests/test_store/test_store.py::test_count_folder_stats_outbox_includes_queued_bulletins -v
```

Expected: all PASS

- [ ] **Step 8: Run full suite**

```bash
uv run pytest -x
```

Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add open_packet/store/store.py tests/test_store/test_store.py
git commit -m "feat: extend store with bulletin outbox helpers and folder stats"
```

---

### Task 4: Store — `mark_bulletin_sent()` and `bulletin_exists()`

**Files:**
- Modify: `open_packet/store/store.py`
- Modify: `tests/test_store/test_store.py`

- [ ] **Step 1: Write failing tests**

```python
def test_mark_bulletin_sent(store):
    """mark_bulletin_sent() sets sent=1 for the bulletin."""
    s, op, node = store
    from datetime import datetime, timezone
    bul = Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="OUT-abc",
        category="WX", from_call="KD9ABC", subject="Test",
        body="Body", timestamp=datetime.now(timezone.utc),
        queued=True, sent=False,
    )
    saved = s.save_bulletin(bul)
    assert saved.sent is False
    s.mark_bulletin_sent(saved.id)
    fetched = s._get_bulletin(saved.id)
    assert fetched.sent is True


def test_bulletin_exists(store):
    """bulletin_exists() returns True only when bbs_id+node_id exists in DB."""
    s, op, node = store
    from datetime import datetime, timezone
    bul = Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="BBS-999",
        category="WX", from_call="W0TEST", subject="Test",
        body="Body", timestamp=datetime.now(timezone.utc),
    )
    assert s.bulletin_exists("BBS-999", node.id) is False
    s.save_bulletin(bul)
    assert s.bulletin_exists("BBS-999", node.id) is True
    assert s.bulletin_exists("BBS-999", node.id + 1) is False  # different node
```

- [ ] **Step 2: Run to confirm they fail**

```bash
uv run pytest tests/test_store/test_store.py::test_mark_bulletin_sent tests/test_store/test_store.py::test_bulletin_exists -v
```

Expected: FAIL

- [ ] **Step 3: Add both methods to `store.py`**

Add after `_row_to_bulletin()`:

```python
def mark_bulletin_sent(self, id: int) -> None:
    assert self._conn
    self._conn.execute("UPDATE bulletins SET sent=1 WHERE id=?", (id,))
    self._conn.commit()

def bulletin_exists(self, bbs_id: str, node_id: int) -> bool:
    assert self._conn
    row = self._conn.execute(
        "SELECT id FROM bulletins WHERE bbs_id=? AND node_id=?",
        (bbs_id, node_id),
    ).fetchone()
    return row is not None
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_store/test_store.py::test_mark_bulletin_sent tests/test_store/test_store.py::test_bulletin_exists -v
```

Expected: PASS

- [ ] **Step 5: Run full suite**

```bash
uv run pytest -x
```

- [ ] **Step 6: Commit**

```bash
git add open_packet/store/store.py tests/test_store/test_store.py
git commit -m "feat: add mark_bulletin_sent and bulletin_exists to store"
```

---

### Task 5: Node layer — `post_bulletin()`

**Files:**
- Modify: `open_packet/node/base.py`
- Modify: `open_packet/node/bpq.py`

Note: `list_bulletins()` and `read_bulletin()` already exist as abstract methods in `NodeBase` and are already implemented in `BPQNode`. Only `post_bulletin()` is missing.

- [ ] **Step 1: Write failing test (abstract method presence)**

Add to `tests/test_node/test_bpq.py` (this directory and file already exist):

```python
def test_node_base_has_post_bulletin():
    """NodeBase declares post_bulletin as abstract."""
    abstract_methods = getattr(NodeBase, '__abstractmethods__', set())
    assert 'post_bulletin' in abstract_methods
```

Ensure `NodeBase` is imported at the top of the file (check existing imports; add `from open_packet.node.base import NodeBase` if missing).

- [ ] **Step 2: Run to confirm it fails**

```bash
uv run pytest tests/test_node/test_bpq.py::test_node_base_has_post_bulletin -v
```

Expected: FAIL

- [ ] **Step 3: Add abstract `post_bulletin()` to `base.py`**

In `open_packet/node/base.py`, add after `read_bulletin()`:

```python
@abstractmethod
def post_bulletin(self, category: str, subject: str, body: str) -> None: ...
```

- [ ] **Step 4: Add `post_bulletin()` implementation to `bpq.py`**

Find `send_message()` in `open_packet/node/bpq.py` and add `post_bulletin()` using the same pattern (body lines one at a time, `/EX` separate):

```python
def post_bulletin(self, category: str, subject: str, body: str) -> None:
    self._send_text(f"SB {category}")
    self._recv_until_prompt(timeout=5.0)
    self._send_text(subject)
    self._recv_until_prompt(timeout=5.0)
    for line in body.splitlines():
        self._send_text(line)
    self._send_text("/EX")
    self._recv_until_prompt()
```

- [ ] **Step 5: Run test to confirm it passes**

```bash
uv run pytest -k "test_node_base_has_post_bulletin" -v
```

Expected: PASS

- [ ] **Step 6: Run full suite**

```bash
uv run pytest -x
```

- [ ] **Step 7: Commit**

```bash
git add open_packet/node/base.py open_packet/node/bpq.py tests/test_node/test_bpq.py
git commit -m "feat: add post_bulletin to NodeBase and BPQNode"
```

---

### Task 6: Engine — `PostBulletinCommand` and `SyncCompleteEvent` update

**Files:**
- Modify: `open_packet/engine/commands.py`
- Modify: `open_packet/engine/events.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_store/test_store.py`:

```python
def test_post_bulletin_command_exists():
    """PostBulletinCommand is a dataclass in the Command union."""
    from open_packet.engine.commands import PostBulletinCommand, Command
    cmd = PostBulletinCommand(category="WX", subject="Test", body="Body")
    assert cmd.category == "WX"
    assert cmd.subject == "Test"
    # Verify it's part of the union by checking the type alias includes it
    import typing
    args = typing.get_args(Command)
    assert PostBulletinCommand in args


def test_sync_complete_event_has_bulletins_retrieved():
    """SyncCompleteEvent accepts bulletins_retrieved with default 0."""
    from open_packet.engine.events import SyncCompleteEvent
    e1 = SyncCompleteEvent(messages_retrieved=3, messages_sent=1)
    assert e1.bulletins_retrieved == 0
    e2 = SyncCompleteEvent(messages_retrieved=2, messages_sent=0, bulletins_retrieved=5)
    assert e2.bulletins_retrieved == 5
```

- [ ] **Step 2: Run to confirm they fail**

```bash
uv run pytest -k "test_post_bulletin_command_exists or test_sync_complete_event_has_bulletins_retrieved" -v
```

Expected: FAIL

- [ ] **Step 3: Add `PostBulletinCommand` to `commands.py`**

```python
@dataclass
class PostBulletinCommand:
    category: str
    subject: str
    body: str


Command = ConnectCommand | DisconnectCommand | CheckMailCommand | SendMessageCommand | DeleteMessageCommand | PostBulletinCommand
```

- [ ] **Step 4: Add `bulletins_retrieved` to `SyncCompleteEvent` in `events.py`**

```python
@dataclass
class SyncCompleteEvent:
    messages_retrieved: int
    messages_sent: int
    bulletins_retrieved: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
uv run pytest -k "test_post_bulletin_command_exists or test_sync_complete_event_has_bulletins_retrieved" -v
```

Expected: PASS

- [ ] **Step 6: Run full suite**

```bash
uv run pytest -x
```

- [ ] **Step 7: Commit**

```bash
git add open_packet/engine/commands.py open_packet/engine/events.py tests/test_store/test_store.py
git commit -m "feat: add PostBulletinCommand and bulletins_retrieved to SyncCompleteEvent"
```

---

### Task 7: Engine — bulletin send/retrieve phases and `_do_post_bulletin()`

**Files:**
- Modify: `open_packet/engine/engine.py`

- [ ] **Step 1: Write failing behavior tests**

Add to `tests/test_engine/test_engine.py`. The file already has `db_and_store` and `make_mock_node` fixtures and imports.

First, add `PostBulletinCommand` to the existing module-level command import (around line 11):

```python
from open_packet.engine.commands import CheckMailCommand, DisconnectCommand, SendMessageCommand, PostBulletinCommand
```

Also add `MessageQueuedEvent` to the existing events import if not already present:

```python
from open_packet.engine.events import (
    ConnectionStatusEvent, SyncCompleteEvent, ErrorEvent, ConnectionStatus,
    MessageQueuedEvent,
)
```

Then add these tests at the bottom:

```python
def test_engine_do_post_bulletin_saves_to_outbox(db_and_store):
    """PostBulletinCommand saves a queued Bulletin to the store outbox."""
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
    cmd_queue.put(PostBulletinCommand(category="WX", subject="WX Report", body="Sunny."))

    events = []
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            events.append(evt_queue.get(timeout=0.5))
        except queue.Empty:
            break
    engine.stop()

    assert any(isinstance(e, MessageQueuedEvent) for e in events)
    outbox = store.list_outbox_bulletins(op.id)
    assert len(outbox) == 1
    assert outbox[0].category == "WX"
    assert outbox[0].queued is True
    assert outbox[0].sent is False


def test_engine_check_mail_retrieves_bulletins(db_and_store):
    """_do_check_mail() phase 4 saves retrieved bulletins and reports count."""
    from open_packet.node.base import MessageHeader, Message as NodeMessage
    db, store, op, node_record = db_and_store
    mock_node = make_mock_node(
        bulletins=[
            MessageHeader(bbs_id="BUL-1", to_call="WX", from_call="W0WX", subject="WX Alert"),
        ]
    )
    mock_node.read_bulletin.return_value = NodeMessage(
        header=mock_node.list_bulletins.return_value[0],
        body="Tornado watch.",
    )
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
    assert sync_events
    assert sync_events[0].bulletins_retrieved == 1
    bulletins = store.list_bulletins(op.id)
    assert len(bulletins) == 1
    assert bulletins[0].bbs_id == "BUL-1"
    assert bulletins[0].category == "WX"
```

- [ ] **Step 2: Run to confirm they fail**

```bash
uv run pytest tests/test_engine/test_engine.py::test_engine_do_post_bulletin_saves_to_outbox tests/test_engine/test_engine.py::test_engine_check_mail_retrieves_bulletins -v
```

Expected: FAIL

- [ ] **Step 3: Update imports in `engine.py`**

Add to the existing imports in `engine.py`:

```python
from open_packet.engine.commands import (
    Command, CheckMailCommand, ConnectCommand, DisconnectCommand,
    SendMessageCommand, DeleteMessageCommand, PostBulletinCommand,
)
```

Also add `Bulletin` import if not present (it already is: `from open_packet.store.models import Operator, Node, Message, Bulletin`).

- [ ] **Step 4: Add dispatch for `PostBulletinCommand` in `_handle()`**

In `_handle()`, add after the `DeleteMessageCommand` branch:

```python
elif isinstance(cmd, PostBulletinCommand):
    self._do_post_bulletin(cmd)
```

- [ ] **Step 5: Add `_do_post_bulletin()` method**

Add after `_do_delete_message()`:

```python
def _do_post_bulletin(self, cmd: PostBulletinCommand) -> None:
    from uuid import uuid4
    bulletin = Bulletin(
        operator_id=self._operator.id,
        node_id=self._node_record.id,
        bbs_id=f"OUT-{uuid4().hex[:8]}",
        category=cmd.category,
        from_call=self._operator.callsign,
        subject=cmd.subject,
        body=cmd.body,
        timestamp=datetime.now(timezone.utc),
        queued=True,
        sent=False,
    )
    self._store.save_bulletin(bulletin)
    self._emit(MessageQueuedEvent())
```

- [ ] **Step 6: Update `_do_check_mail()` — phases 2, 3, 4**

In `_do_check_mail()`, replace the message send block and the `SyncCompleteEvent` emit with:

```python
            # Phase 2: Send queued outbound messages
            sent = 0
            outbound = self._store.list_outbox_messages(self._operator.id)
            for m in outbound:
                self._emit(ConsoleEvent(">", f"Sending to {m.to_call}: {m.subject}"))
                self._node.send_message(m.to_call, m.subject, m.body)
                self._store.mark_message_sent(m.id)
                sent += 1

            # Phase 3: Send queued bulletins
            pending_bulletins = self._store.list_outbox_bulletins(self._operator.id)
            for bul in pending_bulletins:
                self._emit(ConsoleEvent(">", f"Posting bulletin to {bul.category}: {bul.subject}"))
                self._node.post_bulletin(bul.category, bul.subject, bul.body)
                self._store.mark_bulletin_sent(bul.id)

            # Phase 4: Retrieve bulletins
            bulletin_headers = self._node.list_bulletins()
            bulletins_retrieved = 0
            for header in bulletin_headers:
                if self._store.bulletin_exists(header.bbs_id, self._node_record.id):
                    continue
                try:
                    raw = self._node.read_bulletin(header.bbs_id)
                except Exception:
                    logger.exception("Failed to read bulletin %s", header.bbs_id)
                    self._emit(ConsoleEvent("!", f"Failed to read bulletin {header.bbs_id}"))
                    continue
                bulletin = Bulletin(
                    operator_id=self._operator.id,
                    node_id=self._node_record.id,
                    bbs_id=header.bbs_id,
                    category=header.to_call,
                    from_call=header.from_call,
                    subject=header.subject,
                    body=raw.body,
                    timestamp=datetime.now(timezone.utc),
                )
                self._store.save_bulletin(bulletin)
                bulletins_retrieved += 1
                self._emit(ConsoleEvent("<", f"[{header.bbs_id}] {header.subject} from {header.from_call}"))

            self._last_sync = datetime.now(timezone.utc)
            self._messages_last_sync = retrieved
            self._emit(SyncCompleteEvent(
                messages_retrieved=retrieved,
                messages_sent=sent,
                bulletins_retrieved=bulletins_retrieved,
            ))
```

- [ ] **Step 7: Run tests to confirm they pass**

```bash
uv run pytest tests/test_engine/test_engine.py::test_engine_do_post_bulletin_saves_to_outbox tests/test_engine/test_engine.py::test_engine_check_mail_retrieves_bulletins -v
```

Expected: PASS

- [ ] **Step 8: Run full suite**

```bash
uv run pytest -x
```

Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add open_packet/engine/engine.py tests/test_engine/test_engine.py
git commit -m "feat: add bulletin send/retrieve phases and _do_post_bulletin to engine"
```

---

### Task 8: `ComposeBulletinScreen`

**Files:**
- Create: `open_packet/ui/tui/screens/compose_bulletin.py`

- [ ] **Step 1: Write smoke test**

Add to `tests/test_ui/test_tui.py`:

```python
def test_compose_bulletin_command_exists():
    """Importing ComposeBulletinScreen succeeds and PostBulletinCommand is importable."""
    from open_packet.ui.tui.screens.compose_bulletin import ComposeBulletinScreen
    from open_packet.engine.commands import PostBulletinCommand
    assert ComposeBulletinScreen is not None
```

- [ ] **Step 2: Run to confirm it fails**

```bash
uv run pytest tests/test_ui/test_tui.py::test_compose_bulletin_command_exists -v
```

Expected: FAIL (module doesn't exist)

- [ ] **Step 3: Create `compose_bulletin.py`**

Mirror `open_packet/ui/tui/screens/compose.py` but with `category`/`subject`/`body` fields (no `to_call`):

```python
# open_packet/ui/tui/screens/compose_bulletin.py
from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, TextArea
from textual.containers import Vertical, Horizontal
from open_packet.engine.commands import PostBulletinCommand


class ComposeBulletinScreen(ModalScreen):
    DEFAULT_CSS = """
    ComposeBulletinScreen {
        align: center middle;
    }
    ComposeBulletinScreen Vertical {
        width: 70;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    ComposeBulletinScreen TextArea {
        height: 10;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("New Bulletin", id="compose_title")
            yield Label("Category:")
            yield Input(placeholder="e.g. WX", id="category_field")
            yield Label("", id="category_error")
            yield Label("Subject:")
            yield Input(placeholder="Subject", id="subject_field")
            yield Label("Body:")
            yield TextArea(id="body_field")
            with Horizontal():
                yield Button("Post", variant="primary", id="post_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.dismiss(None)
        elif event.button.id == "post_btn":
            category = self.query_one("#category_field", Input).value.strip()
            subject = self.query_one("#subject_field", Input).value.strip()
            body = self.query_one("#body_field", TextArea).text.strip()
            if not category:
                self.query_one("#category_error", Label).update("Category is required.")
                return
            self.dismiss(PostBulletinCommand(
                category=category, subject=subject, body=body
            ))
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
uv run pytest tests/test_ui/test_tui.py::test_compose_bulletin_command_exists -v
```

Expected: PASS

- [ ] **Step 5: Run full suite**

```bash
uv run pytest -x
```

- [ ] **Step 6: Commit**

```bash
git add open_packet/ui/tui/screens/compose_bulletin.py tests/test_ui/test_tui.py
git commit -m "feat: add ComposeBulletinScreen"
```

---

### Task 9: TUI wiring — `main.py`, `app.py`, `message_list.py`, `message_body.py`

**Files:**
- Modify: `open_packet/ui/tui/screens/main.py`
- Modify: `open_packet/ui/tui/app.py`
- Modify: `open_packet/ui/tui/widgets/message_list.py`
- Modify: `open_packet/ui/tui/widgets/message_body.py`

- [ ] **Step 1: Add `b` keybinding to `main.py`**

In `BINDINGS` in `open_packet/ui/tui/screens/main.py`, add after the `n` binding:

```python
("b", "new_bulletin", "Bulletin"),
```

Add `action_new_bulletin()` method:

```python
def action_new_bulletin(self) -> None:
    self.app.open_compose_bulletin()
```

- [ ] **Step 2: Update `app.py`**

Add import at top of `app.py` (with other screen imports):

```python
from open_packet.ui.tui.screens.compose_bulletin import ComposeBulletinScreen
```

Update the `PostBulletinCommand` import:

```python
from open_packet.engine.commands import (
    CheckMailCommand, DeleteMessageCommand, SendMessageCommand, PostBulletinCommand
)
```

Add `Message` import from store models (it's already imported: `from open_packet.store.models import Operator, Node, Interface`). Add `Message` and `Bulletin`:

```python
from open_packet.store.models import Operator, Node, Interface, Message, Bulletin
```

Add methods to `OpenPacketApp`:

```python
def open_compose_bulletin(self) -> None:
    self.push_screen(ComposeBulletinScreen(), callback=self._on_compose_bulletin_result)

def _on_compose_bulletin_result(self, result) -> None:
    if result and isinstance(result, PostBulletinCommand):
        self._cmd_queue.put(result)
```

Replace `delete_selected_message()` with a version that explicitly guards against None and Bulletin:

```python
def delete_selected_message(self) -> None:
    if self._selected_message is None or not isinstance(self._selected_message, Message):
        return
    if self._engine:
        self._cmd_queue.put(DeleteMessageCommand(
            message_id=self._selected_message.id,
            bbs_id=self._selected_message.bbs_id,
        ))
```

Update the `SyncCompleteEvent` handler in `_handle_event()` — change the notify text:

```python
elif isinstance(event, SyncCompleteEvent):
    from datetime import datetime
    status_bar.last_sync = datetime.now().strftime("%H:%M")
    self.notify(
        f"Sync complete: {event.messages_retrieved} new, {event.bulletins_retrieved} bulletins, {event.messages_sent} sent"
    )
    self._refresh_message_list()
```

- [ ] **Step 3: Update `message_list.py` type annotations**

In `open_packet/ui/tui/widgets/message_list.py`, add `Bulletin` to the import:

```python
from open_packet.store.models import Message, Bulletin
```

Update `MessageSelected.__init__` and `load_messages()`:

```python
class MessageSelected(TMessage):
    def __init__(self, message: Message | Bulletin) -> None:
        self.message = message
        super().__init__()

def load_messages(self, messages: list[Message | Bulletin]) -> None:
    self.clear()
    self._messages = messages
    for msg in messages:
        read_marker = " " if msg.read else "●"
        date_str = msg.timestamp.strftime("%m/%d %H:%M") if msg.timestamp else ""
        self.add_row(read_marker, msg.subject[:40], msg.from_call, date_str)
```

- [ ] **Step 4: Update `message_body.py` to handle `Bulletin`**

In `open_packet/ui/tui/widgets/message_body.py`, add `Bulletin` import:

```python
from open_packet.store.models import Message, Bulletin
```

Update `show_message()`:

```python
def show_message(self, message: Message | Bulletin) -> None:
    self.clear()
    self.write(f"From:    {message.from_call}")
    if isinstance(message, Bulletin):
        self.write(f"Category: {message.category}")
    else:
        self.write(f"To:      {message.to_call}")
    self.write(f"Subject: {message.subject}")
    self.write("─" * 40)
    self.write(message.body)
```

- [ ] **Step 5: Run the app-mounts and basic tests**

```bash
uv run pytest tests/test_ui/ -x -v
```

Expected: all pass

- [ ] **Step 6: Run full suite**

```bash
uv run pytest -x
```

- [ ] **Step 7: Commit**

```bash
git add open_packet/ui/tui/screens/main.py open_packet/ui/tui/app.py open_packet/ui/tui/widgets/message_list.py open_packet/ui/tui/widgets/message_body.py
git commit -m "feat: wire bulletin compose flow, type-safe message/bulletin handling in TUI"
```

---

### Task 10: FolderTree — dynamic bulletin category nodes

**Files:**
- Modify: `open_packet/ui/tui/widgets/folder_tree.py`
- Modify: `tests/test_ui/test_tui.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_ui/test_tui.py`:

```python
async def test_update_counts_bulletin_categories_dynamic(app_config, tmp_path):
    """update_counts() creates and updates dynamic bulletin category nodes."""
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node, Interface

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    iface = db.insert_interface(Interface(
        label="Test", iface_type="kiss_tcp", host="localhost", port=8910
    ))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        tree = app.query_one("FolderTree")

        # Provide bulletin stats — WX with 3 total, 1 unread
        tree.update_counts({
            "Inbox": (0, 0), "Sent": (0,), "Outbox": (0,),
            "Bulletins": {"WX": (3, 1), "NTS": (5, 0)},
        })
        await pilot.pause()
        assert "WX" in tree._bulletin_nodes
        assert "NTS" in tree._bulletin_nodes
        wx_label = str(tree._bulletin_nodes["WX"].label)
        nts_label = str(tree._bulletin_nodes["NTS"].label)
        assert "3" in wx_label and "1" in wx_label   # "WX (3/1 new)"
        assert "5" in nts_label                       # "NTS (5)"

        # Remove NTS from stats — node should be removed
        tree.update_counts({
            "Inbox": (0, 0), "Sent": (0,), "Outbox": (0,),
            "Bulletins": {"WX": (3, 1)},
        })
        await pilot.pause()
        assert "NTS" not in tree._bulletin_nodes
        assert "WX" in tree._bulletin_nodes
```

- [ ] **Step 2: Run to confirm it fails**

```bash
uv run pytest tests/test_ui/test_tui.py::test_update_counts_bulletin_categories_dynamic -v
```

Expected: FAIL

- [ ] **Step 3: Update `folder_tree.py`**

Replace the entire file content:

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
        self._inbox_node    = self.root.add_leaf("Inbox",  data="Inbox")
        self._outbox_node   = self.root.add_leaf("Outbox", data="Outbox")
        self._sent_node     = self.root.add_leaf("Sent",   data="Sent")
        self._bulletins_node = self.root.add("Bulletins", data="Bulletins")
        self._bulletin_nodes: dict[str, TreeNode] = {}

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        folder = event.node.data or str(event.node.label)
        parent = event.node.parent
        if parent and parent.data == "Bulletins":
            self.post_message(self.FolderSelected("Bulletins", category=folder))
        else:
            self.post_message(self.FolderSelected(folder))

    def update_counts(self, stats: dict) -> None:
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

        # Dynamic bulletin category nodes
        bulletin_stats: dict[str, tuple[int, int]] = stats.get("Bulletins", {})

        # Add/update nodes for categories present in stats
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

        # Remove nodes for categories no longer in stats
        for category in list(self._bulletin_nodes):
            if category not in bulletin_stats:
                self._bulletin_nodes[category].remove()
                del self._bulletin_nodes[category]
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
uv run pytest tests/test_ui/test_tui.py::test_update_counts_bulletin_categories_dynamic -v
```

Expected: PASS

- [ ] **Step 5: Run full suite**

```bash
uv run pytest -x
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add open_packet/ui/tui/widgets/folder_tree.py tests/test_ui/test_tui.py
git commit -m "feat: dynamic bulletin category nodes in folder tree with counts"
```

---

## Done

Run the full test suite one final time to confirm everything passes:

```bash
uv run pytest
```

Then use `superpowers:finishing-a-development-branch` to merge or create a PR.
