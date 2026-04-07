# Settings Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace YAML config with SQLite-backed settings, add soft-delete to all DB tables, and make status bar identity segments clickable pickers.

**Architecture:** Settings live in a `settings` key-value table in SQLite, read via a typed `Settings` wrapper. All five DB tables gain `deleted=1` soft-delete; deleted rows stay as sync sentinels. The status bar right side becomes three clickable Button widgets that push mini-picker modals.

**Tech Stack:** Python 3.11+, Textual (TUI), SQLite via custom `Database` class, pytest + pytest-asyncio for tests.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `open_packet/store/settings.py` | Typed Settings wrapper over `Database.get_setting`/`set_setting` |
| Modify | `open_packet/store/database.py` | Settings table, soft-delete columns/methods, count methods, filter `deleted=0` in all `list_*` queries |
| Delete | `open_packet/config/config.py` | Eliminated; `db_path` moves to CLI/env, rest moves to Settings |
| Modify | `open_packet/engine/engine.py` | Replace `config=AppConfig` param with `auto_discover: bool = True` |
| Modify | `open_packet/ui/tui/app.py` | Replace `AppConfig` param with `db_path: str`; wire Settings; handle `IdentityClicked` |
| Modify | `open_packet/ui/tui/widgets/status_bar.py` | Replace right `Label` with three `Button` widgets + `IdentityClicked` message |
| Modify | `open_packet/ui/tui/screens/settings.py` | Add "General" button |
| Create | `open_packet/ui/tui/screens/general_settings.py` | Form for `export_path`, `console_visible`, `console_buffer`, `auto_discover` |
| Create | `open_packet/ui/tui/screens/delete_confirm.py` | Reusable confirmation modal with delete/cancel |
| Modify | `open_packet/ui/tui/screens/manage_operators.py` | Add Delete button + `DeleteConfirmScreen` flow |
| Modify | `open_packet/ui/tui/screens/manage_nodes.py` | Add Delete button + `DeleteConfirmScreen` flow |
| Modify | `open_packet/ui/tui/screens/manage_interfaces.py` | Replace hard delete with `soft_delete_interface` + `DeleteConfirmScreen` |
| Create | `open_packet/ui/tui/screens/operator_picker.py` | Mini picker: list operators + Select + Add New |
| Create | `open_packet/ui/tui/screens/node_picker.py` | Mini picker: list nodes + Select + Add New |
| Create | `open_packet/ui/tui/screens/interface_picker.py` | Mini picker: list interfaces + Select + Add New |
| Modify | `pyproject.toml` | Remove `pyyaml` dependency |
| Create | `tests/test_store/test_settings.py` | Settings wrapper tests |
| Create | `tests/test_store/test_soft_delete.py` | Soft-delete DB method tests |
| Delete | `tests/test_config/test_config.py` | Replaced by `test_settings.py` |
| Modify | `tests/test_ui/test_tui.py` | Replace `AppConfig` fixture; adapt to new `OpenPacketApp(db_path=...)` |
| Modify | `tests/test_ui/test_setup_screens.py` | Same AppConfig → db_path replacement |
| Modify | `tests/test_ui/test_status_bar.py` | Update for button-based right side |
| Create | `tests/test_ui/test_picker_screens.py` | Picker modal tests |
| Modify | `tests/test_engine/test_engine.py` | Replace `config=AppConfig(...)` with `auto_discover=` |
| Modify | `tests/test_engine/test_integration.py` | Same engine config replacement |
| Modify | `tests/test_store/test_database_helpers.py` | Update `delete_interface` → `soft_delete_interface` tests |

---

## Task 1: Settings Table and Settings Wrapper

**Files:**
- Create: `tests/test_store/test_settings.py`
- Modify: `open_packet/store/database.py`
- Create: `open_packet/store/settings.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_store/test_settings.py`:

```python
import pytest
from open_packet.store.database import Database
from open_packet.store.settings import Settings


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "test.db"))
    d.initialize()
    yield d
    d.close()


def test_settings_defaults(db):
    s = Settings(db)
    assert "open-packet" in s.export_path
    assert s.console_visible is False
    assert s.console_buffer == 500
    assert s.auto_discover is True


def test_settings_set_export_path(db):
    s = Settings(db)
    s.export_path = "/tmp/my-export"
    assert s.export_path == "/tmp/my-export"


def test_settings_set_console_visible(db):
    s = Settings(db)
    s.console_visible = True
    assert s.console_visible is True


def test_settings_set_console_buffer(db):
    s = Settings(db)
    s.console_buffer = 1000
    assert s.console_buffer == 1000


def test_settings_set_auto_discover(db):
    s = Settings(db)
    s.auto_discover = False
    assert s.auto_discover is False


def test_settings_persisted_across_instances(db):
    s1 = Settings(db)
    s1.export_path = "/tmp/persistent"
    s2 = Settings(db)
    assert s2.export_path == "/tmp/persistent"
```

- [ ] **Step 2: Run test to verify it fails**

```
uv run pytest tests/test_store/test_settings.py -v
```
Expected: `ModuleNotFoundError: No module named 'open_packet.store.settings'`

- [ ] **Step 3: Add `settings` table to `Database._create_schema()`**

In `open_packet/store/database.py`, inside the `executescript` string in `_create_schema()`, add after `node_neighbors`:

```sql
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
```

- [ ] **Step 4: Insert defaults in `Database.initialize()`**

In `open_packet/store/database.py`, after the existing `ALTER TABLE` migrations in `initialize()`, add:

```python
        for key, value in [
            ("export_path", "~/.local/share/open-packet/export"),
            ("console_visible", "false"),
            ("console_buffer", "500"),
            ("auto_discover", "true"),
        ]:
            self._conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        self._conn.commit()
```

- [ ] **Step 5: Add `get_setting` and `set_setting` to `Database`**

In `open_packet/store/database.py`, add these methods after `close()`:

```python
    def get_setting(self, key: str) -> str:
        assert self._conn
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown setting: {key!r}")
        return row[0]

    def set_setting(self, key: str, value: str) -> None:
        assert self._conn
        self._conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._conn.commit()
```

- [ ] **Step 6: Create `open_packet/store/settings.py`**

```python
from __future__ import annotations
from open_packet.store.database import Database


class Settings:
    def __init__(self, db: Database) -> None:
        self._db = db

    @property
    def export_path(self) -> str:
        return self._db.get_setting("export_path")

    @export_path.setter
    def export_path(self, value: str) -> None:
        self._db.set_setting("export_path", value)

    @property
    def console_visible(self) -> bool:
        return self._db.get_setting("console_visible") == "true"

    @console_visible.setter
    def console_visible(self, value: bool) -> None:
        self._db.set_setting("console_visible", "true" if value else "false")

    @property
    def console_buffer(self) -> int:
        return int(self._db.get_setting("console_buffer"))

    @console_buffer.setter
    def console_buffer(self, value: int) -> None:
        self._db.set_setting("console_buffer", str(value))

    @property
    def auto_discover(self) -> bool:
        return self._db.get_setting("auto_discover") == "true"

    @auto_discover.setter
    def auto_discover(self, value: bool) -> None:
        self._db.set_setting("auto_discover", "true" if value else "false")
```

- [ ] **Step 7: Run tests to verify they pass**

