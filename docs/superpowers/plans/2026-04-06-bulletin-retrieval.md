# Bulletin Header-First Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change bulletin sync from downloading every body on every connection to a two-phase model: list headers during sync, then fetch bodies only for bulletins the user has explicitly queued for retrieval.

**Architecture:** The `Bulletin` model gains a nullable `body` (stored as `""` in SQLite to avoid NOT NULL migration complexity, mapped to `None` in Python) and a `wants_retrieval` flag. The engine's Phase 4 saves header-only rows; a new Phase 5 fetches bodies for queued bulletins. The TUI adds an `r` binding to mark a pending bulletin for retrieval, and dims header-only rows in the message list.

**Tech Stack:** Python dataclasses, SQLite (via existing `Database`/`Store` pattern), Textual TUI, pytest with in-memory temp DB fixtures.

---

## File Map

| File | Change |
|------|--------|
| `open_packet/store/models.py` | `body: Optional[str] = None`; add `wants_retrieval: bool = False`; reorder `timestamp`/`body` |
| `open_packet/store/database.py` | Migration: `ALTER TABLE bulletins ADD COLUMN wants_retrieval INTEGER NOT NULL DEFAULT 0` |
| `open_packet/store/store.py` | Update `save_bulletin` + `_row_to_bulletin` for empty-string sentinel; add `mark_bulletin_wants_retrieval`, `list_bulletins_pending_retrieval`, `update_bulletin_body` |
| `open_packet/engine/engine.py` | Revise Phase 4: save headers only; add Phase 5: retrieve queued bodies |
| `open_packet/store/exporter.py` | Guard `export_bulletins` against `body is None` |
| `open_packet/ui/tui/screens/main.py` | Add `Binding("r", "queue_bulletin_retrieval", "Queue Retrieval")` and `action_queue_bulletin_retrieval` |
| `open_packet/ui/tui/app.py` | Add `queue_bulletin_retrieval()` method; pass `node_label` to `show_message` for pending bulletins |
| `open_packet/ui/tui/widgets/message_body.py` | Handle `body is None` in `show_message` with placeholder text |
| `open_packet/ui/tui/widgets/message_list.py` | Dim rows where bulletin `body is None` |
| `tests/test_store/test_store.py` | Tests for header-only save, new store methods |
| `tests/test_engine/test_engine.py` | Tests for revised Phase 4/5 behaviour |

---

## Task 1: Update Bulletin Model and Add DB Migration

**Files:**
- Modify: `open_packet/store/models.py`
- Modify: `open_packet/store/database.py`
- Test: `tests/test_store/test_store.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_store/test_store.py`:

```python
def test_bulletin_body_defaults_to_none():
    from datetime import datetime, timezone
    bul = Bulletin(
        operator_id=1, node_id=1, bbs_id="H001",
        category="WX", from_call="W0WX",
        subject="Header only",
        timestamp=datetime.now(timezone.utc),
    )
    assert bul.body is None
    assert bul.wants_retrieval is False


def test_db_migration_adds_wants_retrieval_column(db):
    # Column must exist and accept 0/1
    db._conn.execute("UPDATE bulletins SET wants_retrieval=0 WHERE 1=0")  # no-op but validates column
    # Insert a row and verify the column round-trips
    op = db.insert_operator(Operator(callsign="K0TEST", ssid=0, label="t", is_default=False))
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq"))
    db._conn.execute(
        """INSERT INTO bulletins
           (operator_id, node_id, bbs_id, category, from_call, subject, body,
            timestamp, read, queued, sent, wants_retrieval)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 1)""",
        (op.id, node.id, "H001", "WX", "W0WX", "Hdr", "",
         "2026-01-01T00:00:00+00:00"),
    )
    db._conn.commit()
    row = db._conn.execute("SELECT wants_retrieval FROM bulletins WHERE bbs_id='H001'").fetchone()
    assert row["wants_retrieval"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_store/test_store.py::test_bulletin_body_defaults_to_none tests/test_store/test_store.py::test_db_migration_adds_wants_retrieval_column -v
```

Expected: `FAILED` — `Bulletin.__init__()` requires positional `body`; `wants_retrieval` column missing.

- [ ] **Step 3: Update `open_packet/store/models.py`**

Replace the `Bulletin` dataclass with:

