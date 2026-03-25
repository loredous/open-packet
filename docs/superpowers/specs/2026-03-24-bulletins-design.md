# Bulletin Retrieval and Posting

**Date:** 2026-03-24
**Status:** Approved

## Summary

Add support for retrieving and posting bulletins. Retrieval is wired into the existing Check Mail flow. Posting uses the same outbox model as messages: a `PostBulletinCommand` saves a queued bulletin to the DB, and it is transmitted inline during the next Check Mail. The folder tree displays dynamic per-category bulletin counts based on what has been retrieved.

## Scope

Two sub-features sharing a common model/store foundation:

1. **Retrieve** — engine calls `list_bulletins()` + `read_bulletin()` during `_do_check_mail`, saves results, emits events
2. **Post** — new `ComposeBulletinScreen`, `PostBulletinCommand`, BPQ `SB` protocol, inline send during check mail

---

## Data Model (`open_packet/store/models.py`)

`Bulletin` gains two new fields, matching the `Message` state matrix:

```python
queued: bool = False
sent: bool = False
```

**Bulletin state matrix:**

| Type | `queued` | `sent` |
|------|----------|--------|
| Received from BBS | 0 | 0 |
| Composed, awaiting send | 1 | 0 |
| Composed, transmitted | 1 | 1 |

Outgoing bulletins use a locally-generated `bbs_id` of the form `f"OUT-{uuid4().hex[:8]}"` to avoid collisions with BBS-assigned IDs.

---

## Database (`open_packet/store/database.py`)

Schema migration in `Database.initialize()` adds both columns using the established `ALTER TABLE ... ADD COLUMN` / `except sqlite3.OperationalError: pass` pattern (using `self._conn.execute()`, never `executescript()`):

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

---

## Store (`open_packet/store/store.py`)

### `save_bulletin(bul: Bulletin) -> Bulletin` — updated

Two changes required:

**1. Add `if not bul.queued` guard** (matching the pattern in `save_message()`): the dedup SELECT only runs for received bulletins; outgoing bulletins (`queued=True`) skip it and are always inserted fresh.

**2. Update the INSERT** to include `queued` and `sent` columns, followed by `commit()` and `return` (matching the existing pattern):

```python
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

### `_row_to_bulletin(row) -> Bulletin` — updated

Must map the new columns:

```python
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

### `list_outbox(operator_id: int) -> list[Message | Bulletin]` — updated

Extended to return both queued messages and queued bulletins in a single list for TUI display. The existing message query is unchanged; a second query fetches bulletins where `queued=1 AND sent=0`. Results are merged and sorted by `timestamp` ascending.

Return type becomes `list[Message | Bulletin]`.

### `list_outbox_messages(operator_id: int) -> list[Message]` — new

Internal helper used only by the engine's message-send phase. Returns only `Message` objects where `queued=1 AND sent=0 AND deleted=0`, ordered by `timestamp ASC`. Mirrors `list_outbox_bulletins()` — together they replace the engine's direct use of `list_outbox()` so neither send loop needs `isinstance` checks.

### `list_outbox_bulletins(operator_id: int) -> list[Bulletin]` — new

Internal helper used only by the engine's bulletin-send phase. Returns only `Bulletin` objects where `queued=1 AND sent=0`, ordered by `timestamp ASC`. Keeps the engine's message-send and bulletin-send loops type-safe without needing `isinstance` checks.

### `count_folder_stats(operator_id: int) -> dict[str, tuple | dict]` — updated

Extended to include per-category bulletin counts. New return shape:

```python
{
    "Inbox": (total, unread),
    "Sent":  (total,),
    "Outbox": (total,),          # includes pending bulletins from both tables
    "Bulletins": {               # new key; all categories present in DB
        "WX": (total, unread),
        "NTS": (total, unread),
        ...
    },
}
```

The Outbox count queries both tables:
- messages: `queued=1 AND sent=0 AND deleted=0`
- bulletins: `queued=1 AND sent=0`