```
uv run pytest tests/test_store/test_settings.py -v
```
Expected: 6 tests PASS

- [ ] **Step 8: Commit**

```bash
git add open_packet/store/settings.py open_packet/store/database.py tests/test_store/test_settings.py
git commit -m "feat: add settings table and Settings wrapper"
```

---

## Task 2: Remove AppConfig from Engine

**Files:**
- Modify: `open_packet/engine/engine.py`
- Modify: `tests/test_engine/test_engine.py`

- [ ] **Step 1: Update `Engine.__init__` signature**

In `open_packet/engine/engine.py`, replace the `__init__` signature and config setup lines:

Old:
```python
    def __init__(
        self,
        command_queue: queue.Queue,
        event_queue: queue.Queue,
        store: Store,
        operator: Operator,
        node_record: Node,
        connection: ConnectionBase,
        node: NodeBase,
        export_path: Optional[str] = None,
        config=None,
    ):
        ...
        from open_packet.config.config import AppConfig
        self._config = config or AppConfig()
```

New:
```python
    def __init__(
        self,
        command_queue: queue.Queue,
        event_queue: queue.Queue,
        store: Store,
        operator: Operator,
        node_record: Node,
        connection: ConnectionBase,
        node: NodeBase,
        export_path: Optional[str] = None,
        auto_discover: bool = True,
    ):
        ...
        self._auto_discover = auto_discover
```

- [ ] **Step 2: Replace `self._config.nodes.auto_discover` usage**

In `open_packet/engine/engine.py` at line 309, replace:
```python
            if self._config.nodes.auto_discover:
```
with:
```python
            if self._auto_discover:
```

- [ ] **Step 3: Update engine tests that pass `config=`**

In `tests/test_engine/test_engine.py`, find the two places that build `AppConfig` and pass `config=cfg`:

First occurrence (around line 407-453):
```python
# Old — find and replace this block:
from open_packet.config.config import AppConfig, NodesConfig
...
cfg = AppConfig(nodes=NodesConfig(auto_discover=auto_discover))
...
Engine(..., config=cfg, ...)
```

Replace the import line with nothing (delete it), and change the Engine call to:
```python
Engine(..., auto_discover=auto_discover, ...)
```

Second occurrence (around line 594-599):
```python
# Old:
cfg = AppConfig(nodes=NodesConfig(auto_discover=False))
...
Engine(connection=TrackingConnection(), node=mock_node, config=cfg, ...)
```

Replace with:
```python
Engine(connection=TrackingConnection(), node=mock_node, auto_discover=False, ...)
```

Also remove the `from open_packet.config.config import AppConfig, NodesConfig` import at the top of the auto_discover test block.

- [ ] **Step 4: Update `test_integration.py`**

In `tests/test_engine/test_integration.py` line 18 and 88:

Remove:
```python
from open_packet.config.config import AppConfig, NodesConfig
```

Change line 88 from:
```python
            config=AppConfig(nodes=NodesConfig(auto_discover=False)),
```
to:
```python
            auto_discover=False,
```

- [ ] **Step 5: Run engine tests to verify they pass**

```
uv run pytest tests/test_engine/ -v
```
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add open_packet/engine/engine.py tests/test_engine/test_engine.py tests/test_engine/test_integration.py
git commit -m "refactor: replace AppConfig in Engine with auto_discover bool"
```

---

## Task 3: Remove AppConfig from app.py and Tests

**Files:**
- Modify: `open_packet/ui/tui/app.py`
- Modify: `tests/test_ui/test_tui.py`
- Modify: `tests/test_ui/test_setup_screens.py`
- Delete: `open_packet/config/config.py`
- Delete: `tests/test_config/test_config.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Rewrite `OpenPacketApp.__init__` and remove AppConfig imports**

In `open_packet/ui/tui/app.py`, replace the imports and class init:

Remove these imports:
```python
from open_packet.config.config import AppConfig, load_config
```

Add this import after existing store imports:
```python
from open_packet.store.settings import Settings
```

Replace `__init__`:
```python
    def __init__(self, db_path: str, console_log: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self._db_path = db_path
        self._console_log = console_log
        self._cmd_queue: queue.Queue = queue.Queue()
        self._evt_queue: queue.Queue = queue.Queue()
        self._engine: Optional[Engine] = None
        self._selected_message = None
        self._store: Optional[Store] = None
        self._settings: Optional[Settings] = None
        self._active_operator: Optional[Operator] = None
        self._active_node: Optional[Node] = None
        self._active_interface: Optional[Interface] = None
        self._active_folder = "Inbox"
        self._active_category = ""
        self._db: Optional[Database] = None
        self._pending_neighbor_prompts: list = []
        self._terminal_sessions: list[TerminalSession] = []
        self._active_session_idx: Optional[int] = None
```

- [ ] **Step 2: Update `_init_engine` to use `self._db_path` and create `Settings`**

In `open_packet/ui/tui/app.py`, replace the first line of `_init_engine`:
```python
# Old:
        db_path = os.path.expanduser(self.config.store.db_path)
# New:
        db_path = os.path.expanduser(self._db_path)
```

After `db.initialize()`, add:
```python
        self._settings = Settings(db)
```

- [ ] **Step 3: Update `_start_engine` to use Settings**

In `open_packet/ui/tui/app.py`, replace the `export_path` block and Engine call:

```python
        export_path = (
            os.path.expanduser(self._settings.export_path)
            if self._settings and self._settings.export_path else None
        )

        self._engine = Engine(
            command_queue=self._cmd_queue,
            event_queue=self._evt_queue,
            store=store,
            operator=operator,
            node_record=node_record,
            connection=connection,
            node=node,
            export_path=export_path,
            auto_discover=self._settings.auto_discover if self._settings else True,
        )
```

- [ ] **Step 4: Rewrite `main()`**

In `open_packet/ui/tui/app.py`, replace `DEFAULT_CONFIG_PATH` constant and `main()`:

Remove:
```python
DEFAULT_CONFIG_PATH = "~/.config/open-packet/config.yaml"
```

Replace `main()`:
```python
def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(prog="open-packet")
    parser.add_argument("--db-path", default=None, help="Path to SQLite database")
    parser.add_argument("--log-path", default=None, help="Path to log file")
    parser.add_argument("--console-log", default=None, help="Path to console frame log")
    args = parser.parse_args()

    db_path = (
        args.db_path
        or os.environ.get("OPEN_PACKET_DB_PATH")
        or "~/.local/share/open-packet/messages.db"
    )
    log_path = (
        args.log_path
        or os.environ.get("OPEN_PACKET_LOG_PATH")
        or "~/.local/share/open-packet/open-packet.log"
    )
    console_log = args.console_log or os.environ.get("OPEN_PACKET_CONSOLE_LOG")

    _setup_logging(log_path)
    app = OpenPacketApp(db_path=db_path, console_log=console_log)
    app.run()
```

- [ ] **Step 5: Update `test_tui.py` fixture and all `OpenPacketApp` calls**

In `tests/test_ui/test_tui.py`, replace the imports and fixture:

Remove:
```python
from open_packet.config.config import AppConfig, StoreConfig, UIConfig
```

Replace the fixture:
```python
@pytest.fixture
def app_db_path(tmp_path):
    return str(tmp_path / "test.db")
```

