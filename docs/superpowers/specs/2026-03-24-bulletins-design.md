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

Schema migration in `Database.initialize()` adds both columns using the established `ALTER TABLE ... ADD COLUMN` / `except sqlite3.OperationalError: pass` pattern:

```python
for sql in [
    "ALTER TABLE bulletins ADD COLUMN queued INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE bulletins ADD COLUMN sent INTEGER NOT NULL DEFAULT 0",
]:
    try:
        self._conn.execute(sql)
    except sqlite3.OperationalError:
        pass
```

---

## Store (`open_packet/store/store.py`)

### `list_outbox(operator_id: int) -> list[Message | Bulletin]`

Extended to return both queued messages and queued bulletins in a single list, ordered by timestamp. The existing message query is unchanged; a second query fetches bulletins where `queued=1 AND sent=0` for the same `operator_id`. Results from both queries are merged and sorted by `timestamp`.

Return type becomes `list[Message | Bulletin]` (union type).

### `count_folder_stats(operator_id: int) -> dict`

Extended to include per-category bulletin counts. Current return shape:

```python
{
    "Inbox": (total, unread),
    "Sent": (total,),
    "Outbox": (total,),
}
```

New return shape:

```python
{
    "Inbox": (total, unread),
    "Sent": (total,),
    "Outbox": (total,),                          # includes pending bulletins
    "Bulletins": {                                # new key
        "WX": (total, unread),
        "NTS": (total, unread),
        # ... all categories present in DB
    },
}
```

The Outbox total includes pending bulletins (`queued=1 AND sent=0`) from both the `messages` and `bulletins` tables.

### `save_bulletin()` — no change needed

The existing `save_bulletin()` deduplicates by `(bbs_id, node_id)`. Outgoing bulletins use a unique local `bbs_id` so they are always inserted fresh.

### `mark_bulletin_sent(bulletin_id: int) -> None` — new method

Sets `sent=1` for the given bulletin `id`. Called by the engine after successful transmission.

---

## Node Layer

### `open_packet/node/base.py`

Add abstract method:

```python
@abstractmethod
def post_bulletin(self, category: str, subject: str, body: str) -> None:
    ...
```

### `open_packet/node/bpq.py`

Implement `post_bulletin()`. The BPQ32 bulletin posting protocol mirrors message sending:

1. Send `SB {category}\r`
2. Wait for subject prompt (response ending with `>`)
3. Send `{subject}\r`
4. Wait for body/enter-message prompt
5. Send `{body}\r/EX\r`
6. Wait for confirmation (response ending with `>`)

```python
def post_bulletin(self, category: str, subject: str, body: str) -> None:
    self._connection.send(f"SB {category}\r")
    self._wait_for_prompt()          # waits for ">" prompt
    self._connection.send(f"{subject}\r")
    self._wait_for_prompt()
    self._connection.send(f"{body}\r/EX\r")
    self._wait_for_prompt()
```

The `_wait_for_prompt()` helper already exists (used in `send_message()`).

---

## Engine (`open_packet/engine/`)

### `commands.py`

New command:

```python
@dataclass
class PostBulletinCommand:
    category: str
    subject: str
    body: str
```

### `events.py`

`SyncCompleteEvent` gains one new field:

```python
@dataclass
class SyncCompleteEvent:
    messages_retrieved: int
    messages_sent: int
    bulletins_retrieved: int = 0     # new, default 0 for backwards compat
```

### `engine.py` — `_do_check_mail()`

**Bulletin send phase** (runs before retrieval, inline with message sends):

After the existing message-send loop, add:

```python
for bulletin in self._store.list_outbox_bulletins(operator_id):
    self._node.post_bulletin(bulletin.category, bulletin.subject, bulletin.body)
    self._store.mark_bulletin_sent(bulletin.id)
    self._evt_queue.put(ConsoleEvent(direction="TX", text=f"SB {bulletin.category}"))
```

Note: `list_outbox_bulletins()` is a private store helper that returns only bulletins (not messages) from the outbox, used here to avoid re-sending messages.

**Bulletin retrieval phase** (runs after message retrieval):

```python
headers = self._node.list_bulletins()
bulletins_retrieved = 0
for header in headers:
    if self._store.bulletin_exists(header.bbs_id, node_id):
        continue
    raw = self._node.read_bulletin(header.bbs_id)
    bulletin = Bulletin(
        operator_id=operator_id,
        node_id=node_id,
        bbs_id=header.bbs_id,
        category=header.to_call,    # BPQ puts category in the to_call field for LB output
        from_call=header.from_call,
        subject=header.subject,
        body=raw.body,
        timestamp=parse_date(header.date_str),
    )
    self._store.save_bulletin(bulletin)
    bulletins_retrieved += 1
    self._evt_queue.put(ConsoleEvent(direction="RX", text=f"Bulletin {header.bbs_id}"))
```

