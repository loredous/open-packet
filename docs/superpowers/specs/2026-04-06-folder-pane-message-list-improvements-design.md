# Folder Pane & Message List Improvements

**Date:** 2026-04-06  
**Status:** Approved

## Overview

Three targeted improvements to the main screen's folder pane and message list:

1. Folder pane auto-sizes to fit contents (min 18, max 32 columns)
2. Unread indicator clears in-place when a message or bulletin is marked read
3. Message list shows two date columns: "Sent" (timestamp) and "Retrieved" (synced_at)

---

## 1. FolderTree Dynamic Width

### Behaviour
The folder pane expands and contracts as label text changes. Width is always between 18 and 32 columns.

### Implementation

Add a private `_recompute_width()` method to `FolderTree`. It:
- Collects the plain-text length of every currently-rendered label: inbox/outbox/sent (with count suffixes), each bulletin category label (with count suffixes), each session label (stripping Rich markup).
- Computes `max(18, min(32, longest_label + 2))` where `+2` accounts for tree indent/padding.
- Applies the result via `self.styles.width = computed`.

`_recompute_width()` is called at the end of both `update_counts()` and `update_sessions()`.

The CSS `width: 18` remains as the initial value; runtime styles override it once data arrives.

---

## 2. In-Place Read Indicator Update

### Behaviour
When the user selects a message or bulletin and it is marked read, the `●` in column 0 of that row clears immediately — without reloading the table or resetting the cursor.

### Implementation

Add `mark_row_read(row_index: int)` to `MessageList`:

```python
def mark_row_read(self, row_index: int) -> None:
    from textual.coordinate import Coordinate
    self.update_cell_at(Coordinate(row_index, 0), " ")
```

In `OpenPacketApp.on_message_list_message_selected`, after the existing `mark_message_read` / `mark_bulletin_read` calls, add:

```python
msg_list = self.query_one("MessageList")
msg_list.mark_row_read(msg_list.cursor_row)
```

No changes to the `SyncCompleteEvent` path — that already calls `_refresh_message_list()` which reloads everything.

---

## 3. Two Date Columns in MessageList

### Behaviour
The message list shows:
- **Sent** — `msg.timestamp`, formatted `%m/%d %H:%M`
- **Retrieved** — `msg.synced_at`, formatted `%m/%d %H:%M`, or `"—"` when None (e.g. outbox items)

### Column Order
`●` | `Subject` | `From` | `Sent` | `Retrieved`

### Implementation

In `MessageList.on_mount`, replace:
```python
self.add_columns("  ", "Subject", "From", "Date")
```
with:
```python
self.add_columns("  ", "Subject", "From", "Sent", "Retrieved")
```

In `load_messages`, replace the existing `date_str` / `add_row` call with:
```python
sent_str = msg.timestamp.strftime("%m/%d %H:%M") if msg.timestamp else "—"
retrieved_str = msg.synced_at.strftime("%m/%d %H:%M") if msg.synced_at else "—"
self.add_row(read_marker, msg.subject[:40], msg.from_call, sent_str, retrieved_str)
```

Both `Message` and `Bulletin` already have `synced_at: Optional[datetime]` on their dataclasses and are populated by `Store._row_to_message` / `Store._row_to_bulletin`. No store or schema changes needed.

---

## Files to Change

| File | Change |
|------|--------|
| `open_packet/ui/tui/widgets/folder_tree.py` | Add `_recompute_width()`, call from `update_counts()` and `update_sessions()` |
| `open_packet/ui/tui/widgets/message_list.py` | Add `Retrieved` column, update `load_messages`, add `mark_row_read()` |
| `open_packet/ui/tui/app.py` | Call `mark_row_read()` in `on_message_list_message_selected` |

No schema, store, or engine changes required.
