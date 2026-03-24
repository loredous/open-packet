# Outbox Folder & Folder Counts — Design Spec
**Date:** 2026-03-23

## Problem

Two bugs exist in the current message flow, plus two features are requested.

### Bugs

1. **Messages not saved after the first compose.** `Store.save_message()` deduplicates on `(bbs_id, node_id)`. Composed messages all have `bbs_id=""`, so every message after the first silently returns the existing row and is never stored.

2. **Wrong messages sent on sync.** `_do_check_mail()` transmits every message where `not m.sent and not m.deleted`. Received inbox messages default to `sent=False`, so the engine attempts to re-transmit incoming mail back through the BBS.

### Features

- **Outbox folder** — a dedicated TUI folder showing outgoing messages not yet transmitted.
- **Folder counts** — each folder label shows item counts; Inbox shows total and unread count.

---

## Approach

Add a `queued` boolean column to `messages`. A queued message is one composed locally awaiting transmission. Received messages never have this set. This makes the distinction explicit in the schema rather than relying on `bbs_id=""` as an implicit signal.

No backward-compatibility migration is required (single-developer codebase).

**Message state summary after changes:**

| Message type | `queued` | `sent` |
|---|---|---|
| Received from BBS | 0 | 0 |
| Composed, awaiting send | 1 | 0 |
| Composed, transmitted | 1 | 1 |

Transmitted outbox messages (`queued=1, sent=1`) appear in the Sent folder. The Sent folder filter (`if m.sent`) requires no change — it correctly includes these rows.

---

## Data Layer

### `Message` model (`store/models.py`)

Add field:
```python
queued: bool = False
```

### Database schema (`store/database.py`)

Add to `messages` CREATE TABLE statement:
```sql
queued INTEGER NOT NULL DEFAULT 0
```

In `Database.initialize()`, after calling `_create_schema()`, add inline migration using `self._conn.execute()`. Do not use `executescript()` for the migration — `executescript()` issues an implicit `COMMIT` before running, which would interfere with the migration's own transaction. Note that `_create_schema()` itself continues to use `executescript()` and is not changed.
```python
try:
    self._conn.execute(
        "ALTER TABLE messages ADD COLUMN queued INTEGER NOT NULL DEFAULT 0"
    )
    self._conn.commit()
except sqlite3.OperationalError:
    pass  # column already exists
```

### `Store` changes (`store/store.py`)

**Step 1 — `_row_to_message()` (prerequisite):** Add `queued=bool(row["queued"])` to the `Message` construction. This must be done first — without it, every message loaded from the DB will have `queued=False` regardless of the stored value, silently breaking `list_outbox()` and all other queued-message logic.

**Step 2 — `save_message()`:**
- When `msg.queued` is True, skip the bbs_id dedup check entirely so every composed message gets its own row. No dedup is applied to outbox messages (intentional — each compose action is a distinct user intent).
- Update the INSERT statement to include `queued` (add between `deleted` and `synced_at`):

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
        # synced_at=NULL for queued (composed) messages; they were never retrieved from a BBS.
    ),
)
self._conn.commit()
```

**Step 3 — `list_outbox(operator_id)`** — new method:
```sql
SELECT * FROM messages
WHERE operator_id=? AND queued=1 AND sent=0 AND deleted=0
ORDER BY timestamp ASC
```
Note: like `list_messages()`, this filters only by `operator_id`, not `node_id`. In a multi-node setup this means outbox messages for all nodes are returned and transmitted through whichever node the current sync uses. This is a known PoC limitation consistent with the rest of the codebase (see comment in `save_message()`).

**Step 4 — `count_folder_stats(operator_id)`** — new method returning `dict[str, tuple[int, ...]]`. Implemented as a single SQL query using conditional aggregates (returns zeros for empty tables, never raises).

SQL:
```sql
SELECT
    COALESCE(SUM(CASE WHEN queued=0 AND sent=0 AND deleted=0             THEN 1 ELSE 0 END), 0) AS inbox_total,
    COALESCE(SUM(CASE WHEN queued=0 AND sent=0 AND deleted=0 AND read=0  THEN 1 ELSE 0 END), 0) AS inbox_unread,
    COALESCE(SUM(CASE WHEN sent=1 AND deleted=0                          THEN 1 ELSE 0 END), 0) AS sent_total,
    -- Note: received messages always have sent=0 (save_message never sets sent=True for received
    -- messages). Under this invariant, sent=1 implies queued=1. The filter is written without
    -- an explicit queued=1 guard to remain consistent with the _refresh_message_list() Sent filter.
    COALESCE(SUM(CASE WHEN queued=1 AND sent=0 AND deleted=0             THEN 1 ELSE 0 END), 0) AS outbox_count
FROM messages
WHERE operator_id=?
```
`COALESCE(..., 0)` ensures integers (never `None`) are returned even when the table is empty or has no rows matching the predicate.

Return value and tuple positions:
```python
{
    "Inbox":  (row["inbox_total"],  row["inbox_unread"]),  # [0]=total, [1]=unread
    "Sent":   (row["sent_total"],),                        # [0]=total
    "Outbox": (row["outbox_count"],),                      # [0]=count
}
```

`update_counts()` in `FolderTree` unpacks by position keyed on folder name: `stats["Inbox"][0]` is total, `stats["Inbox"][1]` is unread, `stats["Outbox"][0]` is count. Bulletins is not included in the dict (out of scope).

---

## Engine (`engine/engine.py`)

### `events.py`

Add new event and include in the `Event` union:
```python
@dataclass
class MessageQueuedEvent:
    pass