```python
@dataclass
class Bulletin:
    operator_id: int
    node_id: int
    bbs_id: str
    category: str
    from_call: str
    subject: str
    timestamp: datetime                   # moved before body so Optional body can have a default
    body: Optional[str] = None            # None = header only, not yet retrieved
    read: bool = False
    queued: bool = False
    sent: bool = False
    wants_retrieval: bool = False
    id: Optional[int] = None
    synced_at: Optional[datetime] = None
```

No new imports needed — `Optional` is already imported.

- [ ] **Step 4: Add DB migration in `open_packet/store/database.py`**

After the existing bulletin migrations (after the block that adds `queued` and `sent` columns), add:

```python
        try:
            self._conn.execute(
                "ALTER TABLE bulletins ADD COLUMN wants_retrieval INTEGER NOT NULL DEFAULT 0"
            )
            self._conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_store/test_store.py::test_bulletin_body_defaults_to_none tests/test_store/test_store.py::test_db_migration_adds_wants_retrieval_column -v
```

Expected: `PASSED`.

- [ ] **Step 6: Run the full test suite to catch any regressions from the model reorder**

```bash
uv run pytest -v
```

Expected: all existing tests pass. If `Bulletin(...)` call sites break, they all use keyword args so there should be no failures.

- [ ] **Step 7: Commit**

```bash
git add open_packet/store/models.py open_packet/store/database.py tests/test_store/test_store.py
git commit -m "feat: add wants_retrieval flag and optional body to Bulletin model"
```

---

## Task 2: Store — Header-Only Save and Row Mapping

**Files:**
- Modify: `open_packet/store/store.py`
- Test: `tests/test_store/test_store.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_store/test_store.py`:

```python
def test_save_bulletin_header_only(store):
    """A bulletin with body=None is saved and read back with body=None."""
    s, op, node = store
    from datetime import datetime, timezone
    bul = Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="H002",
        category="WX", from_call="W0WX",
        subject="Header only",
        timestamp=datetime.now(timezone.utc),
        # body omitted — defaults to None
    )
    saved = s.save_bulletin(bul)
    assert saved.id is not None
    assert saved.body is None
    assert saved.wants_retrieval is False


def test_save_bulletin_header_does_not_duplicate(store):
    """Re-saving the same header by bbs_id+node_id returns the existing row."""
    s, op, node = store
    from datetime import datetime, timezone
    bul = Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="H003",
        category="WX", from_call="W0WX",
        subject="Dedup check",
        timestamp=datetime.now(timezone.utc),
    )
    first = s.save_bulletin(bul)
    second = s.save_bulletin(bul)
    assert first.id == second.id
    bulletins = s.list_bulletins(operator_id=op.id)
    assert sum(1 for b in bulletins if b.bbs_id == "H003") == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_store/test_store.py::test_save_bulletin_header_only tests/test_store/test_store.py::test_save_bulletin_header_does_not_duplicate -v
```

Expected: `FAILED` — `save_bulletin` passes `None` to a `NOT NULL` column.

- [ ] **Step 3: Update `save_bulletin` in `open_packet/store/store.py`**

Change the INSERT call to use the empty-string sentinel for `body` and add `wants_retrieval`:

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
                timestamp, read, queued, sent, wants_retrieval, synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                bul.operator_id, bul.node_id, bul.bbs_id, bul.category,
                bul.from_call, bul.subject,
                bul.body if bul.body is not None else "",   # "" = header-only sentinel
                bul.timestamp.isoformat(), int(bul.read),
                int(bul.queued), int(bul.sent),
                int(bul.wants_retrieval),
                None if bul.queued else datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()
        return self._get_bulletin(cur.lastrowid)  # type: ignore