The Bulletins dict is built from a `SELECT category, COUNT(*), SUM(CASE WHEN read=0 THEN 1 ELSE 0 END) FROM bulletins WHERE operator_id=? AND queued=0 GROUP BY category`.

### `list_bulletins(operator_id: int, category: Optional[str]) -> list[Bulletin]` — updated

Add `AND queued=0` to the WHERE clause so that outgoing bulletins sitting in the outbox do not appear in the Bulletins category folder view. Without this filter, a pending bulletin would be visible in its category folder before transmission.

### `mark_bulletin_sent(bulletin_id: int) -> None` — new

Sets `sent=1` for the given bulletin `id`. Called by the engine after successful transmission.

```python
def mark_bulletin_sent(self, id: int) -> None:
    self._conn.execute("UPDATE bulletins SET sent=1 WHERE id=?", (id,))
    self._conn.commit()
```

### `bulletin_exists(bbs_id: str, node_id: int) -> bool` — new

Returns `True` if a bulletin with the given `(bbs_id, node_id)` pair already exists in the DB. Used by the engine *before* calling `read_bulletin()` (the network call), so that already-known bulletins are skipped without incurring a BBS round-trip. The dedup check inside `save_bulletin()` remains as a safety net.

```python
def bulletin_exists(self, bbs_id: str, node_id: int) -> bool:
    row = self._conn.execute(
        "SELECT id FROM bulletins WHERE bbs_id=? AND node_id=?",
        (bbs_id, node_id),
    ).fetchone()
    return row is not None
```

---

## Node Layer

### `open_packet/node/base.py`

`list_bulletins()` and `read_bulletin()` already exist as abstract methods in `NodeBase`. Only `post_bulletin()` is missing and must be added:

```python
@abstractmethod
def post_bulletin(self, category: str, subject: str, body: str) -> None:
    ...
```

### `open_packet/node/bpq.py`

Implement `post_bulletin()`. The BPQ32 bulletin posting protocol mirrors `send_message()` exactly, replacing `S {to_call}` with `SB {category}`. The helper used throughout is `_recv_until_prompt()` (not `_wait_for_prompt` — no such method exists):

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

Body lines are sent one at a time (same as `send_message()`). `/EX` is sent as a separate `_send_text` call, not concatenated with the body.

---

## Engine (`open_packet/engine/`)

### `commands.py`

New command, added to the `Command` union type:

```python
@dataclass
class PostBulletinCommand:
    category: str
    subject: str
    body: str

Command = (ConnectCommand | DisconnectCommand | CheckMailCommand
           | SendMessageCommand | DeleteMessageCommand | PostBulletinCommand)
```

### `events.py`

`SyncCompleteEvent` gains one new field (default `0` for backwards compatibility):

```python
@dataclass
class SyncCompleteEvent:
    messages_retrieved: int
    messages_sent: int
    bulletins_retrieved: int = 0
```

### `engine.py` — `_handle()`

Add dispatch for the new command:

```python
elif isinstance(cmd, PostBulletinCommand):
    self._do_post_bulletin(cmd)
```

### `engine.py` — `_do_check_mail()` phase ordering

The complete phase sequence (phases 3 and 4 are new):

1. **Retrieve messages** — `list_messages()` + `read_message()` per header (existing)
2. **Send queued messages** — `list_outbox()` messages, `send_message()` per item (existing; see note below)
3. **Send queued bulletins** — new, after message sends
4. **Retrieve bulletins** — new, after bulletin sends

**Note on phase 2:** Replace the existing `list_outbox()` call in phase 2 with `list_outbox_messages()`. This keeps the message-send loop unchanged and type-safe, since `list_outbox_messages()` returns only `Message` objects. The existing loop body (`m.to_call`, `m.subject`, `m.body`) requires no other changes.

**Phase 3 — bulletin sends:**

```python
pending_bulletins = self._store.list_outbox_bulletins(self._operator.id)
for bul in pending_bulletins:
    self._emit(ConsoleEvent(">", f"Posting bulletin to {bul.category}: {bul.subject}"))
    self._node.post_bulletin(bul.category, bul.subject, bul.body)
    self._store.mark_bulletin_sent(bul.id)
```