Event = ConnectionStatusEvent | MessageReceivedEvent | SyncCompleteEvent | ErrorEvent | MessageQueuedEvent
```

### `engine.py`

Add `MessageQueuedEvent` to the import from `open_packet.engine.events`.

**`_do_send_message()`** — set `queued=True` and emit `MessageQueuedEvent`:
```python
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

**`_do_check_mail()`** — `sent = 0` is the first line of the outbound block in the source. Remove the entire block including that line and replace it wholesale. The replacement must also initialise `sent = 0`:
```python
# REMOVE this entire block:
outbound = self._store.list_messages(operator_id=self._operator.id)
for m in outbound:
    if not m.sent and not m.deleted:
        self._node.send_message(m.to_call, m.subject, m.body)
        self._store.mark_message_sent(m.id)
        sent += 1
```

Replace with:
```python
sent = 0
outbound = self._store.list_outbox(self._operator.id)
for m in outbound:
    self._node.send_message(m.to_call, m.subject, m.body)
    self._store.mark_message_sent(m.id)
    sent += 1
```

---

## TUI

### `FolderTree` (`ui/tui/widgets/folder_tree.py`)

**Rewrite `on_mount()` and `on_tree_node_selected()` together** — both depend on `node.data` being set; updating one without the other will break Bulletins routing silently.

New `on_mount()`:
```python
def on_mount(self) -> None:
    self.root.expand()
    self._inbox_node  = self.root.add_leaf("Inbox",  data="Inbox")
    self._outbox_node = self.root.add_leaf("Outbox", data="Outbox")
    self._sent_node   = self.root.add_leaf("Sent",   data="Sent")
    bulletins = self.root.add("Bulletins", data="Bulletins")
    bulletins.add_leaf("WX",  data="WX")
    bulletins.add_leaf("NTS", data="NTS")
    bulletins.add_leaf("ALL", data="ALL")
```

New `on_tree_node_selected()` — uses `node.data` so folder name is unaffected by count suffixes in the display label:
```python
def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
    folder = event.node.data or str(event.node.label)
    parent = event.node.parent
    if parent and parent.data == "Bulletins":
        self.post_message(self.FolderSelected("Bulletins", category=folder))
    else:
        self.post_message(self.FolderSelected(folder))
```

**New `update_counts(stats: dict[str, tuple[int, ...]])` method** — calls `node.set_label()` using Rich `Text` objects:

| Condition | Label | Style |
|-----------|-------|-------|
| Inbox: total=0 | `Inbox` | plain |
| Inbox: total>0, unread=0 | `Inbox (5)` | plain |
| Inbox: total>0, unread>0 | `Inbox (10/5)` | only the unread digit (`5`) is bold |
| Outbox: count=0 | `Outbox` | plain, no background |
| Outbox: count>0 | `Outbox (5)` | full label on `dark_goldenrod` background |
| Sent: total=0 | `Sent` | plain |
| Sent: total>0 | `Sent (3)` | plain |
| Bulletins | unchanged | — |

Full `update_counts()` method:
```python
def update_counts(self, stats: dict[str, tuple[int, ...]]) -> None:
    from rich.text import Text
    from rich.style import Style

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

### `app.py`

**Imports** — add `MessageQueuedEvent` to the import from `open_packet.engine.events`.

**`_handle_event()`** — add a `MessageQueuedEvent` check before the `StatusBar` guard so it is never silently dropped if `StatusBar` is not yet mounted. All existing branches (`ConnectionStatusEvent`, `SyncCompleteEvent`, `ErrorEvent`) remain unchanged after the guard:
```python
def _handle_event(self, event) -> None:
    if isinstance(event, MessageQueuedEvent):
        self._refresh_message_list()
        return
    try:
        status_bar = self.query_one("StatusBar")
    except Exception:
        return
    if isinstance(event, ConnectionStatusEvent):
        # ... unchanged ...
    elif isinstance(event, SyncCompleteEvent):
        # ... unchanged (this also calls _refresh_message_list, updating counts) ...
    elif isinstance(event, ErrorEvent):
        # ... unchanged ...
```

**`_refresh_message_list()`:**

- **Inbox filter**: change `if not m.sent` to `if not m.sent and not m.queued`. **Prerequisite: Store Step 1 (`_row_to_message()`) must be done first** — without it `m.queued` is always `False` and the filter has no effect. The Sent filter (`if m.sent`) requires no change.
- **Add Outbox case** — insert as a new `elif` branch before the final `else: messages = []` fallthrough:
  ```python
  elif folder == "Outbox":
      messages = self._store.list_outbox(operator_id=operator_id)
  ```
- After `msg_list.load_messages(messages)`, update folder counts:
  ```python
  stats = self._store.count_folder_stats(operator_id)
  self.query_one("FolderTree").update_counts(stats)
  ```
  Both calls are inside the existing `try/except Exception` block. If `FolderTree` is not yet mounted, `query_one("FolderTree")` will raise and the count update will be silently skipped for that cycle — this is acceptable and consistent with the existing error-handling pattern throughout `_refresh_message_list()`. `update_counts()` itself does not need to be defensive; the caller's `try/except` is the intended guard.

---

## Out of Scope

- Per-category bulletin counts (deferred)
- Deleting queued messages from the Outbox via a dedicated UI action (existing delete flow handles this already)
- `MessageReceivedEvent` not triggering a UI refresh (pre-existing gap, unrelated to this spec)