For every test that uses `app_config` as a parameter, replace with `app_db_path`. Change every line that sets `app_config.store.db_path = str(tmp_path / "test.db")` to just use `app_db_path` (already the correct path).

Change every:
```python
app = OpenPacketApp(config=app_config)
```
to:
```python
app = OpenPacketApp(db_path=app_db_path)
```

For tests that use both `app_config` and `tmp_path`, remove the `app_config.store.db_path = str(tmp_path / "test.db")` line since `app_db_path` already points there.

- [ ] **Step 6: Update `test_setup_screens.py` fixture and calls**

In `tests/test_ui/test_setup_screens.py`, remove:
```python
from open_packet.config.config import AppConfig, StoreConfig, UIConfig
```

Replace the `base_config` fixture:
```python
@pytest.fixture
def base_config(tmp_path):
    return str(tmp_path / "test.db")
```

Change every:
```python
app = OpenPacketApp(config=base_config)
```
to:
```python
app = OpenPacketApp(db_path=base_config)
```

- [ ] **Step 7: Delete config module and its tests**

```bash
rm open_packet/config/config.py
rm tests/test_config/test_config.py
rmdir open_packet/config  # if __init__.py is the only remaining file, remove that too
```

Also remove the `open_packet/config/__init__.py` if it only has a pass or is empty.

- [ ] **Step 8: Remove pyyaml from pyproject.toml**

In `pyproject.toml`, remove the line:
```
    "pyyaml>=6.0",
```

Run:
```
uv sync
```

- [ ] **Step 9: Run all tests to verify**

```
uv run pytest -v
```
Expected: all tests PASS (test_config/ is gone, all other tests still pass)

- [ ] **Step 10: Commit**

```bash
git add -u
git add open_packet/ui/tui/app.py pyproject.toml
git commit -m "feat: remove YAML config; bootstrap from CLI/env; settings in SQLite"
```

---

## Task 4: GeneralSettingsScreen

**Files:**
- Create: `open_packet/ui/tui/screens/general_settings.py`
- Modify: `open_packet/ui/tui/screens/settings.py`
- Modify: `open_packet/ui/tui/app.py`

- [ ] **Step 1: Create `GeneralSettingsScreen`**

Create `open_packet/ui/tui/screens/general_settings.py`:

```python
from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Input, Switch
from textual.containers import Vertical, Horizontal
from open_packet.store.settings import Settings


class GeneralSettingsScreen(ModalScreen):
    DEFAULT_CSS = """
    GeneralSettingsScreen {
        align: center middle;
    }
    GeneralSettingsScreen > Vertical {
        width: 60;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    GeneralSettingsScreen .field-row {
        height: 3;
        margin-bottom: 1;
    }
    GeneralSettingsScreen .field-label {
        width: 20;
        content-align: left middle;
    }
    GeneralSettingsScreen .field-input {
        width: 1fr;
    }
    GeneralSettingsScreen .footer-row {
        height: 3;
        margin-top: 1;
        align: right middle;
    }
    GeneralSettingsScreen .footer-row Button {
        width: auto;
        min-width: 12;
        margin: 0 0 0 1;
    }
    """

    def __init__(self, settings: Settings, **kwargs):
        super().__init__(**kwargs)
        self._settings = settings

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("General Settings")
            with Horizontal(classes="field-row"):
                yield Label("Export Path", classes="field-label")
                yield Input(
                    value=self._settings.export_path,
                    id="export_path_field",
                    classes="field-input",
                )
            with Horizontal(classes="field-row"):
                yield Label("Console Buffer", classes="field-label")
                yield Input(
                    value=str(self._settings.console_buffer),
                    id="console_buffer_field",
                    classes="field-input",
                )
            with Horizontal(classes="field-row"):
                yield Label("Auto-Discover", classes="field-label")
                yield Switch(
                    value=self._settings.auto_discover,
                    id="auto_discover_field",
                )
            with Horizontal(classes="footer-row"):
                yield Button("Save", id="save_btn", variant="primary")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save_btn":
            self._save()
        else:
            self.dismiss(False)

    def _save(self) -> None:
        export_path = self.query_one("#export_path_field", Input).value.strip()
        console_buffer_raw = self.query_one("#console_buffer_field", Input).value.strip()
        auto_discover = self.query_one("#auto_discover_field", Switch).value

        try:
            console_buffer = int(console_buffer_raw)
        except ValueError:
            self.app.notify("Console buffer must be a number", severity="error")
            return

        old_auto_discover = self._settings.auto_discover
        self._settings.export_path = export_path
        self._settings.console_buffer = console_buffer
        self._settings.auto_discover = auto_discover

        needs_restart = auto_discover != old_auto_discover
        self.dismiss(needs_restart)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)
```

- [ ] **Step 2: Add "General" button to `SettingsScreen`**

In `open_packet/ui/tui/screens/settings.py`, add the button before "Close":

```python
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Settings")
            yield Button("General", id="general_btn")
            yield Button("Operator", id="operator_btn")
            yield Button("Node", id="node_btn")
            yield Button("Interfaces", id="interfaces_btn")
            yield Button("Close", id="close_btn")
```

Add the handler in `on_button_pressed`:
```python
        if event.button.id == "general_btn":
            self.dismiss("general")
        elif event.button.id == "operator_btn":
```

- [ ] **Step 3: Wire "general" result in `app.py`**

In `open_packet/ui/tui/app.py`, in `_on_settings_result`, add before the `elif result == "operator":` block:

```python
        if result == "general":
            if self._settings:
                from open_packet.ui.tui.screens.general_settings import GeneralSettingsScreen
                self.push_screen(
                    GeneralSettingsScreen(self._settings),
                    callback=self._on_manage_result,
                )
            return
```

- [ ] **Step 4: Run tests to verify**

```
uv run pytest tests/test_ui/ -v
```
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add open_packet/ui/tui/screens/general_settings.py \
        open_packet/ui/tui/screens/settings.py \
        open_packet/ui/tui/app.py
git commit -m "feat: add GeneralSettingsScreen for export_path, console_buffer, auto_discover"
```

---

## Task 5: Soft-Delete DB Layer

**Files:**
- Create: `tests/test_store/test_soft_delete.py`
- Modify: `open_packet/store/database.py`
- Modify: `tests/test_store/test_database_helpers.py`

- [ ] **Step 1: Write failing tests for soft-delete methods**

Create `tests/test_store/test_soft_delete.py`:

```python
import pytest
from open_packet.store.database import Database
from open_packet.store.models import Operator, Node, Interface


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "test.db"))
    d.initialize()
    yield d
    d.close()


def test_soft_delete_operator_hides_from_list(db):
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=False))
    db.soft_delete_operator(op.id)
    assert all(o.id != op.id for o in db.list_operators())


def test_soft_delete_operator_hides_from_get(db):
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=False))
    db.soft_delete_operator(op.id)
    assert db.get_operator(op.id) is None


def test_soft_delete_operator_clears_default(db):
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=True))
    db.soft_delete_operator(op.id)
    assert db.get_default_operator() is None


def test_soft_delete_node_hides_from_list(db):
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=False))
    db.soft_delete_node(node.id)
    assert all(n.id != node.id for n in db.list_nodes())


