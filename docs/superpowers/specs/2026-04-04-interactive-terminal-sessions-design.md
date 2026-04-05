# Interactive Terminal Sessions — Design Spec

**Date:** 2026-04-04

## Overview

Add an interactive packet terminal feature to open-packet. Users can initiate a raw AX.25 connection (via KISS interfaces) or a direct telnet connection to any configured interface/node, then exchange free-form text in a live terminal view within the TUI. Sessions appear in the folder sidebar alongside mail folders. Additionally, SSID fields are made optional (defaulting to 0) throughout the setup screens.

---

## Architecture

The feature adds three new components and modifies several existing ones. Terminal sessions are owned entirely by `OpenPacketApp` — independent of the mail `Engine`.

### New components

| Component | Location |
|-----------|----------|
| `TerminalSession` | `open_packet/terminal/session.py` |
| `ConnectTerminalScreen` | `open_packet/ui/tui/screens/connect_terminal.py` |
| `TerminalView` | `open_packet/ui/tui/widgets/terminal_view.py` |

### Modified components

| Component | Change |
|-----------|--------|
| `OpenPacketApp` | Owns `_terminal_sessions`, polls sessions, routes input/output |
| `MainScreen` | Adds `TerminalView` to right pane; `show_terminal()` / `show_messages()` |
| `FolderTree` | New "Sessions" section with status indicators |
| `setup_operator.py` | SSID field made optional |
| `setup_node.py` | SSID field made optional |

---

## Section 1: `TerminalSession`

Lives in `open_packet/terminal/session.py`.

```python
class TerminalSession:
    label: str           # display name, e.g. "W0XYZ" or node label
    status: str          # "connecting" | "connected" | "disconnected" | "error"
    has_unread: bool     # True when poll() produced data but session isn't active; sidebar uses this for the ◉ indicator
    _connection: ConnectionBase
    _target_callsign: str   # ignored for telnet interfaces
    _target_ssid: int       # ignored for telnet interfaces
    _rx_queue: queue.Queue[str]
    _thread: Thread (daemon)
    _stop_event: threading.Event
```

**Construction:** `TerminalSession(label, connection, target_callsign, target_ssid)`. For telnet connections, `target_callsign` and `target_ssid` are ignored — the telnet link connects directly to its configured host.

**Thread behavior:** calls `connection.connect(target_callsign, target_ssid)`, sets `status = "connected"`, then loops calling `connection.receive_frame()` and putting decoded text into `_rx_queue`. On disconnect or error, sets `status` accordingly and exits.

**Public API:**
- `start()` — spawns daemon thread
- `send(text: str)` — calls `connection.send_frame((text + "\r").encode())`
- `disconnect()` — sets stop event, calls `connection.disconnect()`, joins thread
- `poll() -> list[str]` — drains `_rx_queue`, returns all pending lines

---

## Section 2: `ConnectTerminalScreen`

A modal screen (like `ComposeScreen`). Constructor receives `db: Database`.

**Fields:**

- **Node** (`Select`) — populated from `db.list_nodes()`, plus a "— custom —" blank option at the top. Selecting a node auto-fills the interface, callsign, and SSID fields. If the resolved interface is telnet, callsign and SSID are disabled.
- **Interface** (`Select`) — populated from `db.list_interfaces()` (all types). Changing the selection manually updates callsign/SSID enabled state: disabled for telnet, enabled for KISS.
- **Callsign** (`Input`) — uppercase, validated against `CALLSIGN_RE`. Disabled when a telnet interface is active.
- **SSID** (`Input`) — optional integer 0–15; defaults to 0 if blank. Disabled alongside callsign for telnet.

**On Connect:** constructs and returns a `TerminalSession` to the app (not yet started). The app starts it after dismiss.

**On Cancel:** returns `None`.

---

## Section 3: TUI Integration

### `TerminalView` widget (`widgets/terminal_view.py`)

A `Vertical` containing:
- A header bar (one line): session label + current status, e.g. `W0XYZ — connected`
- A `RichLog` (scrollable output, auto-scrolls on new lines)
- An `Input` at the bottom for typing

On Enter in the input, fires `TerminalView.LineSubmitted(text)`. Hidden by default; shown when a session is selected.

### `FolderTree` changes

A "Sessions" section is rendered below the existing mail folders. Each entry shows a status prefix and the session label:

| Status | Indicator |
|--------|-----------|
| connecting | `⟳ label` (yellow) |
| connected | `● label` (green) |
| connected + unread | `◉ label` (cyan/bold) |
| disconnected | `○ label` (dim) |
| error | `✕ label` (red) |

New method: `update_sessions(sessions: list[TerminalSession])` — refreshes this section. Selecting a session entry fires `SessionSelected(session_idx: int)`.

### `MainScreen` right pane

`TerminalView` is added to the right pane alongside `MessageList`/`MessageBody`, hidden by default. Two new methods:
- `show_terminal()` — hides message widgets, shows `TerminalView`
- `show_messages()` — hides `TerminalView`, shows message widgets

### `OpenPacketApp` changes

**State:**
- `_terminal_sessions: list[TerminalSession] = []`
- `_active_session_idx: Optional[int] = None`

**New binding:** `t` → `open_terminal_connect`

**New methods:**
- `open_terminal_connect()` — pushes `ConnectTerminalScreen(db=self._db)`; callback calls `_on_connect_terminal_result`
- `_on_connect_terminal_result(session)` — starts the session, appends to `_terminal_sessions`, calls `update_sessions()` on `FolderTree`

**Modified `_poll_events()`:** after polling the engine queue, iterates `_terminal_sessions`. For each session, calls `session.poll()`. If lines are returned and the session is not the active one, sets `session.has_unread = True` and calls `update_sessions()`. If it is the active session, appends lines to `TerminalView`'s `RichLog`.

**New event handlers:**
- `on_folder_tree_session_selected(event)` — sets `_active_session_idx`, clears `has_unread`, calls `show_terminal()` on `MainScreen`, updates `TerminalView` header
- `on_terminal_view_line_submitted(event)` — calls `_terminal_sessions[_active_session_idx].send(event.text)`

**Disconnect:** `^d` binding (active only in terminal mode) calls `session.disconnect()`, removes from `_terminal_sessions`, refreshes sidebar, calls `show_messages()` if no sessions remain.

---

## Section 4: SSID Optional

SSID fields in `setup_operator.py` and `setup_node.py` are made optional — blank input defaults to `0`.

**Label change:** `"SSID (0-15)"` → `"SSID (optional, 0–15)"`

**Validation change:** `int(ssid_str) if ssid_str else 0` replaces the bare `int(ssid_str)` call that currently errors on blank input.

No model, database, or `compose.py` changes needed. The `to_call` field in `ComposeScreen` is already a free-text string.

---

## Out of Scope

- Via/digipeater path for terminal sessions (deferred to a future digipeater pathing feature)
- Multiple simultaneous sessions on the same interface
- Session history persistence