```

- [ ] **Step 4: Update `_row_to_bulletin` in `open_packet/store/store.py`**

Map the empty-string sentinel back to `None` and add `wants_retrieval`:

```python
    def _row_to_bulletin(self, row) -> Bulletin:
        return Bulletin(
            id=row["id"], operator_id=row["operator_id"], node_id=row["node_id"],
            bbs_id=row["bbs_id"], category=row["category"], from_call=row["from_call"],
            subject=row["subject"],
            body=row["body"] if row["body"] else None,   # "" sentinel → None
            timestamp=datetime.fromisoformat(row["timestamp"]),
            read=bool(row["read"]),
            queued=bool(row["queued"]),
            sent=bool(row["sent"]),
            wants_retrieval=bool(row["wants_retrieval"]),
            synced_at=datetime.fromisoformat(row["synced_at"]) if row["synced_at"] else None,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_store/test_store.py::test_save_bulletin_header_only tests/test_store/test_store.py::test_save_bulletin_header_does_not_duplicate -v
```

Expected: `PASSED`.

- [ ] **Step 6: Run the full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add open_packet/store/store.py tests/test_store/test_store.py
git commit -m "feat: store bulletin headers with empty-string body sentinel, map to None on read"
```

---

## Task 3: Store — Retrieval Methods

**Files:**
- Modify: `open_packet/store/store.py`
- Test: `tests/test_store/test_store.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_store/test_store.py`:

```python
def test_mark_bulletin_wants_retrieval(store):
    s, op, node = store
    from datetime import datetime, timezone
    bul = Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="H010",
        category="WX", from_call="W0WX", subject="Queue me",
        timestamp=datetime.now(timezone.utc),
    )
    saved = s.save_bulletin(bul)
    assert saved.wants_retrieval is False

    s.mark_bulletin_wants_retrieval(saved.id)

    pending = s.list_bulletins_pending_retrieval(node_id=node.id)
    assert len(pending) == 1
    assert pending[0].id == saved.id
    assert pending[0].body is None


def test_list_bulletins_pending_retrieval_excludes_retrieved(store):
    """A bulletin with a body is not returned as pending, even if wants_retrieval=1."""
    s, op, node = store
    from datetime import datetime, timezone
    bul = Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="H011",
        category="WX", from_call="W0WX", subject="Already got it",
        body="Full body here",
        timestamp=datetime.now(timezone.utc),
    )
    saved = s.save_bulletin(bul)
    s.mark_bulletin_wants_retrieval(saved.id)  # shouldn't matter — body is present

    pending = s.list_bulletins_pending_retrieval(node_id=node.id)
    assert all(b.id != saved.id for b in pending)


def test_update_bulletin_body(store):
    s, op, node = store
    from datetime import datetime, timezone
    bul = Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="H012",
        category="WX", from_call="W0WX", subject="Fetch me",
        timestamp=datetime.now(timezone.utc),
    )
    saved = s.save_bulletin(bul)
    assert saved.body is None
    assert saved.synced_at is None

    s.update_bulletin_body(saved.id, "This is the full bulletin body.")

    updated = s._get_bulletin(saved.id)
    assert updated.body == "This is the full bulletin body."
    assert updated.synced_at is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_store/test_store.py::test_mark_bulletin_wants_retrieval tests/test_store/test_store.py::test_list_bulletins_pending_retrieval_excludes_retrieved tests/test_store/test_store.py::test_update_bulletin_body -v
```

Expected: `FAILED` — methods do not exist.

- [ ] **Step 3: Add the three methods to `open_packet/store/store.py`**

Add after `mark_bulletin_sent`:

```python
    def mark_bulletin_wants_retrieval(self, id: int) -> None:
        assert self._conn
        self._conn.execute("UPDATE bulletins SET wants_retrieval=1 WHERE id=?", (id,))
        self._conn.commit()

    def list_bulletins_pending_retrieval(self, node_id: int) -> list[Bulletin]:
        """Bulletins marked for retrieval whose body has not yet been fetched."""
        assert self._conn
        rows = self._conn.execute(
            "SELECT * FROM bulletins WHERE node_id=? AND wants_retrieval=1 AND body=''",
            (node_id,),
        ).fetchall()
        return [self._row_to_bulletin(r) for r in rows]

    def update_bulletin_body(self, id: int, body: str) -> None:
        assert self._conn
        self._conn.execute(
            "UPDATE bulletins SET body=?, synced_at=? WHERE id=?",
            (body, datetime.now(timezone.utc).isoformat(), id),
        )
        self._conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_store/test_store.py::test_mark_bulletin_wants_retrieval tests/test_store/test_store.py::test_list_bulletins_pending_retrieval_excludes_retrieved tests/test_store/test_store.py::test_update_bulletin_body -v
```

Expected: `PASSED`.

- [ ] **Step 5: Run the full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add open_packet/store/store.py tests/test_store/test_store.py
git commit -m "feat: add mark_bulletin_wants_retrieval, list_bulletins_pending_retrieval, update_bulletin_body"
```

---

## Task 4: Engine — Header-Only Phase 4 + Body Retrieval Phase 5

**Files:**
- Modify: `open_packet/engine/engine.py`
- Test: `tests/test_engine/test_engine.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_engine/test_engine.py`:

```python
def test_check_mail_saves_bulletin_headers_only(db_and_store):
    """Phase 4 saves header-only bulletin rows; read_bulletin is NOT called."""
    db, store, op, node_record = db_and_store
    mock_node = make_mock_node(
        bulletins=[
            MessageHeader(bbs_id="B1", to_call="WX", from_call="W0WX",
                          subject="Storm warning", date_str="04/06"),
        ]
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

    # read_bulletin must NOT be called — we only listed headers
    mock_node.read_bulletin.assert_not_called()

    # Header must be stored with body=None
    bulletins = store.list_bulletins(operator_id=op.id)
    assert len(bulletins) == 1
    assert bulletins[0].bbs_id == "B1"
    assert bulletins[0].body is None
    assert bulletins[0].wants_retrieval is False


def test_check_mail_retrieves_body_for_queued_bulletins(db_and_store):
    """Phase 5 calls read_bulletin for bulletins where wants_retrieval=True."""
    db, store, op, node_record = db_and_store

    # Pre-populate a header-only bulletin marked for retrieval
    from datetime import datetime, timezone
    from open_packet.store.models import Bulletin as BulletinModel
    pre = store.save_bulletin(BulletinModel(
        operator_id=op.id, node_id=node_record.id, bbs_id="B2",
        category="WX", from_call="W0WX", subject="Pre-existing header",
        timestamp=datetime.now(timezone.utc),
    ))
    store.mark_bulletin_wants_retrieval(pre.id)

    mock_node = make_mock_node(bulletins=[])  # listing returns nothing new
    mock_node.read_bulletin.return_value = NodeMessage(
        header=MagicMock(bbs_id="B2"), body="Full storm bulletin body."
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

    mock_node.read_bulletin.assert_called_once_with("B2")

    updated = store._get_bulletin(pre.id)
    assert updated.body == "Full storm bulletin body."
    assert updated.synced_at is not None

    sync_events = [e for e in events if isinstance(e, SyncCompleteEvent)]
    assert len(sync_events) == 1
    assert sync_events[0].bulletins_retrieved == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_engine/test_engine.py::test_check_mail_saves_bulletin_headers_only tests/test_engine/test_engine.py::test_check_mail_retrieves_body_for_queued_bulletins -v
```

Expected: `FAILED` — current engine calls `read_bulletin` for every new bulletin.

- [ ] **Step 3: Replace Phase 4 in `open_packet/engine/engine.py`**

In `_run_sync_phases`, replace the entire "Phase 4: Retrieve bulletins" block with:

```python
        # Phase 4: Save bulletin headers (body not retrieved yet)
        self._set_status(ConnectionStatus.SYNCING, "Listing bulletins…")
        bulletin_headers = node.list_bulletins()
        self._emit(ConsoleEvent(">", f"Listing bulletins ({len(bulletin_headers)} available)"))
        for header in bulletin_headers:
            if not self._store.bulletin_exists(header.bbs_id, self._node_record.id):
                self._store.save_bulletin(Bulletin(
                    operator_id=self._operator.id,
                    node_id=self._node_record.id,
                    bbs_id=header.bbs_id,
                    category=header.to_call,
                    from_call=header.from_call,
                    subject=header.subject,
                    timestamp=datetime.now(timezone.utc),
                ))

        # Phase 5: Retrieve bodies for bulletins queued by the user
        pending = self._store.list_bulletins_pending_retrieval(self._node_record.id)
        bulletins_retrieved = 0
        total_pending = len(pending)
        for i, bul in enumerate(pending, 1):
            self._set_status(ConnectionStatus.SYNCING, f"Retrieving bulletin {i} of {total_pending}")
            try:
                raw = node.read_bulletin(bul.bbs_id)
            except Exception:
                logger.exception("Failed to retrieve bulletin %s", bul.bbs_id)
                self._emit(ConsoleEvent("!", f"Failed to retrieve bulletin {bul.bbs_id}"))
                continue
            self._store.update_bulletin_body(bul.id, raw.body)
            bulletins_retrieved += 1
            self._emit(ConsoleEvent("<", f"[{bul.bbs_id}] {bul.subject} from {bul.from_call}"))

        return retrieved, sent, bulletins_retrieved
```

(Remove the old `return retrieved, sent, bulletins_retrieved` line that was before this block, since it is now at the end of Phase 5.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_engine/test_engine.py::test_check_mail_saves_bulletin_headers_only tests/test_engine/test_engine.py::test_check_mail_retrieves_body_for_queued_bulletins -v
```

Expected: `PASSED`.

- [ ] **Step 5: Run the full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add open_packet/engine/engine.py tests/test_engine/test_engine.py
git commit -m "feat: sync saves bulletin headers only; retrieve bodies on demand"
```

---

## Task 5: Guard Exporter Against Header-Only Bulletins

**Files:**
- Modify: `open_packet/store/exporter.py`
- Test: `tests/test_store/test_store.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_store/test_store.py`:

```python
def test_export_bulletins_skips_header_only(store, tmp_path):
    """export_bulletins must not write a file for a bulletin with body=None."""
    s, op, node = store
    from datetime import datetime, timezone
    from open_packet.store.exporter import export_bulletins

    # header-only (body=None)
    bul = Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="H020",
        category="WX", from_call="W0WX", subject="Header skip",
        timestamp=datetime(2026, 4, 6, 12, 0, 0, tzinfo=timezone.utc),
    )
    saved = s.save_bulletin(bul)

    export_bulletins([saved], base_path=str(tmp_path))

    wx_dir = tmp_path / "bulletins" / "WX"
    assert not wx_dir.exists() or len(list(wx_dir.iterdir())) == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_store/test_store.py::test_export_bulletins_skips_header_only -v
```

Expected: `FAILED` — `f.write(bul.body)` raises `TypeError` on `None`.

- [ ] **Step 3: Guard against `body is None` in `open_packet/store/exporter.py`**

In `export_bulletins`, add a guard at the start of the loop:

```python
def export_bulletins(bulletins: list[Bulletin], base_path: str) -> None:
    for bul in bulletins:
        if bul.body is None:
            continue  # header-only; body not yet retrieved
        folder = os.path.join(base_path, "bulletins", bul.category.upper())
        os.makedirs(folder, exist_ok=True)
        date_str = bul.timestamp.strftime("%Y-%m-%d") if bul.timestamp else "0000-00-00"
        safe_subject = "".join(c if c.isalnum() or c in "-_ " else "_" for c in bul.subject)[:40]
        filename = f"{date_str}-{bul.bbs_id}-{safe_subject}.txt".replace(" ", "-")
        path = os.path.join(folder, filename)
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write(f"Category: {bul.category}\n")
                f.write(f"From:     {bul.from_call}\n")
                f.write(f"Subject:  {bul.subject}\n")
                f.write(f"Date:     {bul.timestamp.isoformat() if bul.timestamp else ''}\n")
                f.write("-" * 40 + "\n")
                f.write(bul.body)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_store/test_store.py::test_export_bulletins_skips_header_only -v
```

Expected: `PASSED`.

- [ ] **Step 5: Run the full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add open_packet/store/exporter.py tests/test_store/test_store.py
git commit -m "fix: skip header-only bulletins in export_bulletins"
```

---

## Task 6: TUI — Key Binding and Queue Retrieval Action

**Files:**
- Modify: `open_packet/ui/tui/screens/main.py`
- Modify: `open_packet/ui/tui/app.py`

- [ ] **Step 1: Add binding to `open_packet/ui/tui/screens/main.py`**

In `MainScreen.BINDINGS`, add:

```python
Binding("r", "queue_bulletin_retrieval", "Queue Retrieval", priority=True),
```

At the end of the method definitions, add:

```python
    def action_queue_bulletin_retrieval(self) -> None:
        self.app.queue_bulletin_retrieval()
```

- [ ] **Step 2: Add `queue_bulletin_retrieval` to `open_packet/ui/tui/app.py`**

Add after `delete_selected_message`:

```python
    def queue_bulletin_retrieval(self) -> None:
        msg = self._selected_message
        if not isinstance(msg, Bulletin) or msg.body is not None or not self._store:
            return
        self._store.mark_bulletin_wants_retrieval(msg.id)
        self._refresh_message_list()
```

- [ ] **Step 3: Manually verify**

```bash
uv run open-packet test.yaml
```

Navigate to a bulletin category in the folder tree. Select a header-only bulletin (body=None). Press `r`. Verify the folder counts refresh. On next sync the body should be retrieved.

- [ ] **Step 4: Commit**

```bash
git add open_packet/ui/tui/screens/main.py open_packet/ui/tui/app.py
git commit -m "feat: add r binding to queue bulletin body retrieval"
```

---

## Task 7: TUI — MessageBody Placeholder and MessageList Dim

**Files:**
- Modify: `open_packet/ui/tui/widgets/message_body.py`
- Modify: `open_packet/ui/tui/widgets/message_list.py`
- Modify: `open_packet/ui/tui/app.py`

- [ ] **Step 1: Update `show_message` in `open_packet/ui/tui/widgets/message_body.py`**

Add `node_label: str = ""` parameter and handle `body is None`:

```python
    def show_message(self, message: Message | Bulletin, node_label: str = "") -> None:
        self.clear()
        self.write(f"From:    {message.from_call}")
        if isinstance(message, Bulletin):
            self.write(f"Category: {message.category}")
            if message.body is None:
                self.write("─" * 40)
                source = node_label or f"node #{message.node_id}"
                self.write(f"[dim]Not retrieved — source: {source}[/dim]")
                self.write("[dim]Press r to queue for next sync.[/dim]")
                return
        else:
            self.write(f"To:      {message.to_call}")
        self.write(f"Subject: {message.subject}")
        self.write("─" * 40)
        self.write(message.body)
```

- [ ] **Step 2: Pass `node_label` from `open_packet/ui/tui/app.py`**

In `on_message_list_message_selected`, replace:

```python
        try:
            self.query_one("MessageBody").show_message(event.message)
        except Exception:
            pass
```

with:

```python
        try:
            node_label = ""
            if isinstance(event.message, Bulletin) and event.message.body is None and self._store:
                nodes = {n.id: n.label for n in self._store.list_nodes()}
                node_label = nodes.get(event.message.node_id, f"node #{event.message.node_id}")
            self.query_one("MessageBody").show_message(event.message, node_label=node_label)
        except Exception:
            pass
```

- [ ] **Step 3: Dim header-only rows in `open_packet/ui/tui/widgets/message_list.py`**

Add `from rich.text import Text` at the top (it is not yet imported). Then in `load_messages`, apply dim styling for pending bulletins:

```python
from rich.text import Text

# inside load_messages:
    def load_messages(self, messages: list[Message | Bulletin]) -> None:
        self._loading = True
        self.clear()
        self._messages = messages
        for msg in messages:
            read_marker = " " if msg.read else "●"
            sent_str = msg.timestamp.strftime("%m/%d %H:%M") if msg.timestamp else "—"
            retrieved_str = msg.synced_at.strftime("%m/%d %H:%M") if msg.synced_at else "—"
            is_pending = isinstance(msg, Bulletin) and msg.body is None
            if is_pending:
                self.add_row(
                    read_marker,
                    Text(msg.subject[:40], style="dim"),
                    Text(msg.from_call, style="dim"),
                    sent_str,
                    retrieved_str,
                )
            else:
                self.add_row(read_marker, msg.subject[:40], msg.from_call, sent_str, retrieved_str)
        self.call_after_refresh(self._finish_loading)
```

- [ ] **Step 4: Manually verify**

```bash
uv run open-packet test.yaml
```

Confirm:
- Pending bulletin rows appear dimmed in the message list
- Selecting a pending bulletin shows the placeholder with source node name and `r` hint
- Fully-retrieved bulletins (body present) show normally

- [ ] **Step 5: Run the full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add open_packet/ui/tui/widgets/message_body.py open_packet/ui/tui/widgets/message_list.py open_packet/ui/tui/app.py
git commit -m "feat: dim pending bulletin rows; show source node placeholder when body not retrieved"
```