def test_soft_delete_node_hides_from_get(db):
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=False))
    db.soft_delete_node(node.id)
    assert db.get_node(node.id) is None


def test_soft_delete_node_clears_default(db):
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    db.soft_delete_node(node.id)
    assert db.get_default_node() is None


def test_soft_delete_interface_hides_from_list(db):
    iface = db.insert_interface(Interface(label="TNC", iface_type="kiss_tcp", host="localhost", port=8910))
    db.soft_delete_interface(iface.id)
    assert all(i.id != iface.id for i in db.list_interfaces())


def test_soft_delete_interface_hides_from_get(db):
    iface = db.insert_interface(Interface(label="TNC", iface_type="kiss_tcp", host="localhost", port=8910))
    db.soft_delete_interface(iface.id)
    assert db.get_interface(iface.id) is None


def test_soft_delete_interface_blocked_by_active_node(db):
    iface = db.insert_interface(Interface(label="TNC", iface_type="kiss_tcp", host="localhost", port=8910))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    with pytest.raises(ValueError, match="referenced by one or more nodes"):
        db.soft_delete_interface(iface.id)


def test_soft_delete_interface_allowed_when_node_also_deleted(db):
    iface = db.insert_interface(Interface(label="TNC", iface_type="kiss_tcp", host="localhost", port=8910))
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
                               is_default=True, interface_id=iface.id))
    db.soft_delete_node(node.id)
    db.soft_delete_interface(iface.id)  # should not raise
    assert db.get_interface(iface.id) is None


def test_count_operator_dependents(db):
    from open_packet.store.models import Message, Bulletin
    from datetime import datetime, timezone
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=True))
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    from open_packet.store.store import Store
    store = Store(db)
    store.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="001",
        from_call="W0TEST", to_call="KD9ABC", subject="Hello", body="Hi",
        timestamp=datetime.now(timezone.utc),
    ))
    messages, bulletins = db.count_operator_dependents(op.id)
    assert messages == 1
    assert bulletins == 0


def test_count_node_dependents(db):
    from open_packet.store.models import Message
    from datetime import datetime, timezone
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=True))
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    from open_packet.store.store import Store
    store = Store(db)
    store.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="001",
        from_call="W0TEST", to_call="KD9ABC", subject="Hello", body="Hi",
        timestamp=datetime.now(timezone.utc),
    ))
    messages, bulletins = db.count_node_dependents(node.id)
    assert messages == 1
    assert bulletins == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_store/test_soft_delete.py -v
```
Expected: `AttributeError: 'Database' object has no attribute 'soft_delete_operator'`

- [ ] **Step 3: Add `deleted` column migrations for all five tables**

In `open_packet/store/database.py`, in `initialize()`, add after the existing migrations:

```python
        for table in ("operators", "nodes", "interfaces", "bulletins"):
            try:
                self._conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0"
                )
                self._conn.commit()
            except sqlite3.OperationalError:
                pass  # column already exists
```

(Messages already have `deleted`.)

- [ ] **Step 4: Add `WHERE deleted=0` to all `list_*` and `get_*` queries**

In `open_packet/store/database.py`, update these methods:

`get_operator`:
```python
        row = self._conn.execute(
            "SELECT * FROM operators WHERE id=? AND deleted=0", (id,)
        ).fetchone()
```

`get_default_operator`:
```python
        row = self._conn.execute(
            "SELECT * FROM operators WHERE is_default=1 AND deleted=0 LIMIT 1"
        ).fetchone()
```

`list_operators`:
```python
        rows = self._conn.execute(
            "SELECT * FROM operators WHERE deleted=0 ORDER BY id"
        ).fetchall()
```

`get_node`:
```python
        row = self._conn.execute(
            "SELECT * FROM nodes WHERE id=? AND deleted=0", (id,)
        ).fetchone()
```

`get_default_node`:
```python
        row = self._conn.execute(
            "SELECT * FROM nodes WHERE is_default=1 AND deleted=0 LIMIT 1"
        ).fetchone()
```

`list_nodes`:
```python
        rows = self._conn.execute(
            "SELECT * FROM nodes WHERE deleted=0 ORDER BY id"
        ).fetchall()
```

`get_interface`:
```python
        row = self._conn.execute(
            "SELECT * FROM interfaces WHERE id=? AND deleted=0", (id,)
        ).fetchone()
```

`list_interfaces`:
```python
        rows = self._conn.execute(
            "SELECT * FROM interfaces WHERE deleted=0 ORDER BY id"
        ).fetchall()
```

- [ ] **Step 5: Add soft-delete and count methods to `Database`**

In `open_packet/store/database.py`, add these methods after `clear_default_node`:

```python
    def soft_delete_operator(self, op_id: int) -> None:
        assert self._conn
        self._conn.execute(
            "UPDATE operators SET deleted=1, is_default=0 WHERE id=?", (op_id,)
        )
        self._conn.commit()

    def soft_delete_node(self, node_id: int) -> None:
        assert self._conn
        self._conn.execute(
            "UPDATE nodes SET deleted=1, is_default=0 WHERE id=?", (node_id,)
        )
        self._conn.commit()

    def soft_delete_interface(self, iface_id: int) -> None:
        assert self._conn
        count = self._conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE interface_id=? AND deleted=0", (iface_id,)
        ).fetchone()[0]
        if count > 0:
            raise ValueError(
                f"Cannot delete interface {iface_id}: it is referenced by one or more nodes"
            )
        self._conn.execute(
            "UPDATE interfaces SET deleted=1 WHERE id=?", (iface_id,)
        )
        self._conn.commit()

    def count_operator_dependents(self, op_id: int) -> tuple[int, int]:
        assert self._conn
        msg_count = self._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE operator_id=?", (op_id,)
        ).fetchone()[0]
        bul_count = self._conn.execute(
            "SELECT COUNT(*) FROM bulletins WHERE operator_id=?", (op_id,)
        ).fetchone()[0]
        return (msg_count, bul_count)

    def count_node_dependents(self, node_id: int) -> tuple[int, int]:
        assert self._conn
        msg_count = self._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE node_id=?", (node_id,)
        ).fetchone()[0]
        bul_count = self._conn.execute(
            "SELECT COUNT(*) FROM bulletins WHERE node_id=?", (node_id,)
        ).fetchone()[0]
        return (msg_count, bul_count)
```

- [ ] **Step 6: Run soft-delete tests to verify they pass**

```
uv run pytest tests/test_store/test_soft_delete.py -v
```
Expected: all tests PASS

- [ ] **Step 7: Update `test_database_helpers.py` for renamed interface delete**

In `tests/test_store/test_database_helpers.py`, find `test_delete_interface` and `test_delete_interface_with_linked_node_raises`. Update both to use `soft_delete_interface`:

```python
def test_delete_interface(db):
    iface = db.insert_interface(Interface(label="Temp", iface_type="kiss_serial", device="/dev/ttyUSB0", baud=9600))
    db.soft_delete_interface(iface.id)
    assert db.get_interface(iface.id) is None


def test_delete_interface_with_linked_node_raises(db):
    """Soft-deleting an interface that a non-deleted node references raises ValueError."""
    iface = db.insert_interface(Interface(label="TNC", iface_type="kiss_tcp", host="localhost", port=8910))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    with pytest.raises(ValueError, match="referenced by one or more nodes"):
        db.soft_delete_interface(iface.id)
