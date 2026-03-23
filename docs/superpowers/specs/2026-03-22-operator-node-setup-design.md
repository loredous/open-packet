# Operator and Node Setup — Design Specification

**Date:** 2026-03-22
**Status:** Approved
**Project:** open-packet — Amateur Radio Packet Messaging Client

---

## Overview

The TUI currently has no way to configure operator identity or BBS node records from within the app. When the SQLite database contains no default operator or node, the engine silently fails to initialize and the user is stuck. This feature adds in-TUI setup screens to fix that gap.

---

## Architecture

Three new `ModalScreen` subclasses overlay the main UI. Three existing files are modified to wire them in.

### New files

- `open_packet/ui/tui/screens/settings.py` — `SettingsScreen`: a simple menu with two items ("Operator", "Node"). Dismisses with `"operator"`, `"node"`, or `None` (Escape/cancel).
- `open_packet/ui/tui/screens/setup_operator.py` — `OperatorSetupScreen`: a form for creating an operator record. Dismisses with a populated `Operator` dataclass or `None`.
- `open_packet/ui/tui/screens/setup_node.py` — `NodeSetupScreen`: a form for creating a node record. Dismisses with a populated `Node` dataclass or `None`.
- `tests/test_ui/test_setup_screens.py` — tests for all new screens and flows.

### Modified files

- `open_packet/ui/tui/screens/main.py` — adds `("s", "settings", "Settings")` to BINDINGS and an `action_settings(self)` method that calls `self.app.push_screen(SettingsScreen())`. The push is on `self.app` (not `self`) so that `on_settings_screen_dismiss` fires on `OpenPacketApp`, consistent with how other actions delegate to the app (e.g. `self.app.check_mail()`).
- `open_packet/ui/tui/app.py` — handles first-run detection and all dismiss results; adds `_restart_engine()`, `_save_operator()`, `_save_node()`; stores `self._db`; adds `self._db: Optional[Database] = None` to `__init__`.
- `open_packet/store/database.py` — adds `clear_default_operator()` and `clear_default_node()` methods.

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
| Callsign | `Input` | Required; 1–6 chars; alphanumeric (`[A-Za-z0-9]`); stored uppercased |
| SSID | `Input` | Required; integer 0–15 |
| Label | `Input` | Required; non-empty |
| Set as default | `Switch` | Defaults to `True` |

An inline `Label` (hidden by default) displays validation errors below the relevant field. The "Save" button runs validation; if any field fails, errors are shown and the screen does not dismiss. On success, dismisses with an `Operator` dataclass (not yet written to DB — the app handles the write). Cancel button and Escape both dismiss with `None` without running validation.

Digits-only callsigns (e.g. `"9999"`) are accepted at PoC.

### NodeSetupScreen

A `ModalScreen` form with:

| Field | Widget | Validation |
|-------|--------|------------|
| Label | `Input` | Required; non-empty |
| Callsign | `Input` | Required; 1–6 chars; alphanumeric; stored uppercased |
| SSID | `Input` | Required; integer 0–15 |
| Node Type | `Label` (read-only) | Displays `"bpq"` — not user-editable |
| Set as default | `Switch` | Defaults to `True` |

Same inline error pattern as `OperatorSetupScreen`. On success, the dismissed `Node` dataclass has `node_type="bpq"` hardcoded in the screen's save logic (not read from the label widget). Cancel and Escape dismiss with `None`.

---

## Data Flow

### First-run detection

`_init_engine()` assigns `self._db` immediately after calling `db.initialize()` — on every code path, including early returns. This ensures `_restart_engine()` can always close the connection even if operator/node detection leads to an early return without engine startup.

`_init_engine()` assigns `self._db = db` as the very next line after `db.initialize()` — before the `if not operator or not node_record` early-return check, and before any other statement. This guarantees `self._db` is non-None on all code paths, including early returns, enabling `_restart_engine()` and `_save_operator`/`_save_node` to function correctly regardless of whether the engine fully initialised.

`_init_engine()` then checks independently for a default operator and default node. The branching logic is:

| Operator exists? | Node exists? | Action |
|-----------------|-------------|--------|
| No | No | defer → push `OperatorSetupScreen`; on success push `NodeSetupScreen` |
| No | Yes | defer → push `OperatorSetupScreen` only |
| Yes | No | defer → push `NodeSetupScreen` only |
| Yes | Yes | Normal engine initialization — no setup screens |

All screen pushes from `_init_engine()` are deferred via `self.call_after_refresh(...)`, never called synchronously, so the Textual screen stack is settled before the modal is pushed.

### First-run sequence (both missing)

1. `_init_engine()` detects no default operator and no default node → defers push of `OperatorSetupScreen`.
2. `on_operator_setup_screen_dismiss` receives `Operator` → calls `_save_operator(op)`, then `push_screen(NodeSetupScreen())`.
3. `on_node_setup_screen_dismiss` receives `Node` → calls `_save_node(node)`, then `_restart_engine()`.
4. If the user cancels `OperatorSetupScreen` (dismiss `None`): nothing written, engine stays uninitialized.
5. If the user completes `OperatorSetupScreen` but cancels `NodeSetupScreen` (dismiss `None`): operator is written to DB, node is not. On next mount `_init_engine()` detects operator exists/node missing → defers push of `NodeSetupScreen` only. No duplicate operator form shown.

### Settings flow (any time)

1. User presses `s` on `MainScreen` → `action_settings` calls `self.app.push_screen(SettingsScreen())`.
2. `on_settings_screen_dismiss` receives the result and routes it:
   - `"operator"` → push `OperatorSetupScreen()`
   - `"node"` → push `NodeSetupScreen()`
   - `None` (cancel/Escape) → do nothing
