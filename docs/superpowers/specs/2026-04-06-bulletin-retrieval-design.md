# Bulletin Retrieval: Header-First with Selective Download

**Date:** 2026-04-06
**Status:** Approved

## Overview

Currently, every sync session downloads the full body of every new bulletin from the BBS — expensive on slow RF links. This spec changes bulletin retrieval to a two-phase model: headers are always listed during sync, but bodies are only fetched for bulletins the user has explicitly marked for retrieval.

## Data Model

### `Bulletin` model (`store/models.py`)

Two field changes:

- `body: str` → `body: Optional[str] = None` — `None` means header-only (body not yet fetched)
- Add `wants_retrieval: bool = False` — `True` means the user has queued this bulletin for body retrieval on the next sync

All other fields (`node_id`, `category`, `from_call`, `subject`, `bbs_id`, etc.) are populated when the header is first saved.

The `node_id` field (already present) records which BBS node the header came from; this is used to display the source node to the user and to restrict body retrieval to the correct node during sync.

### DB migration (`store/database.py`)

One new migration using the existing `ALTER TABLE ... ADD COLUMN` pattern:

```sql
ALTER TABLE bulletins ADD COLUMN wants_retrieval INTEGER NOT NULL DEFAULT 0
```

The `body` column already allows NULL in SQLite even though Python previously always wrote a string; no DDL change is needed there.

### New `Store` methods (`store/store.py`)

- `mark_bulletin_wants_retrieval(id: int)` — sets `wants_retrieval=1` for the given bulletin
- `list_bulletins_pending_retrieval(node_id: int) → list[Bulletin]` — returns bulletins where `wants_retrieval=1 AND body IS NULL` for a specific node; used by the engine during sync
- `update_bulletin_body(id: int, body: str)` — writes the retrieved body and sets `synced_at`

The existing `save_bulletin()` deduplication (by `bbs_id + node_id`) means re-listing the same header on subsequent syncs won't create duplicates — the header row persists until the body is retrieved.

## Engine

### Revised Phase 4 in `_run_sync_phases` (`engine/engine.py`)

**Step 1 — List headers:** Call `node.list_bulletins()` to get all available headers.

**Step 2 — Save new headers:** For each header not already in DB (checked via `bulletin_exists`), call `store.save_bulletin()` with `body=None` and `wants_retrieval=False`.

**Step 3 — Retrieve queued bodies:** Call `store.list_bulletins_pending_retrieval(node_id)` to get all bulletins where `wants_retrieval=True AND body IS NULL` for this node. For each: call `node.read_bulletin(bbs_id)`, then `store.update_bulletin_body(id, body)`. Emit a `ConsoleEvent` per successful retrieval.

`SyncCompleteEvent.bulletins_retrieved` reflects bodies fetched (Step 3), not headers listed. A `bulletin_headers_listed` count may be added to `SyncCompleteEvent` in the future but is out of scope here.

No new `Command` type is needed — marking a bulletin for retrieval is a direct store call from the TUI, consistent with how `mark_bulletin_read` works.

## TUI

### Key binding

Add `r` to `MainScreen.BINDINGS` — label "Queue Retrieval". The action handler in `app.py` guards against non-bulletin or already-retrieved selections (silently no-ops if body is already present).

### `app.py`

New `queue_bulletin_retrieval()` method:
1. Confirm `_selected_message` is a `Bulletin` with `body is None`
2. Call `store.mark_bulletin_wants_retrieval(id)`
3. Refresh the message list and folder stats

### `MessageBody` widget

When a `Bulletin` with `body is None` is selected, render a styled placeholder instead of body text. The placeholder includes the source node name, looked up via `store.list_nodes()` (already available in the app). Example:

> Not retrieved — source: W0IA-1 (Local BBS). Press `r` to queue for next sync.

### `MessageList` widget

When rendering a bulletin row where `body is None`, apply a dim style to the row. This follows the same per-row styling pattern as `mark_row_read()`.

### Folder tree

No changes required. Header-only bulletins are saved with a real `category`, so they appear under the correct category node in the tree and are counted in folder stats automatically.

## Out of Scope

- Per-category filtering before listing (future work)
- Bulk "select all" / "select by category" for retrieval queuing
- `bulletin_headers_listed` count in `SyncCompleteEvent`
- Expiry or auto-cleanup of old unselected headers