```

- [ ] **Step 8: Run all store tests**

```
uv run pytest tests/test_store/ -v
```
Expected: all tests PASS

- [ ] **Step 9: Commit**

```bash
git add open_packet/store/database.py \
        tests/test_store/test_soft_delete.py \
        tests/test_store/test_database_helpers.py
git commit -m "feat: soft-delete across all DB tables; sync sentinel behavior preserved"
```

---

## Task 6: DeleteConfirmScreen and Manage Screen Delete Flows

**Files:**
- Create: `open_packet/ui/tui/screens/delete_confirm.py`
- Modify: `open_packet/ui/tui/screens/manage_operators.py`
- Modify: `open_packet/ui/tui/screens/manage_nodes.py`
- Modify: `open_packet/ui/tui/screens/manage_interfaces.py`

- [ ] **Step 1: Create `DeleteConfirmScreen`**

Create `open_packet/ui/tui/screens/delete_confirm.py`:

```python
from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from textual.containers import Vertical, Horizontal


class DeleteConfirmScreen(ModalScreen[bool]):
    DEFAULT_CSS = """
    DeleteConfirmScreen {
        align: center middle;
    }
    DeleteConfirmScreen > Vertical {
        width: 60;
        height: auto;
        border: solid $error;
        background: $surface;
        padding: 1 2;
    }
    DeleteConfirmScreen #confirm_body {
        margin: 1 0;
    }
    DeleteConfirmScreen .footer-row {
        height: 3;
        align: right middle;
    }
    DeleteConfirmScreen .footer-row Button {
        width: auto;
        min-width: 12;
        margin: 0 0 0 1;
    }
    """

    def __init__(self, title: str, body: str, **kwargs):
        super().__init__(**kwargs)
        self._title = title
        self._body = body

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title)
            yield Label(self._body, id="confirm_body")
            with Horizontal(classes="footer-row"):
                yield Button("Delete", id="delete_btn", variant="error")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "delete_btn")

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)
```

- [ ] **Step 2: Add Delete flow to `OperatorManageScreen`**

In `open_packet/ui/tui/screens/manage_operators.py`, add a "Delete" button to each non-default row and handle it:

In `compose()`, inside the operator row loop, add after the `yield Button("Edit", ...)` line:
```python
                            if not op.is_default:
                                yield Button("Delete", id=f"delete_{op.id}", variant="error")
```

In `on_button_pressed`, add a new branch:
```python
        elif btn_id.startswith("delete_"):
            op_id = int(btn_id.split("_")[-1])
            self._confirm_delete(op_id)
```

Add these two new methods:
```python
    def _confirm_delete(self, op_id: int) -> None:
        op = self._db.get_operator(op_id)
        if op is None:
            return
        messages, bulletins = self._db.count_operator_dependents(op_id)
        label = f"{op.callsign}-{op.ssid}" if op.ssid != 0 else op.callsign
        body = (
            f"Deleting {label} will hide {messages} message(s) and "
            f"{bulletins} bulletin(s). This cannot be undone."
        )
        from open_packet.ui.tui.screens.delete_confirm import DeleteConfirmScreen
        self.app.push_screen(
            DeleteConfirmScreen(f"Delete {label}?", body),
            callback=lambda confirmed, oid=op_id: self._on_delete_confirmed(confirmed, oid),
        )

    def _on_delete_confirmed(self, confirmed: bool, op_id: int) -> None:
        if not confirmed:
            return
        self._db.soft_delete_operator(op_id)
        self._needs_restart = True
        self.call_later(self.recompose)
```

- [ ] **Step 3: Add Delete flow to `NodeManageScreen`**

In `open_packet/ui/tui/screens/manage_nodes.py`, apply the same pattern:

In `compose()`, inside the node row loop, after `yield Button("Edit", ...)`:
```python
                            if not node.is_default:
                                yield Button("Delete", id=f"delete_{node.id}", variant="error")
```

In `on_button_pressed`, add:
```python
        elif btn_id.startswith("delete_"):
            node_id = int(btn_id.split("_")[-1])
            self._confirm_delete(node_id)
```

Add new methods:
```python
    def _confirm_delete(self, node_id: int) -> None:
        node = self._db.get_node(node_id)
        if node is None:
            return
        messages, bulletins = self._db.count_node_dependents(node_id)
        label = node.label
        body = (
            f"Deleting {label} will hide {messages} message(s) and "
            f"{bulletins} bulletin(s). This cannot be undone."
        )
        from open_packet.ui.tui.screens.delete_confirm import DeleteConfirmScreen
        self.app.push_screen(
            DeleteConfirmScreen(f"Delete {label}?", body),
            callback=lambda confirmed, nid=node_id: self._on_delete_confirmed(confirmed, nid),
        )

    def _on_delete_confirmed(self, confirmed: bool, node_id: int) -> None:
        if not confirmed:
            return
        self._db.soft_delete_node(node_id)
        self._needs_restart = True
        self.call_later(self.recompose)
```

- [ ] **Step 4: Update `InterfaceManageScreen` to use soft delete with confirmation**

In `open_packet/ui/tui/screens/manage_interfaces.py`, replace the delete handler in `on_button_pressed`:

Old:
```python
        elif btn_id.startswith("delete_"):
            iface_id = int(btn_id.split("_")[-1])
            try:
                self._db.delete_interface(iface_id)
            except ValueError as e:
                self.app.notify(str(e), severity="error")
                return
            self._needs_restart = True
            self.call_later(self.recompose)
```

New:
```python
        elif btn_id.startswith("delete_"):
            iface_id = int(btn_id.split("_")[-1])
            self._confirm_delete(iface_id)
```

Add new methods:
```python
    def _confirm_delete(self, iface_id: int) -> None:
        iface = self._db.get_interface(iface_id)
        if iface is None:
            return
        node_count = self._db._conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE interface_id=? AND deleted=0", (iface_id,)
        ).fetchone()[0]
        if node_count > 0:
            self.app.notify(
                f"Cannot delete: {node_count} node(s) still use this interface.",
                severity="error",
            )
            return
        body = f"Delete interface \"{iface.label}\"? This cannot be undone."
        from open_packet.ui.tui.screens.delete_confirm import DeleteConfirmScreen
        self.app.push_screen(
            DeleteConfirmScreen(f"Delete {iface.label}?", body),
            callback=lambda confirmed, iid=iface_id: self._on_delete_confirmed(confirmed, iid),
        )

    def _on_delete_confirmed(self, confirmed: bool, iface_id: int) -> None:
        if not confirmed:
            return
        self._db.soft_delete_interface(iface_id)
        self._needs_restart = True
        self.call_later(self.recompose)
```

- [ ] **Step 5: Run tests**

```
uv run pytest tests/test_ui/test_manage_screens.py tests/test_store/ -v
```
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add open_packet/ui/tui/screens/delete_confirm.py \
        open_packet/ui/tui/screens/manage_operators.py \
        open_packet/ui/tui/screens/manage_nodes.py \
        open_packet/ui/tui/screens/manage_interfaces.py
git commit -m "feat: soft-delete with confirmation for operators, nodes, and interfaces"
```

---

## Task 7: Clickable Status Bar Segments

