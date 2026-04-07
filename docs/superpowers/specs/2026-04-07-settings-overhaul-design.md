# Settings Overhaul Design

**Date:** 2026-04-07  
**Status:** Approved

## Overview

Three related changes to settings management:

1. **YAML elimination** — remove the YAML config file; bootstrap inputs come from CLI/env; all other settings live in SQLite
2. **Soft-delete across all tables** — all database objects support `deleted=1`; deleted records act as "already seen" sentinels for sync and as soft-deleted UI entities
3. **Clickable status bar identity pickers** — each segment of the status bar (operator / node / interface) is independently clickable and opens a mini-picker modal

---

## Section 1: Config & Settings Storage

### Bootstrap

`db_path` and `log_path` are the only inputs that must be known before the database opens. Both are resolved at process startup from (in priority order):

1. CLI flag: `--db-path`, `--log-path`, `--console-log`
2. Environment variable: `OPEN_PACKET_DB_PATH`, `OPEN_PACKET_LOG_PATH`, `OPEN_PACKET_CONSOLE_LOG`
3. Fixed defaults: `~/.local/share/open-packet/messages.db`, `~/.local/share/open-packet/open-packet.log`, no console log file

`console_log` (the path for writing raw console frames to a file) is also a bootstrap input — logging infrastructure must be configured before the DB opens — so it stays as a CLI/env var and does not appear in the `settings` table.

The YAML config file is eliminated entirely. `AppConfig`, `load_config`, and the `config/config.py` module are deleted. `main()` resolves `db_path` and `log_path` and passes them directly to `OpenPacketApp`.

### Settings Table

`Database.initialize()` creates a new `settings` table:

```sql
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

On first run, defaults are inserted with `INSERT OR IGNORE`:

| key | default |
|-----|---------|
| `export_path` | `~/.local/share/open-packet/export` |
| `console_visible` | `false` |
| `console_buffer` | `500` |
| `auto_discover` | `true` |

### Settings Wrapper

A `Settings` class in `store/settings.py` wraps typed getters/setters over the key-value table. `OpenPacketApp` instantiates it after `Database.initialize()` and uses it wherever `AppConfig` was previously accessed.

### General Settings Screen

A new "General" button is added to `SettingsScreen`, opening `GeneralSettingsScreen` — a modal form with fields for `export_path`, `console_visible`, `console_buffer`, and `auto_discover`. Changes write through to the `settings` table immediately. If any engine-affecting setting changes, the screen returns a `needs_restart=True` signal (same pattern as the existing manage screens).

---

## Section 2: Soft-Delete Across All Tables

### Schema Migrations

`deleted INTEGER NOT NULL DEFAULT 0` is added to all five tables via `ALTER TABLE ... ADD COLUMN` migrations in `Database.initialize()`:

- `operators` — new column
- `nodes` — new column
- `interfaces` — new column (replaces current hard-delete)
- `messages` — already exists; no change
- `bulletins` — new column

All `list_*` query methods gain `WHERE deleted=0` filters so deleted records are invisible to the UI.

### Sync Sentinel Behavior

The sync logic in `BPQNode`/`Engine` avoids re-inserting records it has already seen by checking `bbs_id` existence before inserting. Soft-deleted records remain in the DB with their `bbs_id` intact and continue to act as "already seen" sentinels — the sync skips them silently. No change to the sync logic is required.

### New Database Methods

```python
# Dependent counts (includes deleted records for accurate warning)
db.count_operator_dependents(op_id: int) -> tuple[int, int]  # (messages, bulletins)
db.count_node_dependents(node_id: int) -> tuple[int, int]