`SyncCompleteEvent` updated to include `bulletins_retrieved`.

### `engine.py` — `_do_post_bulletin(cmd: PostBulletinCommand)`

New handler. Saves the bulletin to the outbox immediately (does not transmit — transmission happens in next check mail):

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
    self._evt_queue.put(MessageQueuedEvent())    # reuse existing event to trigger outbox refresh
```

### Store helper: `bulletin_exists(bbs_id, node_id) -> bool`

New method on `Store` to check deduplication before fetching full body. Avoids redundant `read_bulletin()` calls on repeated syncs.

---

## TUI

### New `ComposeBulletinScreen` (`open_packet/ui/tui/screens/compose_bulletin.py`)

Separate from `ComposeScreen`. Fields:
- `category` — single-line `Input` (free text, e.g. "WX")
- `subject` — single-line `Input`
- `body` — multi-line `TextArea`

Submit → `dismiss(PostBulletinCommand(category, subject, body))`
Cancel → `dismiss(None)`

### `open_packet/ui/tui/screens/main.py`

New keybinding: `("b", "new_bulletin", "Bulletin")` alongside existing `("n", "new_message", "New")`.

### `open_packet/ui/tui/app.py`

- `open_compose_bulletin()` pushes `ComposeBulletinScreen`, callback `_on_compose_bulletin_result()`
- `_on_compose_bulletin_result(result)` puts `PostBulletinCommand` on the command queue (if not None)
- `_handle_event()` updated: `SyncCompleteEvent` notification now reads `f"Sync complete: {event.messages_retrieved} new messages, {event.bulletins_retrieved} new bulletins, {event.messages_sent} sent"`
- `_handle_event()` refreshes message list on `MessageQueuedEvent` (already does this — outbox refresh works for bulletins without change since `list_outbox` is extended)
- Engine dispatch: `PostBulletinCommand` added to the command routing in the engine's main loop

### `open_packet/ui/tui/widgets/folder_tree.py`

**Remove** hardcoded `_wx_node`, `_nts_node`, `_all_node` and their construction in `_build_tree()`.

**Add** a `_bulletin_nodes: dict[str, TreeNode]` dict to track dynamically created category nodes under the Bulletins parent.

`update_counts(stats)` extended: when `stats["Bulletins"]` is present, reconcile the category subtree:
- For each `(category, (total, unread))` in the new stats: add a child node if it doesn't exist, update its label
- Remove any child nodes whose category is no longer in the stats
- Label format matches Inbox: plain `"WX"` if total=0, `"WX (5)"` if total>0 and all read, `"WX (5/2 new)"` if unread>0

Folder selection for bulletin categories continues to emit `FolderSelected(folder="Bulletins", category=category)`.

---

## Error / Edge Cases

- **No bulletins on BBS:** `list_bulletins()` returns empty list; bulletin retrieval phase is a no-op
- **Bulletin body fetch fails:** Log to console, skip that bulletin (same pattern as message fetch errors)
- **Post fails during check mail:** Log error to console, bulletin remains `queued=True, sent=False` and retried on next sync
- **Category field empty on compose:** Validate before dismissing — empty category is not allowed

---

## Files Changed

| File | Change |
|------|--------|
| `open_packet/store/models.py` | Add `queued`, `sent` fields to `Bulletin` |
| `open_packet/store/database.py` | Migration: add `queued`/`sent` columns to `bulletins` table |
| `open_packet/store/store.py` | Extend `list_outbox()`, `count_folder_stats()`; add `mark_bulletin_sent()`, `bulletin_exists()`, `list_outbox_bulletins()` |
| `open_packet/node/base.py` | Abstract `post_bulletin()` method |
| `open_packet/node/bpq.py` | Implement `post_bulletin()` |
| `open_packet/engine/commands.py` | Add `PostBulletinCommand` |
| `open_packet/engine/events.py` | Add `bulletins_retrieved` to `SyncCompleteEvent` |
| `open_packet/engine/engine.py` | Add bulletin send/retrieve phases to `_do_check_mail()`; add `_do_post_bulletin()` handler |
| `open_packet/ui/tui/screens/compose_bulletin.py` | New compose screen |
| `open_packet/ui/tui/screens/main.py` | Add `b` keybinding |
| `open_packet/ui/tui/app.py` | Compose bulletin flow; updated sync notification; command dispatch |
| `open_packet/ui/tui/widgets/folder_tree.py` | Dynamic bulletin category nodes with counts |

## Out of Scope

- Bulletin deletion
- Marking individual bulletins as read/unread from the UI
- Configuring which categories to subscribe to
- Bulletin reply
