# Operator and Node Setup — Design Specification

**Date:** 2026-03-22
**Status:** Approved
**Project:** open-packet — Amateur Radio Packet Messaging Client

---

## Overview

The TUI currently has no way to configure operator identity or BBS node records from within the app. When the SQLite database contains no default operator or node, the engine silently fails to initialize and the user is stuck. This feature adds in-TUI setup screens to fix that gap.

---

## Architecture

Three new `ModalScreen` subclasses overlay the main UI. Two existing files are modified to wire them in.

### New files

- `open_packet/ui/tui/screens/settings.py` — `SettingsScreen`: a simple menu with two items ("Operator", "Node"). Dismisses with `"operator"`, `"node"`, or `None` (Escape/cancel).
- `open_packet/ui/tui/screens/setup_operator.py` — `OperatorSetupScreen`: a form for creating an operator record. Dismisses with a populated `Operator` dataclass or `None`.
- `open_packet/ui/tui/screens/setup_node.py` — `NodeSetupScreen`: a form for creating a node record. Dismisses with a populated `Node` dataclass or `None`.

### Modified files

- `open_packet/ui/tui/screens/main.py` — adds an `s` key binding that pushes `SettingsScreen`.
- `open_packet/ui/tui/app.py` — handles first-run detection and all dismiss results; adds `_restart_engine()`.

---

## Screen Designs

### SettingsScreen

A `ModalScreen` containing a vertical list of `Button` widgets:
- **Operator** → dismisses with `"operator"`
- **Node** → dismisses with `"node"`
- **Close** (or Escape) → dismisses with `None`

Designed to be extensible: future settings options are additional buttons.

### OperatorSetupScreen

A `ModalScreen` form with:

| Field | Widget | Validation |
|-------|--------|------------|
| Callsign | `Input` | Required; 1–6 chars; alphanumeric; stored uppercased |
| SSID | `Input` | Required; integer 0–15 |
| Label | `Input` | Required; non-empty |
| Set as default | `Switch` | Defaults to `True` |

An inline `Label` (hidden by default) displays validation errors below the relevant field. The "Save" button runs validation; if any field fails, errors are shown and the screen does not dismiss. On success, dismisses with an `Operator` dataclass (not yet written to DB).

### NodeSetupScreen

A `ModalScreen` form with:

| Field | Widget | Validation |
|-------|--------|------------|
| Label | `Input` | Required; non-empty |
| Callsign | `Input` | Required; 1–6 chars; alphanumeric; stored uppercased |
| SSID | `Input` | Required; integer 0–15 |
| Node Type | `Label` (read-only) | Fixed to `"bpq"` at PoC |
| Set as default | `Switch` | Defaults to `True` |

Same inline error pattern as `OperatorSetupScreen`. Dismisses with a `Node` dataclass on success.

---

## Data Flow

### First-run

1. `OpenPacketApp._init_engine()` detects no default operator or no default node in the DB.
2. App pushes `OperatorSetupScreen` directly (skips `SettingsScreen`).
3. `OperatorSetupScreen` dismisses with `Operator` → app writes to DB via `Database.insert_operator()`, then pushes `NodeSetupScreen`.
4. `NodeSetupScreen` dismisses with `Node` → app writes to DB via `Database.insert_node()`, then calls `_restart_engine()`.
5. If the user cancels at any point, the app stays in the uninitialized state. The user can re-open setup via `s`.

### Settings flow (any time)

1. User presses `s` on `MainScreen` → app pushes `SettingsScreen`.
2. User selects "Operator" or "Node" → `SettingsScreen` dismisses with the appropriate string.
3. App pushes the corresponding setup screen.
4. Setup screen dismisses with result → app writes to DB, calls `_restart_engine()`.
5. Cancel at any point → no DB write, no engine restart.

### Engine reinitialization

`OpenPacketApp._restart_engine()`:
1. If `self._engine` is running, call `self._engine.stop()`.
2. Reset `self._engine = None`, `self._store = None`, `self._active_operator = None`.
3. Call `self._init_engine()`.

This is safe to call any time the default operator or node may have changed.

---

## Validation Rules

- **Callsign**: 1–6 uppercase alphanumeric characters. Stored uppercased regardless of input case.
- **SSID**: Integer in range 0–15 inclusive.
- **Label**: Non-empty string.
- Validation runs on "Save" button press. Errors shown inline; screen does not dismiss until all fields are valid.
- Cancel always dismisses with `None` without validation.

---

## Cancel Behavior

Cancelling any setup screen dismisses with `None`. The app does nothing — no DB write, no engine restart. On first-run, the engine remains uninitialized and the existing error notification stays visible. The user can return to setup at any time via `s`.

---

## Testing Strategy

- **`SettingsScreen`** — selecting "Operator" dismisses with `"operator"`; "Node" with `"node"`; Escape with `None`.
- **`OperatorSetupScreen`** — valid input dismisses with correct `Operator`; blank callsign shows inline error and does not dismiss; SSID out of range shows inline error.
- **`NodeSetupScreen`** — same pattern: valid input → `Node`; invalid callsign/SSID → inline errors.
- **First-run flow** — `OpenPacketApp` with empty DB: verify `OperatorSetupScreen` is pushed on mount.
- **Engine reinit** — after simulating successful operator+node setup, verify `self._engine` is not `None`.

No new DB or store tests needed — `insert_operator` / `insert_node` are already covered by existing tests.

---

## File Map

```
open_packet/ui/tui/screens/
├── settings.py          # NEW: SettingsScreen modal
├── setup_operator.py    # NEW: OperatorSetupScreen modal
├── setup_node.py        # NEW: NodeSetupScreen modal
├── main.py              # MODIFY: add 's' binding
└── compose.py           # unchanged

open_packet/ui/tui/app.py  # MODIFY: first-run detection, dismiss handlers, _restart_engine()

tests/test_ui/
└── test_setup_screens.py  # NEW: tests for all three screens + first-run + reinit
```