**Files:**
- Modify: `open_packet/ui/tui/widgets/status_bar.py`
- Modify: `tests/test_ui/test_status_bar.py`
- Modify: `open_packet/ui/tui/app.py`

- [ ] **Step 1: Rewrite `status_bar.py` with button-based identity section**

Replace the entire content of `open_packet/ui/tui/widgets/status_bar.py`:

```python
from __future__ import annotations
from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Label
from textual.containers import Horizontal
from textual.reactive import reactive
from open_packet.engine.events import ConnectionStatus


class StatusBar(Widget):
    class IdentityClicked(Message):
        def __init__(self, kind: str) -> None:
            super().__init__()
            self.kind = kind

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
        layout: horizontal;
    }
    #status_left {
        width: 1fr;
        content-align: left middle;
    }
    #identity_container {
        width: auto;
        height: 1;
        layout: horizontal;
    }
    #identity_sep {
        width: auto;
        content-align: left middle;
    }
    .identity-btn {
        background: $primary;
        color: $text;
        border: none;
        height: 1;
        min-width: 1;
        padding: 0;
    }
    .identity-btn:hover {
        background: $primary-lighten-1;
    }
    .identity-mid-sep {
        width: auto;
        content-align: left middle;
    }
    """

    status: reactive[ConnectionStatus] = reactive(ConnectionStatus.DISCONNECTED)
    sync_detail: reactive[str] = reactive("")
    last_sync: reactive[str] = reactive("Never")
    operator: reactive[str] = reactive("")
    node: reactive[str] = reactive("")
    interface_label: reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        yield Label("", id="status_left")
        with Horizontal(id="identity_container"):
            yield Label("│  ", id="identity_sep")
            yield Button("", id="identity_operator", classes="identity-btn")
            yield Label("  :  ", classes="identity-mid-sep", id="identity_sep_node")
            yield Button("", id="identity_node", classes="identity-btn")
            yield Label("  :  ", classes="identity-mid-sep", id="identity_sep_iface")
            yield Button("", id="identity_interface", classes="identity-btn")

    def on_mount(self) -> None:
        self._render_left()
        self._render_identity()

    def watch_status(self, _) -> None:
        self._render_left()

    def watch_sync_detail(self, _) -> None:
        self._render_left()

    def watch_last_sync(self, _) -> None:
        self._render_left()

    def watch_operator(self, _) -> None:
        self._render_identity()

    def watch_node(self, _) -> None:
        self._render_identity()

    def watch_interface_label(self, _) -> None:
        self._render_identity()

    def _render_left(self) -> None:
        icon = {
            ConnectionStatus.DISCONNECTED: "○",
            ConnectionStatus.CONNECTING: "◎",
            ConnectionStatus.CONNECTED: "●",
            ConnectionStatus.SYNCING: "⟳",
            ConnectionStatus.ERROR: "✗",
        }.get(self.status, "?")
        status_text = self.status.value.title()
        if self.status == ConnectionStatus.SYNCING and self.sync_detail:
            status_text = f"Syncing: {self.sync_detail}"
        text = f"📻 open-packet  {icon}  {status_text}  | Last sync: {self.last_sync}"
        try:
            self.query_one("#status_left", Label).update(text)
        except NoMatches:
            return

    def _render_identity(self) -> None:
        try:
            any_set = bool(self.operator or self.node or self.interface_label)
            self.query_one("#identity_container").display = any_set
            self.query_one("#identity_operator", Button).label = self.operator
            self.query_one("#identity_operator").display = bool(self.operator)
            self.query_one("#identity_sep_node").display = bool(self.operator and self.node)
            self.query_one("#identity_node", Button).label = self.node
            self.query_one("#identity_node").display = bool(self.node)
            self.query_one("#identity_sep_iface").display = bool(self.node and self.interface_label)
            self.query_one("#identity_interface", Button).label = self.interface_label
            self.query_one("#identity_interface").display = bool(self.interface_label)
        except NoMatches:
            return

    def on_button_pressed(self, event: Button.Pressed) -> None:
        kind_map = {
            "identity_operator": "operator",
            "identity_node": "node",
            "identity_interface": "interface",
        }
        kind = kind_map.get(event.button.id or "")
        if kind:
            event.stop()
            self.post_message(self.IdentityClicked(kind))
```

- [ ] **Step 2: Update `test_status_bar.py` to match new structure**

Replace the entire content of `tests/test_ui/test_status_bar.py`:

```python
from textual.app import App, ComposeResult
from textual.widgets import Button
from open_packet.ui.tui.widgets.status_bar import StatusBar
from open_packet.engine.events import ConnectionStatus
from tests.test_ui.conftest import _label_text


class StatusBarApp(App):
    def compose(self) -> ComposeResult:
        yield StatusBar(id="status_bar")


async def test_left_label_shows_emoji_and_app_name():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        left = app.query_one("#status_left")
        assert "📻 open-packet" in _label_text(left)


async def test_left_label_shows_disconnected_icon_by_default():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        left = app.query_one("#status_left")
        assert "○" in _label_text(left)


async def test_left_label_updates_on_status_change():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.status = ConnectionStatus.CONNECTED
        await pilot.pause()
        text = _label_text(app.query_one("#status_left"))
        assert "●" in text
        assert "Connected" in text


async def test_left_label_updates_on_last_sync_change():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.last_sync = "13:45"
        await pilot.pause()
        assert "13:45" in _label_text(app.query_one("#status_left"))


async def test_identity_hidden_when_all_fields_empty():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        assert not app.query_one("#identity_container").display


async def test_identity_shows_operator_button():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.operator = "W1AW"
        await pilot.pause()
        assert app.query_one("#identity_container").display
        assert str(app.query_one("#identity_operator", Button).label) == "W1AW"


async def test_identity_hides_node_sep_when_node_empty():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.operator = "W1AW"
        await pilot.pause()
        assert not app.query_one("#identity_sep_node").display


async def test_identity_shows_all_three_buttons():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.operator = "W1AW"
        sb.node = "Home BBS"
        sb.interface_label = "Home TNC"
        await pilot.pause()
        assert app.query_one("#identity_container").display
        assert app.query_one("#identity_sep_node").display
        assert app.query_one("#identity_sep_iface").display


async def test_identity_cleared_when_all_empty():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.operator = "W1AW"
        await pilot.pause()
        sb.operator = ""
        await pilot.pause()
        assert not app.query_one("#identity_container").display


async def test_identity_clicked_message_posted_on_operator_click():
    messages = []

    class _App(App):
        def compose(self) -> ComposeResult:
            yield StatusBar()

        def on_status_bar_identity_clicked(self, event: StatusBar.IdentityClicked) -> None:
            messages.append(event.kind)

    app = _App()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.operator = "W1AW"
        await pilot.pause()
        await pilot.click("#identity_operator")
        await pilot.pause()
    assert messages == ["operator"]


async def test_left_label_does_not_contain_triple_dash():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        left = app.query_one("#status_left")
        assert "---" not in _label_text(left)
```

- [ ] **Step 3: Run status bar tests**

```
uv run pytest tests/test_ui/test_status_bar.py -v
```
Expected: all tests PASS

- [ ] **Step 4: Wire `IdentityClicked` handler in `app.py`**

In `open_packet/ui/tui/app.py`, add this import near the top with other widget imports:
```python
from open_packet.ui.tui.widgets.status_bar import StatusBar
```

