# Console Log Level Design

**Date:** 2026-04-09  
**Status:** Approved

## Overview

Add a "Console Log Level" option to General Settings with two values:

- **Basic** (default) — everything currently shown, plus status-bar-equivalent progress messages and sync-complete summary
- **Debug** — all of basic, plus decoded AX.25 frame summaries or telnet command I/O

## Data Model

### `ConsoleEvent` (events.py)

Add a `level: str = "basic"` field. Valid values: `"basic"`, `"debug"`.

```python
@dataclass
class ConsoleEvent:
    direction: str   # ">" sent, "<" received, "!" info/error
    text: str
    level: str = "basic"
```

Existing call sites that don't pass `level` default to `"basic"` with no changes needed.

### `Settings` (store/settings.py)

Add `console_log_level` property backed by `get_setting`/`set_setting`. Default: `"basic"`.

```python
@property
def console_log_level(self) -> str:
    return self._db.get_setting("console_log_level")

@console_log_level.setter
def console_log_level(self, value: str) -> None:
    self._db.set_setting("console_log_level", value)
```

### `Database` (store/database.py)

`get_setting` raises `KeyError` for unknown keys; defaults are seeded in `initialize()`. Add `"console_log_level"` to both `_KNOWN_SETTING_KEYS` and the seed list in `initialize()`:

```python
_KNOWN_SETTING_KEYS = frozenset({
    ...,
    "console_log_level",
})

# in initialize():
("console_log_level", "basic"),
```

## Engine Changes (engine/engine.py)

### New "basic" ConsoleEvents

Wherever the engine calls `_set_status(SYNCING, detail)`, also emit:

```python
self._emit(ConsoleEvent("!", detail, level="basic"))
```

After constructing the sync-complete summary (currently built only in `app.py`), emit it from the engine before emitting `SyncCompleteEvent`:

```python
parts = [f"{retrieved} new", f"{bulletins_retrieved} bulletins", f"{sent} sent"]
if files_retrieved:
    parts.append(f"{files_retrieved} files")
self._emit(ConsoleEvent("<", f"Sync complete: {', '.join(parts)}", level="basic"))
self._emit(SyncCompleteEvent(...))
```

Error paths in `_run()` (the `except` block) also emit:

```python
self._emit(ConsoleEvent("!", str(e), level="basic"))
```

### Frame Logger Callback

The engine constructs a closure capturing `self._evt_queue`:

```python
def _make_frame_logger(self) -> Callable[[str, str], None]:
    def log(direction: str, summary: str) -> None:
        self._evt_queue.put(ConsoleEvent(direction, summary, level="debug"))
    return log
```

This closure is passed as `on_frame=self._make_frame_logger()` when building `AX25Connection` or `TelnetLink` in `_build_connection()`. It is always wired up — filtering happens at display time in the app, not here.

## Connection Layer Changes

### `AX25Connection` (ax25/connection.py)

Add `on_frame: Callable[[str, str], None] | None = None` to `__init__`. Store as `self._on_frame`.

Call `self._on_frame` (when not None) in:

- `_send_sabm` → `self._on_frame(">", f"SABM {self._my_call}→{self._dest_call} (poll)")`
- `_send_disc` → `self._on_frame(">", f"DISC {self._my_call}→{self._dest_call}")`
- `_send_i_frame` → `self._on_frame(">", f"I({self.V_S},{self.V_A}) {payload_repr}")`
- `_send_rr` / `_send_rnr` / `_send_rej` → `self._on_frame(">", f"RR/RNR/REJ NR={nr}")`
- `_process_frame` (after decode) → `self._on_frame("<", f"{f.frame_type.value}({f.ns},{f.nr}) {payload_repr}")` for I-frames, or `self._on_frame("<", f"{f.frame_type.value} {f.source}→{f.destination}")` for supervisory/unnumbered

Where `payload_repr` is the info field decoded as ASCII (replacing non-printable bytes with `.`), truncated to 40 characters.

Parameter is nullable so all existing construction sites (tests, etc.) keep working unchanged.

### `TelnetLink` (link/telnet.py)

Add `on_frame: Callable[[str, str], None] | None = None` to `__init__`. Store as `self._on_frame`.

Call it in:
- `send_frame(data)` → `self._on_frame(">", data.decode("ascii", errors="replace").rstrip())`
- `receive_frame(...)` return path (when data is not None) → `self._on_frame("<", data.decode("ascii", errors="replace").rstrip())`

## App Changes (ui/tui/app.py)

### Filtering in `_handle_event`

```python
if isinstance(event, ConsoleEvent):
    if getattr(event, "level", "basic") == "debug":
        if not self._settings or self._settings.console_log_level != "debug":
            return
    try:
        self.query_one("ConsolePanel").log_frame(event.direction, event.text)
    except Exception:
        pass
    return
```

The setting is read live on each event — no restart needed when the user changes the level.

## UI Changes (ui/tui/screens/general_settings.py)

Add a `Select` widget between "Console Buffer" and "Auto-Discover":

```python
from textual.widgets import Select

# In compose():
with Horizontal(classes="field-row"):
    yield Label("Log Level", classes="field-label")
    yield Select(
        options=[("Basic", "basic"), ("Debug", "debug")],
        value=self._settings.console_log_level,
        id="console_log_level_field",
        classes="field-input",
    )

# In _save():
console_log_level = self.query_one("#console_log_level_field", Select).value
self._settings.console_log_level = console_log_level
```

No restart required; the filter in `_handle_event` reads the setting live.

## What Each Level Shows

### Basic
- Everything currently shown (connecting, messages in/out, bulletins, files, errors)
- Sync phase progress: "Reading message 2 of 10", "Sending message 1 of 1", "Retrieving bulletin 1 of 3", etc.
- Sync complete summary: "Sync complete: 2 new, 3 bulletins, 0 sent"
- Engine-level errors

### Debug (all of basic, plus)
- For KISS/AX.25: decoded frame summaries — `SABM W0IA→W0BBS (poll)`, `I(0,3) "L\r"`, `UA W0BBS→W0IA`, `RR NR=1`, etc.
- For Telnet: raw text lines sent/received — `L\r`, `R 1 W0IA\r`, BPQ responses

## Out of Scope
- Log-to-file filtering (file logger in `ConsolePanel.set_log_file` logs everything regardless of level)
- Per-channel filtering (AX.25 vs Telnet separately)
- A third "verbose" level
