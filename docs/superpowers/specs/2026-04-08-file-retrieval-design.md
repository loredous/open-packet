# BBS File Retrieval — Design Spec

**Date:** 2026-04-08  
**Status:** Approved

## Overview

Add BBS file listing and retrieval to open-packet on the same two-phase model as bulletins: file headers are synced automatically each cycle, users mark individual files for retrieval, and content is downloaded and saved to disk on the next sync.

---

## 1. Data Model & Storage

### `BBSFile` dataclass (`store/models.py`)

```python
@dataclass
class BBSFile:
    id: Optional[int]
    node_id: int
    directory: str          # BBS directory name (e.g. "ARES", "WEATHER")
    filename: str           # unique identifier within the BBS
    size: Optional[int]     # bytes, from DIR listing
    date_str: str           # raw date string from BBS
    description: str        # one-line description from DIR listing
    content: Optional[str]  # None = not yet retrieved
    wants_retrieval: bool = False
    synced_at: Optional[datetime] = None
```

### `bbs_files` table (`store/database.py`)

```sql
CREATE TABLE IF NOT EXISTS bbs_files (
    id INTEGER PRIMARY KEY,
    node_id INTEGER NOT NULL,
    directory TEXT NOT NULL,
    filename TEXT NOT NULL,
    size INTEGER,
    date_str TEXT,
    description TEXT,
    content TEXT,
    wants_retrieval INTEGER NOT NULL DEFAULT 0,
    synced_at TEXT,
    deleted INTEGER NOT NULL DEFAULT 0,
    UNIQUE(node_id, filename)
)
```

`content` uses the same NUL sentinel (`"\x00"`) as bulletins to mean "header-only, not yet retrieved". A separate sentinel `"\x01"` marks "retrieved and saved to disk" — the actual content lives on disk, not in the DB.

Added via `ALTER TABLE ... ADD COLUMN` migration pattern with `except sqlite3.OperationalError: pass`.

### Store methods (`store/store.py`)

- `save_file_header(file: BBSFile)` — `INSERT OR IGNORE` on `(node_id, filename)`; never overwrites existing rows, preserving `wants_retrieval` and retrieval state
- `mark_file_wants_retrieval(file_id: int)` — sets `wants_retrieval=1`
- `list_files_pending_retrieval(node_id: int) -> list[BBSFile]` — `wants_retrieval=1 AND content="\x00"`
- `update_file_content(file_id: int)` — sets `content="\x01"`, clears `wants_retrieval`, sets `synced_at`
- `list_files(node_id: int, directory: str = "") -> list[BBSFile]` — optional directory filter
- `count_file_stats(node_id: int) -> dict[str, int]` — count per directory, for folder tree badges

---

## 2. Node Protocol Layer

### `FileHeader` dataclass (`node/base.py`)

```python
@dataclass
class FileHeader:
    filename: str
    directory: str
    size: Optional[int]
    date_str: str
    description: str
```

### `NodeBase` abstract methods (`node/base.py`)

```python
@abstractmethod
def list_files(self, directory: str = "") -> list[FileHeader]: ...

@abstractmethod
def read_file(self, filename: str) -> str: ...
```

### `BPQNode` implementation (`node/bpq.py`)

- `list_files(directory="")` — sends `DIR <directory>` (or bare `DIR` for all directories), parses with `parse_file_list()`
- `read_file(filename)` — sends `D <filename>`, reads until prompt, strips header/prompt lines, returns body as string

### `parse_file_list(text: str) -> list[FileHeader]` (`node/bpq.py`)

New top-level function. Parses BPQ32 DIR output format:
```
Filename        Size  Date    Description
ARES-NET.TXT   1234  230615  Weekly ARES net preamble
```

Uses best-effort regex, skipping lines that don't match (DIR format varies by node). Extracts directory from a preceding directory header line (e.g. `Dir: ARES`) when present; falls back to empty string.

---

## 3. Engine Sync Phases

Two new phases appended to `_run_sync_phases()` in `engine/engine.py`, after the existing bulletin phases.

**Phase 6 — List file headers:**

```python
self._set_status(ConnectionStatus.SYNCING, "Listing files…")
file_headers = node.list_files()
self._emit(ConsoleEvent(">", f"Listing files ({len(file_headers)} available)"))
for header in file_headers:
    self._store.save_file_header(BBSFile(
        id=None, node_id=self._node_record.id,
        directory=header.directory, filename=header.filename,
        size=header.size, date_str=header.date_str,
        description=header.description, content=None,
    ))
```

**Phase 7 — Retrieve wanted files:**

```python
pending = self._store.list_files_pending_retrieval(self._node_record.id)
files_retrieved = 0
for i, f in enumerate(pending, 1):
    self._set_status(ConnectionStatus.SYNCING, f"Retrieving file {i} of {len(pending)}")
    try:
        raw = node.read_file(f.filename)
    except Exception:
        logger.exception("Failed to retrieve file %s", f.filename)
        self._emit(ConsoleEvent("!", f"Failed to retrieve file {f.filename}"))
        continue
    export_dir = Path(self._export_path or ".")
    path = export_dir / "files" / f.directory / f.filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw)
    self._store.update_file_content(f.id)
    files_retrieved += 1
```

Files are saved to `<export_path>/files/<directory>/<filename>`.

**`SyncCompleteEvent`** gains a `files_retrieved: int` field (default 0) alongside existing fields.

---

## 4. TUI Integration

### Folder tree (`widgets/folder_tree.py`)

A "Files" top-level node added alongside "Messages" and "Bulletins". Children are directory names (e.g. "ARES", "WEATHER"), each with a count badge showing available file count. Selecting a directory node loads the file list panel.

### File list widget (`widgets/file_list.py`) — new widget

- Columns: filename, size, date, description, status
- Status column: blank (header only), `[Q]` (queued for retrieval), `[✓]` (retrieved and saved)
- Keybinding `r` on selected row toggles `wants_retrieval`, calling `store.mark_file_wants_retrieval()` directly (no engine command needed — same pattern as bulletins)
- No read pane; file content lives on disk

### Sync notification (`app.py`)

After sync, if `files_retrieved > 0`, the existing `SyncCompleteEvent` handler appends "N file(s) saved to `<export_path>/files/`" to the notification message.

---

## 5. Error Handling

- `parse_file_list` skips unrecognized lines silently — DIR format varies by BBS
- Per-file retrieval errors are logged and emitted as console events; other files continue
- `path.write_text` failures (e.g. permission error) are caught per-file with the same error pattern

---

## 6. Out of Scope

- Uploading files to the BBS
- In-app file content viewer
- Filtering/searching the file list
- Per-directory selective sync (all directories always listed)