Add a new handler method after `open_settings`:
```python
    def on_status_bar_identity_clicked(self, event: StatusBar.IdentityClicked) -> None:
        if self._db is None:
            return
        if event.kind == "operator":
            from open_packet.ui.tui.screens.operator_picker import OperatorPickerScreen
            self.push_screen(OperatorPickerScreen(self._db), callback=self._on_manage_result)
        elif event.kind == "node":
            from open_packet.ui.tui.screens.node_picker import NodePickerScreen
            self.push_screen(NodePickerScreen(self._db), callback=self._on_manage_result)
        elif event.kind == "interface":
            if self._active_node:
                from open_packet.ui.tui.screens.interface_picker import InterfacePickerScreen
                self.push_screen(
                    InterfacePickerScreen(self._db, self._active_node),
                    callback=self._on_manage_result,
                )
```

- [ ] **Step 5: Run all tests**

```
uv run pytest -v
```
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add open_packet/ui/tui/widgets/status_bar.py \
        tests/test_ui/test_status_bar.py \
        open_packet/ui/tui/app.py
git commit -m "feat: clickable status bar identity segments with IdentityClicked message"
```

---

## Task 8: Picker Screens

**Files:**
- Create: `open_packet/ui/tui/screens/operator_picker.py`
- Create: `open_packet/ui/tui/screens/node_picker.py`
- Create: `open_packet/ui/tui/screens/interface_picker.py`
- Create: `tests/test_ui/test_picker_screens.py`

- [ ] **Step 1: Create `OperatorPickerScreen`**

Create `open_packet/ui/tui/screens/operator_picker.py`:

```python
from __future__ import annotations
from typing import Optional
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from textual.containers import Vertical, Horizontal, VerticalScroll
from open_packet.store.database import Database
from open_packet.store.models import Operator


class OperatorPickerScreen(ModalScreen):
    DEFAULT_CSS = """
    OperatorPickerScreen {
        align: center middle;
    }
    OperatorPickerScreen > Vertical {
        width: 60;
        height: auto;
        max-height: 80%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    OperatorPickerScreen VerticalScroll {
        height: auto;
        max-height: 20;
    }
    OperatorPickerScreen .row {
        height: 3;
    }
    OperatorPickerScreen .row-label {
        width: 1fr;
        content-align: left middle;
    }
    OperatorPickerScreen .row Button {
        width: auto;
        min-width: 12;
        margin: 0 0 0 1;
    }
    OperatorPickerScreen .footer-row {
        height: 3;
        margin-top: 1;
        align: right middle;
    }
    OperatorPickerScreen .footer-row Button {
        width: auto;
        min-width: 12;
        margin: 0 0 0 1;
    }
    """

    def __init__(self, db: Database, **kwargs):
        super().__init__(**kwargs)
        self._db = db

    def compose(self) -> ComposeResult:
        operators = self._db.list_operators()
        with Vertical():
            yield Label("Select Operator")
            with VerticalScroll():
                if operators:
                    for op in operators:
                        label_text = f"{op.callsign}-{op.ssid}  \"{op.label}\"" if op.ssid != 0 else f"{op.callsign}  \"{op.label}\""
                        with Horizontal(classes="row"):
                            yield Label(label_text, classes="row-label")
                            yield Button("Select", id=f"select_{op.id}", variant="primary")
                else:
                    yield Label("No operators configured.")
            with Horizontal(classes="footer-row"):
                yield Button("Add New", id="add_btn", variant="primary")
                yield Button("Close", id="close_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "close_btn":
            self.dismiss(False)
        elif btn_id == "add_btn":
            from open_packet.ui.tui.screens.setup_operator import OperatorSetupScreen
            self.app.push_screen(OperatorSetupScreen(), callback=self._on_add)
        elif btn_id.startswith("select_"):
            op_id = int(btn_id.split("_")[-1])
            self._select(op_id)

    def _select(self, op_id: int) -> None:
        self._db.clear_default_operator()
        op = self._db.get_operator(op_id)
        if op:
            op.is_default = True
            self._db.update_operator(op)
        self.dismiss(True)

    def _on_add(self, result: Optional[Operator]) -> None:
        if result is None:
            return
        if result.is_default:
            self._db.clear_default_operator()
        self._db.insert_operator(result)
        self.call_later(self.recompose)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)
```

- [ ] **Step 2: Create `NodePickerScreen`**

Create `open_packet/ui/tui/screens/node_picker.py`:

```python
from __future__ import annotations
from typing import Optional
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from textual.containers import Vertical, Horizontal, VerticalScroll
from open_packet.store.database import Database
from open_packet.store.models import Node


class NodePickerScreen(ModalScreen):
    DEFAULT_CSS = """
    NodePickerScreen {
        align: center middle;
    }
    NodePickerScreen > Vertical {
        width: 60;
        height: auto;
        max-height: 80%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    NodePickerScreen VerticalScroll {
        height: auto;
        max-height: 20;
    }
    NodePickerScreen .row {
        height: 3;
    }
    NodePickerScreen .row-label {
        width: 1fr;
        content-align: left middle;
    }
    NodePickerScreen .row Button {
        width: auto;
        min-width: 12;
        margin: 0 0 0 1;
    }
    NodePickerScreen .footer-row {
        height: 3;
        margin-top: 1;
        align: right middle;
    }
    NodePickerScreen .footer-row Button {
        width: auto;
        min-width: 12;
        margin: 0 0 0 1;
    }
    """

    def __init__(self, db: Database, **kwargs):
        super().__init__(**kwargs)
        self._db = db

    def compose(self) -> ComposeResult:
        nodes = self._db.list_nodes()
        with Vertical():
            yield Label("Select Node")
            with VerticalScroll():
                if nodes:
                    for node in nodes:
                        label_text = f"{node.callsign}-{node.ssid}  \"{node.label}\""
                        with Horizontal(classes="row"):
                            yield Label(label_text, classes="row-label")
                            yield Button("Select", id=f"select_{node.id}", variant="primary")
                else:
                    yield Label("No nodes configured.")
            with Horizontal(classes="footer-row"):
                yield Button("Add New", id="add_btn", variant="primary")
                yield Button("Close", id="close_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "close_btn":
            self.dismiss(False)
        elif btn_id == "add_btn":
            from open_packet.ui.tui.screens.setup_node import NodeSetupScreen
            self.app.push_screen(
                NodeSetupScreen(interfaces=self._db.list_interfaces(), db=self._db),
                callback=self._on_add,
            )
        elif btn_id.startswith("select_"):
            node_id = int(btn_id.split("_")[-1])
            self._select(node_id)

    def _select(self, node_id: int) -> None:
        self._db.clear_default_node()
        node = self._db.get_node(node_id)
        if node:
            node.is_default = True
            self._db.update_node(node)
        self.dismiss(True)

    def _on_add(self, result: Optional[Node]) -> None:
        if result is None:
            return
        if result.is_default:
            self._db.clear_default_node()
        self._db.insert_node(result)
        self.call_later(self.recompose)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)
```

- [ ] **Step 3: Create `InterfacePickerScreen`**

Create `open_packet/ui/tui/screens/interface_picker.py`:

```python
from __future__ import annotations
from typing import Optional
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from textual.containers import Vertical, Horizontal, VerticalScroll
from open_packet.store.database import Database
from open_packet.store.models import Interface, Node