3. `on_operator_setup_screen_dismiss` or `on_node_setup_screen_dismiss` receives result → calls `_save_operator`/`_save_node`, then applies the context-disambiguation rule below (which applies unconditionally regardless of how the setup screen was reached).
4. Cancel at any point → dismiss `None` → no DB write, no engine restart.

**Dismiss callback mechanism:** All screen results are handled via Textual's `on_<ScreenClassName>_dismiss` message handler pattern on `OpenPacketApp`, where the class name is converted to snake_case (e.g. `OperatorSetupScreen` → `on_operator_setup_screen_dismiss`). This is consistent with the existing `on_compose_screen_dismiss` pattern. Typos in handler names will silently swallow results with no error — names must be exact.

### Context disambiguation in `on_operator_setup_screen_dismiss`

`on_operator_setup_screen_dismiss` is invoked in two contexts: first-run (where node setup must follow) and settings flow (where only engine restart is needed). Rather than a flag, the handler determines what to do next by checking the database state at dismiss time. This rule applies unconditionally regardless of how the setup screen was reached:

- If `self._db.get_default_node()` returns `None` → push `NodeSetupScreen()` (node still needed; this covers both first-run and the case where settings is used to update an operator when no node has ever been configured)
- If `self._db.get_default_node()` returns a node → call `_restart_engine()` (both records now exist)

`_save_operator` and `_save_node` can assume `self._db` is non-None at the point they are called: `_init_engine()` guarantees `self._db` is assigned before any setup screen is pushed. No defensive guard is required inside these helpers.

### Engine reinitialization

`OpenPacketApp._restart_engine()`:
1. If `self._engine` is not `None`, call `self._engine.stop()`.
2. If `self._db` is not `None`, call `self._db.close()`.
3. Reset `self._engine = None`, `self._store = None`, `self._active_operator = None`, `self._db = None`.
4. Call `self._init_engine()`. Per the assignment guarantee above, `_init_engine()` assigns `self._db = db` as its first action after `db.initialize()`, so `self._db` will be non-None again after this call on all paths.

### Default record handling

`_save_operator(op: Operator)` and `_save_node(node: Node)` are helper methods on `OpenPacketApp`. When the record has `is_default=True`, they call the new `Database` helper methods before inserting:

- `Database.clear_default_operator()` — executes `UPDATE operators SET is_default=0 WHERE is_default=1` and commits.
- `Database.clear_default_node()` — executes `UPDATE nodes SET is_default=0 WHERE is_default=1` and commits.

These new methods are the only DB changes required. After clearing, `insert_operator` / `insert_node` is called as before. This ensures `get_default_operator()` / `get_default_node()` always return at most one row.

---

## Validation Rules

- **Callsign**: 1–6 characters, matching `[A-Za-z0-9]+`. Digits-only accepted at PoC. Stored uppercased.
- **SSID**: Integer in range 0–15 inclusive. Non-numeric input or out-of-range value shows an error.
- **Label**: Non-empty string after stripping whitespace.
- Validation runs on "Save" button press only. Errors shown inline below each invalid field; screen does not dismiss until all fields are valid.
- Cancel / Escape always dismisses with `None` without validation.

---

## Cancel Behavior

Cancelling any setup screen dismisses with `None`. The app does nothing — no DB write, no engine restart. On first-run, the engine remains uninitialized and the existing error notification stays visible. The user can return to setup at any time via `s`. If operator was already saved before cancelling node setup, the next mount pushes `NodeSetupScreen` only.

---

## Testing Strategy

- **`SettingsScreen`** — "Operator" button dismisses with `"operator"`; "Node" with `"node"`; Escape with `None`.
- **`OperatorSetupScreen`**:
  - Valid input dismisses with correct `Operator` (callsign uppercased).
  - Blank callsign shows inline error, does not dismiss.
  - SSID out of range shows inline error, does not dismiss.
  - Cancel/Escape dismisses with `None`.
- **`NodeSetupScreen`**:
  - Valid input dismisses with `Node` where `node_type == "bpq"`.
  - Invalid callsign/SSID shows inline errors, does not dismiss.
  - Cancel/Escape dismisses with `None`.
- **First-run (both missing)** — `OpenPacketApp` with empty DB: verify a setup screen is pushed after mount.
- **First-run (operator exists, node missing)** — verify `NodeSetupScreen` is pushed, not `OperatorSetupScreen`.
- **Partial first-run cancel** — operator saved, `NodeSetupScreen` cancelled: verify operator is in DB, engine is still uninitialized (`self._engine is None`), and next mount pushes a setup screen (not `OperatorSetupScreen`).
- **Engine reinit** — after simulating successful operator+node setup via dismiss handlers, verify `self._engine is not None`.

No new DB or store tests needed — `insert_operator` / `insert_node` are already covered. The new `clear_default_operator` / `clear_default_node` methods are simple enough to be covered implicitly by the integration tests above.

---

## File Map

```
open_packet/ui/tui/screens/
├── settings.py          # NEW: SettingsScreen modal
├── setup_operator.py    # NEW: OperatorSetupScreen modal
├── setup_node.py        # NEW: NodeSetupScreen modal
├── main.py              # MODIFY: add 's' binding
└── compose.py           # unchanged

open_packet/ui/tui/app.py      # MODIFY: first-run detection, dismiss handlers,
                               #         _restart_engine(), _save_operator(), _save_node(), self._db

open_packet/store/database.py  # MODIFY: add clear_default_operator(), clear_default_node()

tests/test_ui/
└── test_setup_screens.py      # NEW: all screen unit tests + first-run + reinit flows
```