**Phase 4 — bulletin retrieval:**

```python
bulletin_headers = self._node.list_bulletins()
bulletins_retrieved = 0
for header in bulletin_headers:
    if self._store.bulletin_exists(header.bbs_id, self._node_record.id):
        continue
    raw = self._node.read_bulletin(header.bbs_id)
    bulletin = Bulletin(
        operator_id=self._operator.id,
        node_id=self._node_record.id,
        bbs_id=header.bbs_id,
        category=header.to_call,   # BPQ puts category in the to_call field for LB output
        from_call=header.from_call,
        subject=header.subject,
        body=raw.body,
        timestamp=datetime.now(timezone.utc),
    )
    self._store.save_bulletin(bulletin)
    bulletins_retrieved += 1
    self._emit(ConsoleEvent("<", f"[{header.bbs_id}] {header.subject} from {header.from_call}"))
```

`SyncCompleteEvent` emitted at end includes `bulletins_retrieved`.

### `engine.py` — `_do_post_bulletin(cmd: PostBulletinCommand)` — new

Saves the bulletin to the outbox; transmission happens during the next `_do_check_mail`:

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
    self._emit(MessageQueuedEvent())   # reuse to trigger outbox refresh in TUI
```

---

## TUI

### New `ComposeBulletinScreen` (`open_packet/ui/tui/screens/compose_bulletin.py`)

Separate from `ComposeScreen`. Fields:
- `category` — single-line `Input` (free text, e.g. "WX")
- `subject` — single-line `Input`
- `body` — multi-line `TextArea`

Validation: `category` must not be empty; show an error and do not dismiss if blank.

Submit → `dismiss(PostBulletinCommand(category, subject, body))`
Cancel → `dismiss(None)`

### `open_packet/ui/tui/screens/main.py`

New keybinding: `("b", "new_bulletin", "Bulletin")` alongside existing `("n", "new_message", "New")`.

### `open_packet/ui/tui/app.py`

- `open_compose_bulletin()` pushes `ComposeBulletinScreen`, callback `_on_compose_bulletin_result()`
- `_on_compose_bulletin_result(result)` puts `PostBulletinCommand` on the command queue (if not None)
- `_handle_event()` updated: `SyncCompleteEvent` notification text becomes:
  `f"Sync complete: {event.messages_retrieved} new, {event.bulletins_retrieved} bulletins, {event.messages_sent} sent"`
  (matches existing "new" phrasing, adding a bulletins count)
- `MainScreen.action_new_bulletin()` → calls `self.app.open_compose_bulletin()`
- `_handle_event()` already calls `_refresh_message_list()` on `SyncCompleteEvent`, which refreshes bulletin counts in the folder tree. Folder tree category counts therefore update only at sync completion — not incrementally during retrieval. This is acceptable and intentional.
- `_refresh_message_list()` already passes the result of `list_outbox()` directly to `msg_list.load_messages()` for the Outbox folder. Since `list_outbox()` now returns `list[Message | Bulletin]`, update the `load_messages()` type annotation in `MessageList` from `list[Message]` to `list[Message | Bulletin]`. No other changes to `MessageList` are needed: `Bulletin` has `read`, `subject`, `from_call`, and `timestamp` fields, which are all the columns it renders.
- `MessageBody.show_message()` currently accesses `message.to_call`, which does not exist on `Bulletin`. Update `show_message()` to handle both types: when the item is a `Bulletin`, display `Category: {category}` in place of the `To:` line. Update the type annotation from `message: Message` to `message: Message | Bulletin`.
- `delete_selected_message()` currently passes `self._selected_message` to `DeleteMessageCommand`. Guard against `Bulletin` items: if `self._selected_message` is a `Bulletin`, do nothing (delete is out of scope for bulletins). The simplest check: `if not isinstance(self._selected_message, Message): return`.
- `MessageSelected.__init__` annotation in `MessageList` should be updated from `message: Message` to `message: Message | Bulletin`.

### `open_packet/ui/tui/widgets/folder_tree.py`

**Current state:** Bulletin category nodes are created inline with `bulletins_node.add_leaf(...)` calls (for "WX", "NTS", "ALL") with no named instance attributes holding those nodes.

**Change:** Remove the three hardcoded inline `add_leaf` calls. Add `self._bulletin_nodes: dict[str, TreeNode] = {}` initialized in `on_mount()` alongside the other node attributes (e.g. `self._inbox_node`). The Bulletins parent node (`self._bulletins_node`) is also stored as an instance attribute in `on_mount()` so `update_counts()` can add child nodes to it. Do not use a class-level mutable default.

`update_counts(stats)` extended: when `"Bulletins"` is present in stats, reconcile the subtree:
- For each `(category, (total, unread))` in `stats["Bulletins"]`: if `category` not in `_bulletin_nodes`, add a child leaf to the Bulletins parent and store in `_bulletin_nodes`; then update its label
- Remove child nodes (and their `_bulletin_nodes` entries) for categories no longer in stats
- Label format: plain `"WX"` if total=0 and unread=0; `"WX (5)"` if total>0 and unread=0; `"WX (5/2 new)"` if unread>0

`node.data` for bulletin category nodes stores the category string, so `FolderSelected` events include the category. This is consistent with the existing approach in `folder_tree.py` where `node.data` (not `str(node.label)`) is used for routing.

---

## Error / Edge Cases

- **No bulletins on BBS:** `list_bulletins()` returns empty list; phase 4 is a no-op
- **Bulletin body fetch fails:** Log to console, skip that bulletin (same pattern as existing message error handling)
- **Post fails during check mail:** Log error to console; bulletin remains `queued=True, sent=False` and retried on next sync
- **Empty category in compose:** Validated before dismiss — not allowed

---

## Files Changed

| File | Change |
|------|--------|
| `open_packet/store/models.py` | Add `queued`, `sent` fields to `Bulletin` |
| `open_packet/store/database.py` | Migration: add `queued`/`sent` columns to `bulletins` table |
| `open_packet/store/store.py` | Update `save_bulletin()` (guard + INSERT + `_row_to_bulletin`); update `list_bulletins()` (add `queued=0` filter); extend `list_outbox()`, `count_folder_stats()`; add `list_outbox_messages()`, `list_outbox_bulletins()`, `mark_bulletin_sent()`, `bulletin_exists()` |
| `open_packet/node/base.py` | Abstract `post_bulletin()` method |
| `open_packet/node/bpq.py` | Implement `post_bulletin()` |
| `open_packet/engine/commands.py` | Add `PostBulletinCommand`; update `Command` union |
| `open_packet/engine/events.py` | Add `bulletins_retrieved` to `SyncCompleteEvent` |
| `open_packet/engine/engine.py` | Add bulletin send/retrieve phases to `_do_check_mail()`; add `_do_post_bulletin()` handler; dispatch `PostBulletinCommand` |
| `open_packet/ui/tui/screens/compose_bulletin.py` | New compose screen |
| `open_packet/ui/tui/screens/main.py` | Add `b` keybinding and `action_new_bulletin()` |
| `open_packet/ui/tui/app.py` | Compose bulletin flow; updated sync notification; command dispatch |
| `open_packet/ui/tui/widgets/message_list.py` | Update `load_messages()` and `MessageSelected.__init__` type annotations to `Message \| Bulletin` |
| `open_packet/ui/tui/widgets/message_body.py` | Update `show_message()` to handle `Bulletin` (display `Category:` instead of `To:`); update type annotation |
| `open_packet/ui/tui/widgets/folder_tree.py` | Dynamic bulletin category nodes with counts |

## Out of Scope

- Bulletin deletion
- Marking individual bulletins as read/unread from the UI
- Configuring which categories to subscribe to
- Bulletin reply