class InterfacePickerScreen(ModalScreen):
    DEFAULT_CSS = """
    InterfacePickerScreen {
        align: center middle;
    }
    InterfacePickerScreen > Vertical {
        width: 70;
        height: auto;
        max-height: 80%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    InterfacePickerScreen VerticalScroll {
        height: auto;
        max-height: 20;
    }
    InterfacePickerScreen .row {
        height: 3;
    }
    InterfacePickerScreen .row-label {
        width: 1fr;
        content-align: left middle;
    }
    InterfacePickerScreen .row Button {
        width: auto;
        min-width: 12;
        margin: 0 0 0 1;
    }
    InterfacePickerScreen .footer-row {
        height: 3;
        margin-top: 1;
        align: right middle;
    }
    InterfacePickerScreen .footer-row Button {
        width: auto;
        min-width: 12;
        margin: 0 0 0 1;
    }
    """

    def __init__(self, db: Database, active_node: Node, **kwargs):
        super().__init__(**kwargs)
        self._db = db
        self._active_node = active_node

    def compose(self) -> ComposeResult:
        interfaces = self._db.list_interfaces()
        with Vertical():
            yield Label("Select Interface")
            with VerticalScroll():
                if interfaces:
                    for iface in interfaces:
                        summary = f"{iface.label}  [{iface.iface_type}]"
                        if iface.host:
                            summary += f"  {iface.host}:{iface.port}"
                        elif iface.device:
                            summary += f"  {iface.device}"
                        with Horizontal(classes="row"):
                            yield Label(summary, classes="row-label")
                            yield Button("Select", id=f"select_{iface.id}", variant="primary")
                else:
                    yield Label("No interfaces configured.")
            with Horizontal(classes="footer-row"):
                yield Button("Add New", id="add_btn", variant="primary")
                yield Button("Close", id="close_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "close_btn":
            self.dismiss(False)
        elif btn_id == "add_btn":
            from open_packet.ui.tui.screens.setup_interface import InterfaceSetupScreen
            self.app.push_screen(InterfaceSetupScreen(), callback=self._on_add)
        elif btn_id.startswith("select_"):
            iface_id = int(btn_id.split("_")[-1])
            self._select(iface_id)

    def _select(self, iface_id: int) -> None:
        self._active_node.interface_id = iface_id
        self._db.update_node(self._active_node)
        self.dismiss(True)

    def _on_add(self, result: Optional[Interface]) -> None:
        if result is None:
            return
        self._db.insert_interface(result)
        self.call_later(self.recompose)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)
```

- [ ] **Step 4: Write picker tests**

Create `tests/test_ui/test_picker_screens.py`:

```python
import pytest
from textual.app import App
from open_packet.store.database import Database
from open_packet.store.models import Operator, Node, Interface
from open_packet.ui.tui.screens.operator_picker import OperatorPickerScreen
from open_packet.ui.tui.screens.node_picker import NodePickerScreen
from open_packet.ui.tui.screens.interface_picker import InterfacePickerScreen

_SENTINEL = object()


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "test.db"))
    d.initialize()
    yield d
    d.close()


@pytest.fixture
def db_with_operators(db):
    db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=True))
    db.insert_operator(Operator(callsign="W0TEST", ssid=1, label="car", is_default=False))
    return db


@pytest.fixture
def db_with_nodes(db):
    db.insert_node(Node(label="Home BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    db.insert_node(Node(label="Work BBS", callsign="W0FOO", ssid=0, node_type="bpq", is_default=False))
    return db


class _PickerTestApp(App):
    def __init__(self, screen_factory, **kwargs):
        super().__init__(**kwargs)
        self._factory = screen_factory
        self.dismiss_result = _SENTINEL

    def on_mount(self) -> None:
        self.push_screen(self._factory(), callback=lambda r: setattr(self, "dismiss_result", r))


@pytest.mark.asyncio
async def test_operator_picker_close_returns_false(db_with_operators):
    db = db_with_operators
    app = _PickerTestApp(lambda: OperatorPickerScreen(db))
    async with app.run_test() as pilot:
        await pilot.click("#close_btn")
        await pilot.pause()
    assert app.dismiss_result is False


@pytest.mark.asyncio
async def test_operator_picker_select_changes_default(db_with_operators):
    db = db_with_operators
    ops = db.list_operators()
    non_default = next(o for o in ops if not o.is_default)
    app = _PickerTestApp(lambda: OperatorPickerScreen(db))
    async with app.run_test() as pilot:
        await pilot.click(f"#select_{non_default.id}")
        await pilot.pause()
    assert app.dismiss_result is True
    assert db.get_default_operator().id == non_default.id


@pytest.mark.asyncio
async def test_node_picker_close_returns_false(db_with_nodes):
    db = db_with_nodes
    app = _PickerTestApp(lambda: NodePickerScreen(db))
    async with app.run_test() as pilot:
        await pilot.click("#close_btn")
        await pilot.pause()
    assert app.dismiss_result is False


@pytest.mark.asyncio
async def test_node_picker_select_changes_default(db_with_nodes):
    db = db_with_nodes
    nodes = db.list_nodes()
    non_default = next(n for n in nodes if not n.is_default)
    app = _PickerTestApp(lambda: NodePickerScreen(db))
    async with app.run_test() as pilot:
        await pilot.click(f"#select_{non_default.id}")
        await pilot.pause()
    assert app.dismiss_result is True
    assert db.get_default_node().id == non_default.id


@pytest.mark.asyncio
async def test_interface_picker_select_updates_node(db):
    iface1 = db.insert_interface(Interface(label="TNC1", iface_type="kiss_tcp", host="localhost", port=8910))
    iface2 = db.insert_interface(Interface(label="TNC2", iface_type="kiss_tcp", host="localhost", port=9000))
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
                               is_default=True, interface_id=iface1.id))
    app = _PickerTestApp(lambda: InterfacePickerScreen(db, node))
    async with app.run_test() as pilot:
        await pilot.click(f"#select_{iface2.id}")
        await pilot.pause()
    assert app.dismiss_result is True
    refreshed = db.get_node(node.id)
    assert refreshed.interface_id == iface2.id


@pytest.mark.asyncio
async def test_interface_picker_close_returns_false(db):
    iface = db.insert_interface(Interface(label="TNC", iface_type="kiss_tcp", host="localhost", port=8910))
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
                               is_default=True, interface_id=iface.id))
    app = _PickerTestApp(lambda: InterfacePickerScreen(db, node))
    async with app.run_test() as pilot:
        await pilot.click("#close_btn")
        await pilot.pause()
    assert app.dismiss_result is False
```

- [ ] **Step 5: Run picker tests**

```
uv run pytest tests/test_ui/test_picker_screens.py -v
```
Expected: all 6 tests PASS

- [ ] **Step 6: Run full test suite**

```
uv run pytest -v
```
Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add open_packet/ui/tui/screens/operator_picker.py \
        open_packet/ui/tui/screens/node_picker.py \
        open_packet/ui/tui/screens/interface_picker.py \
        tests/test_ui/test_picker_screens.py
git commit -m "feat: operator/node/interface picker screens with Add New"
```