# Soft deletes (set deleted=1, clear is_default)
db.soft_delete_operator(op_id: int) -> None
db.soft_delete_node(node_id: int) -> None
db.soft_delete_interface(iface_id: int) -> None  # blocks if non-deleted nodes reference it
```

`delete_interface` (hard delete) is replaced by `soft_delete_interface`. The FK violation guard is replaced with an explicit check: if any non-deleted node references the interface, the soft-delete raises `ValueError`.

### Confirmation Modal

A new `DeleteConfirmScreen(title: str, body: str)` modal displays a warning message and two buttons: "Delete" (error variant) and "Cancel". It returns `True` on confirm, `False` on cancel or escape.

Example body: `"Deleting KD9ABC will hide 42 messages and 7 bulletins. This cannot be undone."`

### Manage Screen Changes

`OperatorManageScreen` and `NodeManageScreen` each gain a "Delete" button per row (error variant). The Delete button is hidden for the `is_default` row (the "★ Active" badge row) — deleting the active operator/node is blocked in the UI.

Clicking Delete:
1. Fetches dependent counts via `count_*_dependents`
2. Builds and pushes `DeleteConfirmScreen`
3. On `True`: calls the soft-delete method, recomposes

`InterfaceManageScreen` replaces the existing immediate hard-delete with the same `DeleteConfirmScreen` flow. Dependent count is the number of non-deleted nodes referencing the interface.

---

## Section 3: Clickable Status Bar Identity Pickers

### Status Bar Refactor

The right-side `Label` in `StatusBar` is replaced with three `Button` widgets:

- `#identity_operator`
- `#identity_node`  
- `#identity_interface`

Buttons are styled to look like plain text (no border, background matches status bar, `color: $text`, `cursor: pointer`). Each button is only visible when its reactive value is non-empty.

When pressed, the button posts a `StatusBar.IdentityClicked` message with `kind: str` (`"operator"`, `"node"`, or `"interface"`).

### Picker Modals

`OpenPacketApp` handles `StatusBar.IdentityClicked` and pushes the appropriate picker:

**`OperatorPickerScreen(db: Database)`**
- Lists all non-deleted operators, one row per operator
- Each row: label text + "Select" button
- Footer: "Add New" button (primary) → pushes `OperatorSetupScreen`; on save, inserts and recomposes
- Selecting an operator: `db.clear_default_operator()`, set `is_default=True`, `db.update_operator()`, dismiss with `needs_restart=True`

**`NodePickerScreen(db: Database)`**
- Same pattern for nodes
- "Add New" → pushes `NodeSetupScreen`

**`InterfacePickerScreen(db: Database)`**
- Same pattern for interfaces
- Selecting an interface: calls `db.update_node(active_node)` with the new `interface_id` set, then dismisses with `needs_restart=True`
- "Add New" → pushes `InterfaceSetupScreen`

All three pickers are read-only selections — no Edit or Delete. Full management remains in the Settings menu manage screens.

`_on_manage_result` in `OpenPacketApp` handles the `needs_restart` signal from pickers the same way it does from manage screens.

### Row Layout

Picker rows reuse the same CSS class pattern (`.row`, `.row-label`, `.row Button`) as the existing manage screens for visual consistency.

---

## Affected Files

| File | Change |
|------|--------|
| `open_packet/config/config.py` | Deleted |
| `open_packet/store/database.py` | Migrations, new soft-delete and count methods |
| `open_packet/store/settings.py` | New — typed Settings wrapper |
| `open_packet/ui/tui/app.py` | Remove AppConfig dependency, handle IdentityClicked |
| `open_packet/ui/tui/widgets/status_bar.py` | Replace right Label with three Buttons, add IdentityClicked message |
| `open_packet/ui/tui/screens/settings.py` | Add "General" button |
| `open_packet/ui/tui/screens/general_settings.py` | New — GeneralSettingsScreen |
| `open_packet/ui/tui/screens/delete_confirm.py` | New — DeleteConfirmScreen |
| `open_packet/ui/tui/screens/manage_operators.py` | Add Delete button + flow |
| `open_packet/ui/tui/screens/manage_nodes.py` | Add Delete button + flow |
| `open_packet/ui/tui/screens/manage_interfaces.py` | Replace hard delete with confirmation flow |
| `open_packet/ui/tui/screens/operator_picker.py` | New — OperatorPickerScreen |
| `open_packet/ui/tui/screens/node_picker.py` | New — NodePickerScreen |
| `open_packet/ui/tui/screens/interface_picker.py` | New — InterfacePickerScreen |
| `open_packet/__init__.py` or `__main__.py` | Update main() for new CLI args |
| `pyproject.toml` | Remove `pyyaml` dependency (only used in deleted `config/config.py`) |
