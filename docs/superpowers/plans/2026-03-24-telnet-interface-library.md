# TelnetLink + Interface Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Telnet BBS connectivity and a shared radio interface library, with all connection config stored in the database and managed through the TUI.

**Architecture:** A new `Interface` model stores connection details (Telnet, KISS TCP, KISS Serial) in SQLite. `Node` gains an `interface_id` FK. `app.py._start_engine()` uses a `match` on the interface type to build the right `ConnectionBase`. A new `TelnetLink` handles Telnet login/IAC stripping. `NodeSetupScreen` is redesigned to include inline interface creation with a connection type selector.

**Tech Stack:** Python, Textual TUI, SQLite (via custom Database class), `socket` stdlib for TelnetLink, pytest + pytest-asyncio for tests.

---

## File Map

**New files:**
- `open_packet/link/telnet.py` — `TelnetLink(ConnectionBase)`
- `open_packet/ui/tui/screens/setup_interface.py` — `InterfaceSetupScreen` modal
- `open_packet/ui/tui/screens/manage_interfaces.py` — `InterfaceManageScreen`
- `tests/test_link/test_telnet.py` — TelnetLink unit tests

**Modified files:**
- `open_packet/store/models.py` — add `Interface` dataclass; add `interface_id` to `Node`
- `open_packet/store/database.py` — `interfaces` table DDL, `interface_id` migration, Interface CRUD, update Node read/write methods
- `open_packet/config/config.py` — remove connection config; simplify `AppConfig` and `load_config`
- `open_packet/ui/tui/app.py` — match-based engine wiring; `_on_settings_result` interfaces branch (Task 4); NodeSetupScreen push sites updated to pass `interfaces=` and `db=` (Task 5, committed atomically with the new screen signature)
- `open_packet/ui/tui/screens/setup_node.py` — full redesign with dynamic connection section
- `open_packet/ui/tui/screens/settings.py` — add Interfaces button
- `open_packet/ui/tui/screens/manage_nodes.py` — pass `interfaces=` and `db=` to NodeSetupScreen
- `tests/test_config/test_config.py` — rewrite (remove connection tests)
- `tests/test_ui/test_tui.py` — fix `app_config` fixture; update DB setup to include Interface
- `tests/test_ui/test_setup_screens.py` — fix `base_config` fixture; add new node/interface screen tests
- `tests/test_store/test_database_helpers.py` — add Interface CRUD + migration tests

---

## Task 1: Interface model and database layer

**Files:**
- Modify: `open_packet/store/models.py`
- Modify: `open_packet/store/database.py`
- Modify: `tests/test_store/test_database_helpers.py`

- [ ] **Step 1: Write failing tests for Interface CRUD and Node.interface_id**

Add to the bottom of `tests/test_store/test_database_helpers.py`:

```python
from open_packet.store.models import Interface


def test_insert_and_get_interface(db):
    iface = db.insert_interface(Interface(
        label="Home TNC", iface_type="kiss_tcp", host="localhost", port=8910
    ))
    assert iface.id is not None
    fetched = db.get_interface(iface.id)
    assert fetched.label == "Home TNC"
    assert fetched.iface_type == "kiss_tcp"
    assert fetched.host == "localhost"
    assert fetched.port == 8910


def test_list_interfaces(db):
    db.insert_interface(Interface(label="TNC1", iface_type="kiss_tcp", host="localhost", port=8910))
    db.insert_interface(Interface(label="BBS", iface_type="telnet", host="192.168.1.1", port=8023,
                                  username="K0JLB", password="pw"))
    ifaces = db.list_interfaces()
    assert len(ifaces) == 2
    assert ifaces[0].label == "TNC1"
    assert ifaces[1].username == "K0JLB"


def test_update_interface(db):
    iface = db.insert_interface(Interface(label="Old", iface_type="kiss_tcp", host="localhost", port=8910))
    iface.label = "New"
    iface.port = 9000
    db.update_interface(iface)
    fetched = db.get_interface(iface.id)
    assert fetched.label == "New"
    assert fetched.port == 9000


def test_delete_interface(db):
    iface = db.insert_interface(Interface(label="Temp", iface_type="kiss_serial", device="/dev/ttyUSB0", baud=9600))
    db.delete_interface(iface.id)
    assert db.get_interface(iface.id) is None


def test_interface_telnet_fields_round_trip(db):
    iface = db.insert_interface(Interface(
        label="Telnet BBS", iface_type="telnet",
        host="192.168.1.209", port=8023, username="K0JLB", password="secret"
    ))
    fetched = db.get_interface(iface.id)
    assert fetched.host == "192.168.1.209"
    assert fetched.port == 8023
    assert fetched.username == "K0JLB"
    assert fetched.password == "secret"
    assert fetched.device is None
    assert fetched.baud is None


def test_interface_serial_fields_round_trip(db):
    iface = db.insert_interface(Interface(
        label="Serial TNC", iface_type="kiss_serial", device="/dev/ttyUSB0", baud=9600
    ))
    fetched = db.get_interface(iface.id)
    assert fetched.device == "/dev/ttyUSB0"
    assert fetched.baud == 9600
    assert fetched.host is None
    assert fetched.port is None


def test_node_interface_id_round_trip(db):
    iface = db.insert_interface(Interface(label="TNC", iface_type="kiss_tcp", host="localhost", port=8910))
    node = db.insert_node(Node(
        label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
        is_default=True, interface_id=iface.id
    ))
    fetched = db.get_node(node.id)
    assert fetched.interface_id == iface.id


def test_node_interface_id_none_by_default(db):
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    fetched = db.get_node(node.id)
    assert fetched.interface_id is None


def test_interface_id_migration_on_existing_db(tmp_path):
    """Calling initialize() on a pre-existing DB (without interface_id column) adds it cleanly."""
    import sqlite3
    db_path = str(tmp_path / "old.db")
    # Create a DB that looks like the old schema (no interface_id on nodes, no interfaces table)
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            callsign TEXT NOT NULL,
            ssid INTEGER NOT NULL DEFAULT 0,
            node_type TEXT NOT NULL,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()

    d = Database(db_path)
    d.initialize()  # should not raise
    # interface_id column now exists
    conn2 = sqlite3.connect(db_path)
    conn2.row_factory = sqlite3.Row
    row = conn2.execute("SELECT * FROM nodes LIMIT 1").fetchone()
    # Just verify the column exists by checking the table info
    cols = [r["name"] for r in conn2.execute("PRAGMA table_info(nodes)").fetchall()]
    assert "interface_id" in cols
    # interfaces table also created
    tables = [r[0] for r in conn2.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "interfaces" in tables
    conn2.close()
    d.close()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_store/test_database_helpers.py -v 2>&1 | tail -20
```

Expected: FAIL — `ImportError: cannot import name 'Interface' from 'open_packet.store.models'`

- [ ] **Step 3: Add Interface dataclass to models.py**

In `open_packet/store/models.py`, add after the imports and before the `Operator` class:

```python
@dataclass
class Interface:
    id: Optional[int] = None
    label: str = ""
    iface_type: str = ""          # "telnet" | "kiss_tcp" | "kiss_serial"
    host: Optional[str] = None    # telnet + kiss_tcp
    port: Optional[int] = None    # telnet + kiss_tcp
    username: Optional[str] = None  # telnet only
    password: Optional[str] = None  # telnet only
    device: Optional[str] = None  # kiss_serial only
    baud: Optional[int] = None    # kiss_serial only
```

Add `interface_id: Optional[int] = None` to the `Node` dataclass after the `is_default` field:

```python
@dataclass
class Node:
    label: str
    callsign: str
    ssid: int
    node_type: str
    is_default: bool = False
    interface_id: Optional[int] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
```

- [ ] **Step 4: Add Interface to database.py — table DDL, migration, CRUD, and Node method updates**

In `open_packet/store/database.py`:

**4a.** Add `Interface` to the import line at the top:

```python
from open_packet.store.models import Operator, Node, Message, Bulletin, Interface
```

**4b.** Inside `_create_schema()`, add the `interfaces` table to the executescript string (before the final `"""`):

```python
            CREATE TABLE IF NOT EXISTS interfaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                iface_type TEXT NOT NULL,
                host TEXT,
                port INTEGER,
                username TEXT,
                password TEXT,
                device TEXT,
                baud INTEGER
            );
```

**4c.** In `initialize()`, add the `interface_id` migration after the existing `queued` column migration block:

```python
        try:
            self._conn.execute(
                "ALTER TABLE nodes ADD COLUMN interface_id INTEGER REFERENCES interfaces(id)"
            )
            self._conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
```

**4d.** Add Interface CRUD methods after `update_node`:

```python
    def insert_interface(self, iface: Interface) -> Interface:
        assert self._conn
        cur = self._conn.execute(
            """INSERT INTO interfaces (label, iface_type, host, port, username, password, device, baud)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (iface.label, iface.iface_type, iface.host, iface.port,
             iface.username, iface.password, iface.device, iface.baud),
        )
        self._conn.commit()
        return self.get_interface(cur.lastrowid)  # type: ignore

    def get_interface(self, id: int) -> Optional[Interface]:
        assert self._conn
        row = self._conn.execute("SELECT * FROM interfaces WHERE id=?", (id,)).fetchone()
        if not row:
            return None
        return Interface(
            id=row["id"], label=row["label"], iface_type=row["iface_type"],
            host=row["host"], port=row["port"],
            username=row["username"], password=row["password"],
            device=row["device"], baud=row["baud"],
        )

    def list_interfaces(self) -> list[Interface]:
        assert self._conn
        rows = self._conn.execute("SELECT * FROM interfaces ORDER BY id").fetchall()
        return [
            Interface(
                id=r["id"], label=r["label"], iface_type=r["iface_type"],
                host=r["host"], port=r["port"],
                username=r["username"], password=r["password"],
                device=r["device"], baud=r["baud"],
            )
            for r in rows
        ]

    def update_interface(self, iface: Interface) -> None:
        assert self._conn
        assert iface.id is not None, "Cannot update interface without id"
        self._conn.execute(
            """UPDATE interfaces SET label=?, iface_type=?, host=?, port=?,
               username=?, password=?, device=?, baud=? WHERE id=?""",
            (iface.label, iface.iface_type, iface.host, iface.port,
             iface.username, iface.password, iface.device, iface.baud, iface.id),
        )
        self._conn.commit()

    def delete_interface(self, id: int) -> None:
        assert self._conn
        self._conn.execute("DELETE FROM interfaces WHERE id=?", (id,))
        self._conn.commit()
```

**4e.** Update `insert_node` to include `interface_id`:

```python
    def insert_node(self, node: Node) -> Node:
        assert self._conn
        cur = self._conn.execute(
            "INSERT INTO nodes (label, callsign, ssid, node_type, is_default, interface_id) VALUES (?, ?, ?, ?, ?, ?)",
            (node.label, node.callsign, node.ssid, node.node_type, int(node.is_default), node.interface_id),
        )
        self._conn.commit()
        return self.get_node(cur.lastrowid)  # type: ignore
```

**4f.** Update `get_node` to read `interface_id`:

```python
    def get_node(self, id: int) -> Optional[Node]:
        assert self._conn
        row = self._conn.execute("SELECT * FROM nodes WHERE id=?", (id,)).fetchone()
        if not row:
            return None
        return Node(
            id=row["id"], label=row["label"], callsign=row["callsign"],
            ssid=row["ssid"], node_type=row["node_type"],
            is_default=bool(row["is_default"]),
            interface_id=row["interface_id"],
        )
```

**4g.** Update `get_default_node` to read `interface_id`:

```python
    def get_default_node(self) -> Optional[Node]:
        assert self._conn
        row = self._conn.execute(
            "SELECT * FROM nodes WHERE is_default=1 LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return Node(
            id=row["id"], label=row["label"], callsign=row["callsign"],
            ssid=row["ssid"], node_type=row["node_type"],
            is_default=bool(row["is_default"]),
            interface_id=row["interface_id"],
        )
```

**4h.** Update `list_nodes` to read `interface_id`:

```python
    def list_nodes(self) -> list[Node]:
        assert self._conn
        rows = self._conn.execute("SELECT * FROM nodes ORDER BY id").fetchall()
        return [
            Node(
                id=r["id"], label=r["label"], callsign=r["callsign"],
                ssid=r["ssid"], node_type=r["node_type"],
                is_default=bool(r["is_default"]),
                interface_id=r["interface_id"],
            )
            for r in rows
        ]
```

**4i.** Update `update_node` to persist `interface_id`:

```python
    def update_node(self, node: Node) -> None:
        assert self._conn
        assert node.id is not None, "Cannot update node without id"
        self._conn.execute(
            "UPDATE nodes SET label=?, callsign=?, ssid=?, node_type=?, is_default=?, interface_id=? WHERE id=?",
            (node.label, node.callsign, node.ssid, node.node_type,
             int(node.is_default), node.interface_id, node.id),
        )
        self._conn.commit()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_store/test_database_helpers.py -v 2>&1 | tail -30
```

Expected: all tests pass including the 9 new ones.

- [ ] **Step 6: Run the full test suite to check for regressions**

```bash
uv run pytest --tb=short 2>&1 | tail -20
```

Expected: all existing tests still pass (only failures should be none).

- [ ] **Step 7: Commit**

```bash
git add open_packet/store/models.py open_packet/store/database.py tests/test_store/test_database_helpers.py
git commit -m "feat: add Interface model and database layer with Node.interface_id FK"
```

---

## Task 2: Remove connection config from AppConfig

**Files:**
- Modify: `open_packet/config/config.py`
- Modify: `tests/test_config/test_config.py`
- Modify: `tests/test_ui/test_tui.py` (fixture only)
- Modify: `tests/test_ui/test_setup_screens.py` (fixture only)

- [ ] **Step 1: Write the new config tests**

Replace the entire contents of `tests/test_config/test_config.py` with:

```python
import pytest
import tempfile
import os
from open_packet.config.config import AppConfig, StoreConfig, UIConfig, load_config, ConfigError


MINIMAL_YAML = """
store:
  db_path: /tmp/test.db
  export_path: /tmp/export

ui:
  console_visible: false
  console_buffer: 500
"""

YAML_WITH_CONNECTION = """
connection:
  type: kiss_tcp
  host: localhost
  port: 8001

store:
  db_path: /tmp/test.db
  export_path: /tmp/export
"""


def write_yaml(content: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(content)
    f.close()
    return f.name


def test_load_config_store_and_ui():
    path = write_yaml(MINIMAL_YAML)
    try:
        config = load_config(path)
        assert config.store.db_path == "/tmp/test.db"
        assert config.store.export_path == "/tmp/export"
        assert config.ui.console_visible is False
        assert config.ui.console_buffer == 500
        assert config.ui.console_log is None
    finally:
        os.unlink(path)


def test_load_config_ignores_connection_section():
    """A YAML with a legacy 'connection' key is silently accepted."""
    path = write_yaml(YAML_WITH_CONNECTION)
    try:
        config = load_config(path)
        assert config.store.db_path == "/tmp/test.db"
        assert not hasattr(config, "connection")
    finally:
        os.unlink(path)


def test_load_config_missing_file_raises():
    with pytest.raises(ConfigError, match="not found"):
        load_config("/nonexistent/path/config.yaml")


def test_load_config_empty_file_uses_defaults():
    path = write_yaml("")
    try:
        config = load_config(path)
        assert "open-packet" in config.store.db_path
    finally:
        os.unlink(path)


def test_console_log_optional():
    yaml_with_log = MINIMAL_YAML + "\n  console_log: /tmp/console.log\n"
    path = write_yaml(yaml_with_log)
    try:
        config = load_config(path)
        assert config.ui.console_log == "/tmp/console.log"
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Run new config tests to see them fail**

```bash
uv run pytest tests/test_config/test_config.py -v 2>&1 | tail -20
```

Expected: FAIL — `AppConfig` still requires `connection` argument; `TCPConnectionConfig` still exported.

- [ ] **Step 3: Rewrite config.py**

Replace the entire contents of `open_packet/config/config.py` with:

```python
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import yaml


class ConfigError(Exception):
    pass


@dataclass
class StoreConfig:
    db_path: str = "~/.local/share/open-packet/messages.db"
    export_path: str = "~/.local/share/open-packet/export"


@dataclass
class UIConfig:
    console_visible: bool = False
    console_buffer: int = 500
    console_log: Optional[str] = None


@dataclass
class AppConfig:
    store: StoreConfig = field(default_factory=StoreConfig)
    ui: UIConfig = field(default_factory=UIConfig)


def _parse_store(raw: dict) -> StoreConfig:
    return StoreConfig(
        db_path=str(raw.get("db_path", "~/.local/share/open-packet/messages.db")),
        export_path=str(raw.get("export_path", "~/.local/share/open-packet/export")),
    )


def _parse_ui(raw: dict) -> UIConfig:
    return UIConfig(
        console_visible=bool(raw.get("console_visible", False)),
        console_buffer=int(raw.get("console_buffer", 500)),
        console_log=raw.get("console_log"),
    )


def load_config(path: str) -> AppConfig:
    expanded = os.path.expanduser(path)
    if not os.path.exists(expanded):
        raise ConfigError(f"Config file not found: {expanded}")
    with open(expanded) as f:
        raw = yaml.safe_load(f) or {}
    try:
        return AppConfig(
            store=_parse_store(raw.get("store", {})),
            ui=_parse_ui(raw.get("ui", {})),
        )
    except (TypeError, ValueError) as e:
        raise ConfigError(f"Invalid config value: {e}") from e
```

- [ ] **Step 4: Run config tests to verify they pass**

```bash
uv run pytest tests/test_config/test_config.py -v 2>&1 | tail -15
```

Expected: all 5 tests pass.

- [ ] **Step 5: Fix the app_config fixture in test_tui.py**

In `tests/test_ui/test_tui.py`, replace the import line and the `app_config` fixture:

```python
# Remove this import line:
from open_packet.config.config import AppConfig, TCPConnectionConfig, StoreConfig, UIConfig

# Replace with:
from open_packet.config.config import AppConfig, StoreConfig, UIConfig
```

Replace the fixture:

```python
@pytest.fixture
def app_config(tmp_path):
    return AppConfig(
        store=StoreConfig(
            db_path=str(tmp_path / "test.db"),
            export_path=str(tmp_path / "export"),
        ),
        ui=UIConfig(),
    )
```

- [ ] **Step 6: Fix the base_config fixture in test_setup_screens.py**

In `tests/test_ui/test_setup_screens.py`, replace the import line and the `base_config` fixture:

```python
# Remove this import line:
from open_packet.config.config import AppConfig, TCPConnectionConfig, StoreConfig, UIConfig

# Replace with:
from open_packet.config.config import AppConfig, StoreConfig, UIConfig
```

Replace the fixture:

```python
@pytest.fixture
def base_config(tmp_path):
    return AppConfig(
        store=StoreConfig(
            db_path=str(tmp_path / "test.db"),
            export_path=str(tmp_path / "export"),
        ),
        ui=UIConfig(),
    )
```

- [ ] **Step 7: Run the full test suite**

```bash
uv run pytest --tb=short 2>&1 | tail -20
```

Expected: config tests pass. TUI tests that exercise `_start_engine` will FAIL with `AttributeError` because `app.py._start_engine` still accesses `self.config.connection` at runtime — that is fixed in Task 4. There is no `ImportError` because `app.py` does not import `TCPConnectionConfig` or `SerialConnectionConfig` at all. All other tests (store, link, node, ax25) should pass.

- [ ] **Step 8: Commit**

```bash
git add open_packet/config/config.py tests/test_config/test_config.py tests/test_ui/test_tui.py tests/test_ui/test_setup_screens.py
git commit -m "feat: remove connection section from AppConfig; connection config moves to DB"
```

---

## Task 3: TelnetLink

**Files:**
- Create: `open_packet/link/telnet.py`
- Modify: `tests/test_link/test_telnet.py`

- [ ] **Step 1: Write failing TelnetLink tests**

Create `tests/test_link/test_telnet.py`:

```python
import socket
from unittest.mock import MagicMock, patch, call
import pytest
from open_packet.link.base import ConnectionError
from open_packet.link.telnet import TelnetLink, _strip_iac


# --- Unit tests for IAC stripping ---

def test_strip_iac_removes_3byte_will_sequence():
    # IAC WILL SUPPRESS-GO-AHEAD + IAC WILL ECHO
    data = b'\xff\xfb\x03\xff\xfb\x01user:'
    assert _strip_iac(data) == b'user:'


def test_strip_iac_removes_2byte_ga():
    # IAC GA (Go Ahead) — 2-byte command
    data = b'hello\xff\xf9world'
    assert _strip_iac(data) == b'helloworld'


def test_strip_iac_leaves_normal_data_unchanged():
    assert _strip_iac(b'de N0WHR>') == b'de N0WHR>'


def test_strip_iac_empty():
    assert _strip_iac(b'') == b''


# --- TelnetLink tests using mock socket ---

def _make_mock_sock(responses):
    """
    responses: list of bytes chunks returned by successive recv() calls.
    """
    sock = MagicMock()
    sock.recv.side_effect = responses + [socket.timeout]
    return sock


@patch('open_packet.link.telnet.socket.socket')
def test_connect_sends_username_then_password(MockSocket):
    mock_sock = _make_mock_sock([
        b'\xff\xfb\x03\xff\xfb\x01user:',   # banner + user prompt
        b'password:',                          # password prompt
        b'de N0WHR>',                          # BPQ node prompt
    ])
    MockSocket.return_value = mock_sock

    link = TelnetLink(host='localhost', port=8023, username='K0JLB', password='secret')
    link.connect('W0BPQ', 0)  # callsign/ssid ignored

    send_calls = mock_sock.sendall.call_args_list
    assert send_calls[0] == call(b'K0JLB\r\n')
    assert send_calls[1] == call(b'secret\r\n')


@patch('open_packet.link.telnet.socket.socket')
def test_connect_strips_iac_from_banner(MockSocket):
    """IAC bytes in banner are stripped before prompt matching."""
    mock_sock = _make_mock_sock([
        b'\xff\xfb\x03\xff\xfb\x01user:',
        b'password:',
        b'de N0WHR>',
    ])
    MockSocket.return_value = mock_sock

    link = TelnetLink('localhost', 8023, 'K0JLB', 'pw')
    # Should not raise — IAC bytes stripped before checking for 'user:'
    link.connect('W0BPQ', 0)


@patch('open_packet.link.telnet.socket.socket')
def test_connect_raises_on_timeout(MockSocket):
    mock_sock = MagicMock()
    mock_sock.recv.side_effect = socket.timeout
    MockSocket.return_value = mock_sock

    link = TelnetLink('localhost', 8023, 'K0JLB', 'pw')
    with pytest.raises(ConnectionError, match="Timed out"):
        link.connect('W0BPQ', 0)


@patch('open_packet.link.telnet.socket.socket')
def test_receive_frame_returns_empty_on_timeout(MockSocket):
    mock_sock = MagicMock()
    mock_sock.recv.side_effect = socket.timeout
    MockSocket.return_value = mock_sock

    link = TelnetLink('localhost', 8023, 'K0JLB', 'pw')
    link._sock = mock_sock
    result = link.receive_frame(timeout=0.1)
    assert result == b''


@patch('open_packet.link.telnet.socket.socket')
def test_receive_frame_strips_iac(MockSocket):
    mock_sock = MagicMock()
    mock_sock.recv.return_value = b'\xff\xf9de N0WHR>'  # IAC GA + prompt
    MockSocket.return_value = mock_sock

    link = TelnetLink('localhost', 8023, 'K0JLB', 'pw')
    link._sock = mock_sock
    result = link.receive_frame(timeout=1.0)
    assert result == b'de N0WHR>'


@patch('open_packet.link.telnet.socket.socket')
def test_send_frame_calls_sendall(MockSocket):
    mock_sock = MagicMock()
    MockSocket.return_value = mock_sock

    link = TelnetLink('localhost', 8023, 'K0JLB', 'pw')
    link._sock = mock_sock
    link.send_frame(b'L\r')
    mock_sock.sendall.assert_called_once_with(b'L\r')


@patch('open_packet.link.telnet.socket.socket')
def test_disconnect_closes_socket(MockSocket):
    mock_sock = MagicMock()
    MockSocket.return_value = mock_sock

    link = TelnetLink('localhost', 8023, 'K0JLB', 'pw')
    link._sock = mock_sock
    link.disconnect()
    mock_sock.close.assert_called_once()
    assert link._sock is None


@patch('open_packet.link.telnet.socket.socket')
def test_connect_multi_chunk_login(MockSocket):
    """Login prompts may arrive split across multiple recv() calls."""
    mock_sock = _make_mock_sock([
        b'\xff\xfb\x03',    # IAC chunk
        b'\xff\xfb\x01',    # IAC chunk
        b'user:',           # prompt arrives separately
        b'pass',
        b'word:',           # password prompt split across chunks
        b'de N0WHR>',
    ])
    MockSocket.return_value = mock_sock

    link = TelnetLink('localhost', 8023, 'K0JLB', 'pw')
    link.connect('W0BPQ', 0)  # should not raise
```

- [ ] **Step 2: Run tests to see them fail**

```bash
uv run pytest tests/test_link/test_telnet.py -v 2>&1 | tail -15
```

Expected: FAIL — `ModuleNotFoundError: No module named 'open_packet.link.telnet'`

- [ ] **Step 3: Implement TelnetLink**

Create `open_packet/link/telnet.py`:

```python
# open_packet/link/telnet.py
from __future__ import annotations
import re
import socket
import time

from open_packet.link.base import ConnectionBase, ConnectionError

# IAC stripping regex:
# 2-byte: IAC + single-byte command (NOP=\xf1, GA=\xf9, SE=\xf0, etc., range \xf0-\xfa)
# 3-byte: IAC + WILL/WONT/DO/DONT (\xfb-\xfe) + option byte
_IAC_RE = re.compile(
    b'\xff[\xf0-\xfa]|'   # 2-byte IAC commands
    b'\xff[\xfb-\xfe].'   # 3-byte option negotiations
)

TIMEOUT = 10.0


def _strip_iac(data: bytes) -> bytes:
    return _IAC_RE.sub(b'', data)


class TelnetLink(ConnectionBase):
    def __init__(self, host: str, port: int, username: str, password: str):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sock: socket.socket | None = None

    def connect(self, callsign: str, ssid: int) -> None:
        """Connect to Telnet BPQ node and log in. callsign/ssid are ignored."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        try:
            sock.connect((self._host, self._port))
            self._sock = sock
            self._read_until(b'user:')
            sock.sendall(self._username.encode() + b'\r\n')
            self._read_until(b'password:')
            sock.sendall(self._password.encode() + b'\r\n')
            self._read_until_prompt()
        except socket.timeout:
            sock.close()
            self._sock = None
            raise ConnectionError('Timed out during Telnet login')
        except ConnectionError:
            sock.close()
            self._sock = None
            raise
        except Exception as e:
            sock.close()
            self._sock = None
            raise ConnectionError(f'Telnet connect failed: {e}') from e

    def _read_until(self, token: bytes, timeout: float = TIMEOUT) -> bytes:
        """Accumulate recv() chunks (IAC-stripped) until token is found."""
        buf = b''
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                chunk = self._sock.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                raise ConnectionError('Connection closed during login')
            buf += _strip_iac(chunk)
            if token in buf:
                return buf
        raise ConnectionError(f'Timed out waiting for {token!r}')

    def _read_until_prompt(self, timeout: float = TIMEOUT) -> bytes:
        """Accumulate recv() chunks until IAC-stripped buffer ends with '>'."""
        buf = b''
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                chunk = self._sock.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                raise ConnectionError('Connection closed waiting for prompt')
            buf += _strip_iac(chunk)
            if buf.rstrip().endswith(b'>'):
                return buf
        raise ConnectionError('Timed out waiting for BPQ node prompt')

    def disconnect(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def send_frame(self, data: bytes) -> None:
        if self._sock is None:
            raise ConnectionError('Not connected')
        self._sock.sendall(data)

    def receive_frame(self, timeout: float = 5.0) -> bytes:
        if self._sock is None:
            return b''
        self._sock.settimeout(timeout)
        try:
            data = self._sock.recv(4096)
            return _strip_iac(data) if data else b''
        except socket.timeout:
            return b''
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_link/test_telnet.py -v 2>&1 | tail -20
```

Expected: all 11 tests pass.

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest --tb=short 2>&1 | tail -10
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add open_packet/link/telnet.py tests/test_link/test_telnet.py
git commit -m "feat: add TelnetLink with IAC stripping and credential login"
```

---

## Task 4: Wire app.py engine to interface records

**Note:** This task updates `_start_engine` and `_on_settings_result` in `app.py`. The NodeSetupScreen push-site updates (`interfaces=`, `db=`) are intentionally deferred to Task 5 so that Tasks 4 and 5 can be committed atomically without breaking the first-run flow.

**Files:**
- Modify: `open_packet/ui/tui/app.py`
- Modify: `tests/test_ui/test_tui.py`

- [ ] **Step 1: Update test_tui.py DB setup to include Interface records**

In `tests/test_ui/test_tui.py`, add `Interface` to the models import and update every place that calls `db.insert_node(...)` to first insert an Interface and link it:

```python
# Change the import at the top of the file:
from open_packet.config.config import AppConfig, StoreConfig, UIConfig  # already done in Task 2
```

Add `Interface` to the models import where `Operator, Node` are imported. Then in each test that sets up the DB, replace the bare `insert_node` call with:

```python
    iface = db.insert_interface(Interface(
        label="Test", iface_type="kiss_tcp", host="localhost", port=8910
    ))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
                        is_default=True, interface_id=iface.id))
```

There are four such setup blocks in `test_tui.py` (in `test_app_mounts`, `test_console_toggle`, `test_update_counts_inbox_labels`, `test_update_counts_outbox_cleared`). Update all four. Also add `Interface` to the imports in `test_folder_selection_loads_inbox`.

The full updated import at the top of `tests/test_ui/test_tui.py`:

```python
# tests/test_ui/test_tui.py
import pytest
from open_packet.ui.tui.app import OpenPacketApp
from open_packet.config.config import AppConfig, StoreConfig, UIConfig
```

Each test's DB setup block (example for `test_app_mounts`):

```python
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node, Interface

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    iface = db.insert_interface(Interface(
        label="Test", iface_type="kiss_tcp", host="localhost", port=8910
    ))
    db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    db.close()
```

Apply the same pattern to `test_console_toggle`, `test_update_counts_inbox_labels`, and `test_update_counts_outbox_cleared`.

- [ ] **Step 2: Update app.py — replace _start_engine and fix imports**

In `open_packet/ui/tui/app.py`:

**2a.** Verify the config import in `app.py` is already minimal — it should be:

```python
from open_packet.config.config import AppConfig, load_config
```

`app.py` does not import `TCPConnectionConfig` or `SerialConnectionConfig`, so no change is needed on this line.

**2b.** Add `Interface` to the store models import:

```python
from open_packet.store.models import Operator, Node, Interface
```

**2c.** Add TelnetLink import at the top (with the other link imports):

```python
from open_packet.link.telnet import TelnetLink
```

**2d.** Replace the entire `_start_engine` method:

```python
    def _start_engine(self, db: Database, operator: Operator, node_record: Node) -> None:
        store = Store(db)
        self._store = store
        self._active_operator = operator

        if node_record.interface_id is None:
            return  # no interface configured; engine stays dormant

        iface = db.get_interface(node_record.interface_id)
        if iface is None:
            return

        match iface.iface_type:
            case "telnet":
                connection = TelnetLink(
                    host=iface.host, port=iface.port,
                    username=iface.username, password=iface.password,
                )
            case "kiss_tcp":
                transport = TCPTransport(host=iface.host, port=iface.port)
                connection = AX25Connection(
                    kiss=KISSLink(transport=transport),
                    my_callsign=operator.callsign,
                    my_ssid=operator.ssid,
                )
            case "kiss_serial":
                transport = SerialTransport(device=iface.device, baud=iface.baud)
                connection = AX25Connection(
                    kiss=KISSLink(transport=transport),
                    my_callsign=operator.callsign,
                    my_ssid=operator.ssid,
                )
            case _:
                raise ValueError(f"Unknown interface type: {iface.iface_type!r}")

        node = BPQNode(
            connection=connection,
            node_callsign=node_record.callsign,
            node_ssid=node_record.ssid,
            my_callsign=operator.callsign,
            my_ssid=operator.ssid,
        )

        export_path = (
            os.path.expanduser(self.config.store.export_path)
            if self.config.store.export_path else None
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
        )
        self._engine.start()
```

**2e.** Add the `"interfaces"` branch to `_on_settings_result`. The `"node"` else-branch (when `self._db` is falsy) will be updated to pass `interfaces=` and `db=` in Task 5. For now only add the interfaces branch:

```python
        elif result == "interfaces":
            if self._db:
                from open_packet.ui.tui.screens.manage_interfaces import InterfaceManageScreen
                self.push_screen(InterfaceManageScreen(self._db),
                                 callback=self._on_manage_result)
```

Add this `elif` block after the existing `elif result == "node":` block in `_on_settings_result`.

- [ ] **Step 3: Run tests to verify**

```bash
uv run pytest tests/test_ui/test_tui.py tests/test_ui/test_setup_screens.py --tb=short 2>&1 | tail -20
```

Expected: tests that were previously passing still pass. Some setup_screens tests involving NodeSetupScreen may fail because the screen's API has changed — those will be fixed in Task 5.

- [ ] **Step 4: Run full suite**

```bash
uv run pytest --tb=short 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
git add open_packet/ui/tui/app.py tests/test_ui/test_tui.py
git commit -m "feat: wire _start_engine to Interface record via match statement; add interfaces Settings branch"
```

---

## Task 5: Redesign NodeSetupScreen with inline interface creation

**Note:** This task also updates the NodeSetupScreen push sites in `app.py` (committed atomically with the new screen so the signature change and all callers land together).

**Files:**
- Modify: `open_packet/ui/tui/screens/setup_node.py`
- Modify: `open_packet/ui/tui/app.py` (push-site updates)
- Modify: `tests/test_ui/test_setup_screens.py`

- [ ] **Step 1: Write the new NodeSetupScreen tests**

Replace the existing `test_node_setup_*` tests in `tests/test_ui/test_setup_screens.py` (keep operator tests and the integration tests). Add the following new tests. First, add these imports at the top:

```python
from open_packet.store.database import Database
from open_packet.store.models import Interface
```

Add a `node_db` fixture and the new tests:

```python
@pytest.fixture
def node_db(tmp_path):
    db = Database(str(tmp_path / "node_test.db"))
    db.initialize()
    yield db
    db.close()


@pytest.mark.asyncio
async def test_node_setup_telnet_creates_interface(node_db):
    """Saving a Telnet node creates an Interface record and links the Node to it."""
    app = _ScreenTestApp(lambda: NodeSetupScreen(interfaces=[], db=node_db))
    async with app.run_test() as pilot:
        await pilot.click("#label_field")
        await pilot.press(*"Home BBS")
        await pilot.click("#callsign_field")
        await pilot.press(*"w0bpq")
        await pilot.click("#ssid_field")
        await pilot.press("1")
        # conn_type defaults to "telnet", iface_selector defaults to "New"
        await pilot.click("#telnet_host")
        await pilot.press(*"192.168.1.209")
        await pilot.click("#telnet_port")
        await pilot.press(*"8023")
        await pilot.click("#telnet_user")
        await pilot.press(*"K0JLB")
        await pilot.click("#telnet_pass")
        await pilot.press(*"password")
        await pilot.click("#save_btn")
        await pilot.pause()

    result = app.dismiss_result
    assert result is not _SENTINEL
    assert result is not None
    assert result.label == "Home BBS"
    assert result.callsign == "W0BPQ"
    assert result.ssid == 1
    assert result.interface_id is not None

    iface = node_db.get_interface(result.interface_id)
    assert iface.iface_type == "telnet"
    assert iface.host == "192.168.1.209"
    assert iface.port == 8023
    assert iface.username == "K0JLB"
    assert iface.password == "password"


@pytest.mark.asyncio
async def test_node_setup_reuses_existing_interface(node_db):
    """When an existing interface is selected, no new Interface record is created."""
    existing = node_db.insert_interface(Interface(
        label="Home TNC", iface_type="telnet",
        host="10.0.0.1", port=8023, username="K0JLB", password="pw"
    ))
    before_count = len(node_db.list_interfaces())

    app = _ScreenTestApp(lambda: NodeSetupScreen(
        interfaces=node_db.list_interfaces(), db=node_db
    ))
    async with app.run_test() as pilot:
        await pilot.click("#label_field")
        await pilot.press(*"Remote BBS")
        await pilot.click("#callsign_field")
        await pilot.press(*"W0BPQ")
        await pilot.click("#ssid_field")
        await pilot.press("0")
        # interface selector should have the existing interface; select it
        iface_sel = pilot.app.query_one("#iface_selector")
        iface_sel.value = existing.id
        await pilot.pause()
        await pilot.click("#save_btn")
        await pilot.pause()

    result = app.dismiss_result
    assert result is not _SENTINEL
    assert result is not None
    assert result.interface_id == existing.id
    assert len(node_db.list_interfaces()) == before_count  # no new interface created


@pytest.mark.asyncio
async def test_node_setup_blank_host_does_not_dismiss(node_db):
    """Telnet with blank host should not dismiss."""
    app = _ScreenTestApp(lambda: NodeSetupScreen(interfaces=[], db=node_db))
    async with app.run_test() as pilot:
        await pilot.click("#label_field")
        await pilot.press(*"BBS")
        await pilot.click("#callsign_field")
        await pilot.press(*"W0BPQ")
        await pilot.click("#ssid_field")
        await pilot.press("0")
        # Leave host blank, fill rest
        await pilot.click("#telnet_port")
        await pilot.press(*"8023")
        await pilot.click("#telnet_user")
        await pilot.press(*"K0JLB")
        await pilot.click("#telnet_pass")
        await pilot.press(*"pw")
        await pilot.click("#save_btn")
        await pilot.pause()
    assert app.dismiss_result is _SENTINEL


@pytest.mark.asyncio
async def test_node_setup_cancel(node_db):
    app = _ScreenTestApp(lambda: NodeSetupScreen(interfaces=[], db=node_db))
    async with app.run_test() as pilot:
        await pilot.click("#cancel_btn")
        await pilot.pause()
    assert app.dismiss_result is None
```

Also delete the four old `test_node_setup_*` tests that test the old screen API (`test_node_setup_valid_input`, `test_node_setup_blank_callsign_does_not_dismiss`, `test_node_setup_invalid_ssid_does_not_dismiss`, `test_node_setup_cancel`).

- [ ] **Step 2: Run new node setup tests to see them fail**

```bash
uv run pytest tests/test_ui/test_setup_screens.py::test_node_setup_telnet_creates_interface -v 2>&1 | tail -15
```

Expected: FAIL — `NodeSetupScreen.__init__` doesn't accept `db=` parameter yet.

- [ ] **Step 3: Implement the new NodeSetupScreen**

Replace the entire contents of `open_packet/ui/tui/screens/setup_node.py`:

```python
# open_packet/ui/tui/screens/setup_node.py
from __future__ import annotations
from typing import Optional
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Switch, Select
from textual.containers import Vertical, Horizontal
from open_packet.store.database import Database
from open_packet.store.models import Node, Interface
from open_packet.ui.tui.screens import CALLSIGN_RE

_NEW_IFACE = "__new__"
_CONN_TYPES = [("Telnet", "telnet"), ("KISS TCP", "kiss_tcp"), ("KISS Serial", "kiss_serial")]


class NodeSetupScreen(ModalScreen):
    DEFAULT_CSS = """
    NodeSetupScreen {
        align: center middle;
    }
    NodeSetupScreen > Vertical {
        width: 60;
        height: auto;
        max-height: 90%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    NodeSetupScreen .error {
        color: $error;
        height: 1;
    }
    NodeSetupScreen .section {
        margin-top: 1;
    }
    """

    def __init__(
        self,
        node: Optional[Node] = None,
        interfaces: Optional[list[Interface]] = None,
        db: Optional[Database] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._node = node
        self._interfaces = interfaces or []
        self._db = db

    def compose(self) -> ComposeResult:
        n = self._node
        title = "Edit Node" if n else "Node Setup"
        default_type = "telnet"
        if n and n.interface_id:
            existing = next((i for i in self._interfaces if i.id == n.interface_id), None)
            if existing:
                default_type = existing.iface_type

        with Vertical():
            yield Label(title)
            yield Label("Label:")
            yield Input(placeholder="e.g. Home BBS", id="label_field",
                        value=n.label if n else "")
            yield Label("", id="label_error", classes="error")
            yield Label("Callsign:")
            yield Input(placeholder="e.g. W0BPQ", id="callsign_field",
                        value=n.callsign if n else "")
            yield Label("", id="callsign_error", classes="error")
            yield Label("SSID (0-15):")
            yield Input(placeholder="0", id="ssid_field",
                        value=str(n.ssid) if n else "")
            yield Label("", id="ssid_error", classes="error")
            yield Label("Set as default:")
            yield Switch(value=n.is_default if n else True, id="default_switch")

            yield Label("Connection Type:", classes="section")
            yield Select(_CONN_TYPES, value=default_type, id="conn_type_select")
            yield Label("Interface:")
            yield Select([("— New interface —", _NEW_IFACE)], value=_NEW_IFACE,
                         id="iface_selector")

            with Vertical(id="telnet_fields"):
                yield Label("Host:")
                yield Input(placeholder="e.g. 192.168.1.209", id="telnet_host")
                yield Label("Port:")
                yield Input(placeholder="8023", id="telnet_port")
                yield Label("Username:")
                yield Input(placeholder="e.g. K0JLB", id="telnet_user")
                yield Label("Password:")
                yield Input(placeholder="", id="telnet_pass", password=True)
                yield Label("Interface Label (optional):")
                yield Input(placeholder="auto-generated if blank", id="iface_label_telnet")

            with Vertical(id="kiss_tcp_fields"):
                yield Label("Host:")
                yield Input(placeholder="e.g. 192.168.1.1", id="kiss_tcp_host")
                yield Label("Port:")
                yield Input(placeholder="8910", id="kiss_tcp_port")
                yield Label("Interface Label (optional):")
                yield Input(placeholder="auto-generated if blank", id="iface_label_kiss_tcp")

            with Vertical(id="kiss_serial_fields"):
                yield Label("Device:")
                yield Input(placeholder="/dev/ttyUSB0", id="kiss_serial_device")
                yield Label("Baud:")
                yield Input(placeholder="9600", id="kiss_serial_baud")
                yield Label("Interface Label (optional):")
                yield Input(placeholder="auto-generated if blank", id="iface_label_kiss_serial")

            yield Label("", id="conn_error", classes="error")

            with Horizontal():
                yield Button("Save", variant="primary", id="save_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_mount(self) -> None:
        self._refresh_iface_selector()
        self._refresh_field_visibility()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "conn_type_select":
            self._refresh_iface_selector()
            self._refresh_field_visibility()
        elif event.select.id == "iface_selector":
            self._refresh_field_visibility()

    def _conn_type(self) -> str:
        v = self.query_one("#conn_type_select", Select).value
        return str(v) if v and v != Select.BLANK else "telnet"

    def _using_new_iface(self) -> bool:
        v = self.query_one("#iface_selector", Select).value
        return v == _NEW_IFACE or v == Select.BLANK

    def _refresh_iface_selector(self) -> None:
        conn_type = self._conn_type()
        matching = [i for i in self._interfaces if i.iface_type == conn_type]
        options = [("— New interface —", _NEW_IFACE)]
        options += [(i.label or f"{i.host}:{i.port}", i.id) for i in matching]
        sel = self.query_one("#iface_selector", Select)
        sel.set_options(options)
        # Pre-select the node's existing interface if editing
        if self._node and self._node.interface_id:
            match = next((i for i in matching if i.id == self._node.interface_id), None)
            if match:
                sel.value = match.id
                return
        sel.value = _NEW_IFACE

    def _refresh_field_visibility(self) -> None:
        conn_type = self._conn_type()
        using_new = self._using_new_iface()
        self.query_one("#telnet_fields").display = (conn_type == "telnet" and using_new)
        self.query_one("#kiss_tcp_fields").display = (conn_type == "kiss_tcp" and using_new)
        self.query_one("#kiss_serial_fields").display = (conn_type == "kiss_serial" and using_new)

    def _validate(self) -> bool:
        valid = True
        label = self.query_one("#label_field", Input).value.strip()
        callsign = self.query_one("#callsign_field", Input).value.strip()
        ssid_str = self.query_one("#ssid_field", Input).value.strip()

        if not label:
            self.query_one("#label_error", Label).update("Label is required")
            valid = False
        else:
            self.query_one("#label_error", Label).update("")

        if not CALLSIGN_RE.match(callsign):
            self.query_one("#callsign_error", Label).update(
                "Callsign must be 1-6 alphanumeric characters"
            )
            valid = False
        else:
            self.query_one("#callsign_error", Label).update("")

        try:
            ssid = int(ssid_str)
            if not 0 <= ssid <= 15:
                raise ValueError
            self.query_one("#ssid_error", Label).update("")
        except ValueError:
            self.query_one("#ssid_error", Label).update("SSID must be an integer 0-15")
            valid = False

        if self._using_new_iface():
            valid = self._validate_new_iface() and valid

        return valid

    def _validate_new_iface(self) -> bool:
        conn_type = self._conn_type()
        err = self.query_one("#conn_error", Label)

        if conn_type == "telnet":
            host = self.query_one("#telnet_host", Input).value.strip()
            port_str = self.query_one("#telnet_port", Input).value.strip()
            user = self.query_one("#telnet_user", Input).value.strip()
            pw = self.query_one("#telnet_pass", Input).value.strip()
            if not host or not user or not pw:
                err.update("Host, username, and password are required")
                return False
            try:
                if int(port_str) <= 0:
                    raise ValueError
            except ValueError:
                err.update("Port must be a positive integer")
                return False

        elif conn_type == "kiss_tcp":
            host = self.query_one("#kiss_tcp_host", Input).value.strip()
            port_str = self.query_one("#kiss_tcp_port", Input).value.strip()
            if not host:
                err.update("Host is required")
                return False
            try:
                if int(port_str) <= 0:
                    raise ValueError
            except ValueError:
                err.update("Port must be a positive integer")
                return False

        elif conn_type == "kiss_serial":
            device = self.query_one("#kiss_serial_device", Input).value.strip()
            baud_str = self.query_one("#kiss_serial_baud", Input).value.strip()
            if not device:
                err.update("Device is required")
                return False
            try:
                if int(baud_str) <= 0:
                    raise ValueError
            except ValueError:
                err.update("Baud must be a positive integer")
                return False

        err.update("")
        return True

    def _build_and_save_interface(self) -> int:
        """Insert a new Interface record and return its id."""
        assert self._db is not None
        conn_type = self._conn_type()
        callsign = self.query_one("#callsign_field", Input).value.strip().upper()

        if conn_type == "telnet":
            host = self.query_one("#telnet_host", Input).value.strip()
            port = int(self.query_one("#telnet_port", Input).value.strip())
            username = self.query_one("#telnet_user", Input).value.strip()
            password = self.query_one("#telnet_pass", Input).value.strip()
            label = (self.query_one("#iface_label_telnet", Input).value.strip()
                     or f"{callsign} via {host}")
            iface = Interface(label=label, iface_type="telnet",
                              host=host, port=port, username=username, password=password)

        elif conn_type == "kiss_tcp":
            host = self.query_one("#kiss_tcp_host", Input).value.strip()
            port = int(self.query_one("#kiss_tcp_port", Input).value.strip())
            label = (self.query_one("#iface_label_kiss_tcp", Input).value.strip()
                     or f"{callsign} via {host}")
            iface = Interface(label=label, iface_type="kiss_tcp", host=host, port=port)

        else:  # kiss_serial
            device = self.query_one("#kiss_serial_device", Input).value.strip()
            baud = int(self.query_one("#kiss_serial_baud", Input).value.strip())
            label = (self.query_one("#iface_label_kiss_serial", Input).value.strip()
                     or f"{callsign} via {device}")
            iface = Interface(label=label, iface_type="kiss_serial", device=device, baud=baud)

        saved = self._db.insert_interface(iface)
        return saved.id

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.dismiss(None)
        elif event.button.id == "save_btn":
            if self._validate():
                label = self.query_one("#label_field", Input).value.strip()
                callsign = self.query_one("#callsign_field", Input).value.strip().upper()
                ssid = int(self.query_one("#ssid_field", Input).value.strip())
                is_default = self.query_one("#default_switch", Switch).value

                if self._using_new_iface():
                    interface_id = self._build_and_save_interface()
                else:
                    interface_id = int(self.query_one("#iface_selector", Select).value)

                self.dismiss(Node(
                    label=label,
                    callsign=callsign,
                    ssid=ssid,
                    node_type="bpq",
                    is_default=is_default,
                    interface_id=interface_id,
                    id=self._node.id if self._node else None,
                ))

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
```

- [ ] **Step 4: Run new NodeSetupScreen tests**

```bash
uv run pytest tests/test_ui/test_setup_screens.py -k "node_setup" -v 2>&1 | tail -20
```

Expected: all new node setup tests pass.

- [ ] **Step 5: Update all NodeSetupScreen push sites in app.py to pass `interfaces=` and `db=`**

In `open_packet/ui/tui/app.py`:

In `_init_engine`, change:
```python
            self.call_after_refresh(
                lambda: self.push_screen(NodeSetupScreen(), callback=self._on_node_setup_result)
            )
```
to:
```python
            self.call_after_refresh(
                lambda: self.push_screen(
                    NodeSetupScreen(interfaces=self._db.list_interfaces(), db=self._db),
                    callback=self._on_node_setup_result,
                )
            )
```

In `_on_operator_setup_result`, change:
```python
            self.push_screen(NodeSetupScreen(), callback=self._on_node_setup_result)
```
to:
```python
            self.push_screen(
                NodeSetupScreen(interfaces=self._db.list_interfaces(), db=self._db),
                callback=self._on_node_setup_result,
            )
```

In `_on_settings_result`, update the `"node"` else-branch (when `self._db` is falsy):
```python
            else:
                self.push_screen(
                    NodeSetupScreen(interfaces=[], db=None),
                    callback=self._on_node_setup_result,
                )
```

- [ ] **Step 6: Update test_setup_screens.py integration tests that fill in the node form**

The tests `test_partial_first_run_cancel_engine_stays_none` and `test_engine_reinit_after_full_setup` interact with `NodeSetupScreen` through a full app. Update both to fill in the new connection fields. In `test_engine_reinit_after_full_setup`, add after filling the ssid field:

```python
        # Telnet fields (default connection type)
        await pilot.click("#telnet_host")
        await pilot.press(*"192.168.1.209")
        await pilot.click("#telnet_port")
        await pilot.press(*"8023")
        await pilot.click("#telnet_user")
        await pilot.press(*"K0JLB")
        await pilot.click("#telnet_pass")
        await pilot.press(*"password")
```

In `test_partial_first_run_cancel_engine_stays_none`, no node form is filled (the test cancels the node screen), so no change is needed there.

- [ ] **Step 7: Run full test suite**

```bash
uv run pytest --tb=short 2>&1 | tail -15
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add open_packet/ui/tui/screens/setup_node.py open_packet/ui/tui/app.py tests/test_ui/test_setup_screens.py
git commit -m "feat: redesign NodeSetupScreen with inline interface creation and connection type selector"
```

---

## Task 6: InterfaceSetupScreen

**Files:**
- Create: `open_packet/ui/tui/screens/setup_interface.py`
- Modify: `tests/test_ui/test_setup_screens.py`

- [ ] **Step 1: Write failing InterfaceSetupScreen tests**

Add to `tests/test_ui/test_setup_screens.py`:

```python
from open_packet.ui.tui.screens.setup_interface import InterfaceSetupScreen


@pytest.mark.asyncio
async def test_interface_setup_telnet_valid():
    app = _ScreenTestApp(InterfaceSetupScreen)
    async with app.run_test() as pilot:
        # Default type is telnet
        await pilot.click("#iface_label_field")
        await pilot.press(*"Home BBS")
        await pilot.click("#host_field")
        await pilot.press(*"192.168.1.209")
        await pilot.click("#port_field")
        await pilot.press(*"8023")
        await pilot.click("#username_field")
        await pilot.press(*"K0JLB")
        await pilot.click("#password_field")
        await pilot.press(*"secret")
        await pilot.click("#save_btn")
        await pilot.pause()
    result = app.dismiss_result
    assert result is not _SENTINEL
    assert result is not None
    assert result.label == "Home BBS"
    assert result.iface_type == "telnet"
    assert result.host == "192.168.1.209"
    assert result.port == 8023
    assert result.username == "K0JLB"
    assert result.password == "secret"


@pytest.mark.asyncio
async def test_interface_setup_blank_host_does_not_dismiss():
    app = _ScreenTestApp(InterfaceSetupScreen)
    async with app.run_test() as pilot:
        await pilot.click("#iface_label_field")
        await pilot.press(*"Bad")
        # leave host blank
        await pilot.click("#port_field")
        await pilot.press(*"8023")
        await pilot.click("#username_field")
        await pilot.press(*"user")
        await pilot.click("#password_field")
        await pilot.press(*"pw")
        await pilot.click("#save_btn")
        await pilot.pause()
    assert app.dismiss_result is _SENTINEL


@pytest.mark.asyncio
async def test_interface_setup_cancel():
    app = _ScreenTestApp(InterfaceSetupScreen)
    async with app.run_test() as pilot:
        await pilot.click("#cancel_btn")
        await pilot.pause()
    assert app.dismiss_result is None
```

- [ ] **Step 2: Run to see them fail**

```bash
uv run pytest tests/test_ui/test_setup_screens.py -k "interface_setup" -v 2>&1 | tail -10
```

Expected: FAIL — `ModuleNotFoundError: No module named 'open_packet.ui.tui.screens.setup_interface'`

- [ ] **Step 3: Implement InterfaceSetupScreen**

Create `open_packet/ui/tui/screens/setup_interface.py`:

```python
# open_packet/ui/tui/screens/setup_interface.py
from __future__ import annotations
from typing import Optional
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select
from textual.containers import Vertical, Horizontal
from open_packet.store.models import Interface

_CONN_TYPES = [("Telnet", "telnet"), ("KISS TCP", "kiss_tcp"), ("KISS Serial", "kiss_serial")]


class InterfaceSetupScreen(ModalScreen):
    DEFAULT_CSS = """
    InterfaceSetupScreen {
        align: center middle;
    }
    InterfaceSetupScreen > Vertical {
        width: 55;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    InterfaceSetupScreen .error {
        color: $error;
        height: 1;
    }
    """

    def __init__(self, interface: Optional[Interface] = None, **kwargs):
        super().__init__(**kwargs)
        self._interface = interface

    def compose(self) -> ComposeResult:
        iface = self._interface
        title = "Edit Interface" if iface else "New Interface"
        default_type = iface.iface_type if iface else "telnet"

        with Vertical():
            yield Label(title)
            yield Label("Label:")
            yield Input(placeholder="e.g. Home TNC", id="iface_label_field",
                        value=iface.label if iface else "")
            yield Label("", id="label_error", classes="error")
            yield Label("Type:")
            yield Select(_CONN_TYPES, value=default_type, id="iface_type_select")

            with Vertical(id="telnet_fields"):
                yield Label("Host:")
                yield Input(placeholder="e.g. 192.168.1.209", id="host_field",
                            value=iface.host or "" if iface else "")
                yield Label("Port:")
                yield Input(placeholder="8023", id="port_field",
                            value=str(iface.port) if iface and iface.port else "")
                yield Label("Username:")
                yield Input(placeholder="e.g. K0JLB", id="username_field",
                            value=iface.username or "" if iface else "")
                yield Label("Password:")
                yield Input(placeholder="", id="password_field", password=True,
                            value=iface.password or "" if iface else "")

            with Vertical(id="kiss_tcp_fields"):
                yield Label("Host:")
                yield Input(placeholder="e.g. 192.168.1.1", id="kiss_tcp_host_field",
                            value=iface.host or "" if iface else "")
                yield Label("Port:")
                yield Input(placeholder="8910", id="kiss_tcp_port_field",
                            value=str(iface.port) if iface and iface.port else "")

            with Vertical(id="kiss_serial_fields"):
                yield Label("Device:")
                yield Input(placeholder="/dev/ttyUSB0", id="device_field",
                            value=iface.device or "" if iface else "")
                yield Label("Baud:")
                yield Input(placeholder="9600", id="baud_field",
                            value=str(iface.baud) if iface and iface.baud else "")

            yield Label("", id="conn_error", classes="error")

            with Horizontal():
                yield Button("Save", variant="primary", id="save_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_mount(self) -> None:
        self._refresh_visibility()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "iface_type_select":
            self._refresh_visibility()

    def _iface_type(self) -> str:
        v = self.query_one("#iface_type_select", Select).value
        return str(v) if v and v != Select.BLANK else "telnet"

    def _refresh_visibility(self) -> None:
        t = self._iface_type()
        self.query_one("#telnet_fields").display = (t == "telnet")
        self.query_one("#kiss_tcp_fields").display = (t == "kiss_tcp")
        self.query_one("#kiss_serial_fields").display = (t == "kiss_serial")

    def _validate(self) -> bool:
        label = self.query_one("#iface_label_field", Input).value.strip()
        if not label:
            self.query_one("#label_error", Label).update("Label is required")
            return False
        self.query_one("#label_error", Label).update("")

        t = self._iface_type()
        err = self.query_one("#conn_error", Label)

        if t == "telnet":
            host = self.query_one("#host_field", Input).value.strip()
            port_str = self.query_one("#port_field", Input).value.strip()
            user = self.query_one("#username_field", Input).value.strip()
            pw = self.query_one("#password_field", Input).value.strip()
            if not host or not user or not pw:
                err.update("Host, username, and password are required")
                return False
            try:
                if int(port_str) <= 0:
                    raise ValueError
            except ValueError:
                err.update("Port must be a positive integer")
                return False

        elif t == "kiss_tcp":
            host = self.query_one("#kiss_tcp_host_field", Input).value.strip()
            port_str = self.query_one("#kiss_tcp_port_field", Input).value.strip()
            if not host:
                err.update("Host is required")
                return False
            try:
                if int(port_str) <= 0:
                    raise ValueError
            except ValueError:
                err.update("Port must be a positive integer")
                return False

        elif t == "kiss_serial":
            device = self.query_one("#device_field", Input).value.strip()
            baud_str = self.query_one("#baud_field", Input).value.strip()
            if not device:
                err.update("Device is required")
                return False
            try:
                if int(baud_str) <= 0:
                    raise ValueError
            except ValueError:
                err.update("Baud must be a positive integer")
                return False

        err.update("")
        return True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.dismiss(None)
        elif event.button.id == "save_btn":
            if not self._validate():
                return
            label = self.query_one("#iface_label_field", Input).value.strip()
            t = self._iface_type()

            if t == "telnet":
                host = self.query_one("#host_field", Input).value.strip()
                port = int(self.query_one("#port_field", Input).value.strip())
                username = self.query_one("#username_field", Input).value.strip()
                password = self.query_one("#password_field", Input).value.strip()
                self.dismiss(Interface(
                    id=self._interface.id if self._interface else None,
                    label=label, iface_type=t,
                    host=host, port=port, username=username, password=password,
                ))
            elif t == "kiss_tcp":
                host = self.query_one("#kiss_tcp_host_field", Input).value.strip()
                port = int(self.query_one("#kiss_tcp_port_field", Input).value.strip())
                self.dismiss(Interface(
                    id=self._interface.id if self._interface else None,
                    label=label, iface_type=t, host=host, port=port,
                ))
            elif t == "kiss_serial":
                device = self.query_one("#device_field", Input).value.strip()
                baud = int(self.query_one("#baud_field", Input).value.strip())
                self.dismiss(Interface(
                    id=self._interface.id if self._interface else None,
                    label=label, iface_type=t, device=device, baud=baud,
                ))

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_ui/test_setup_screens.py -k "interface_setup" -v 2>&1 | tail -15
```

Expected: all 3 interface setup tests pass.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest --tb=short 2>&1 | tail -10
```

- [ ] **Step 6: Commit**

```bash
git add open_packet/ui/tui/screens/setup_interface.py tests/test_ui/test_setup_screens.py
git commit -m "feat: add InterfaceSetupScreen modal for creating and editing interfaces"
```

---

## Task 7: InterfaceManageScreen, SettingsScreen, and NodeManageScreen wiring

**Files:**
- Create: `open_packet/ui/tui/screens/manage_interfaces.py`
- Modify: `open_packet/ui/tui/screens/settings.py`
- Modify: `open_packet/ui/tui/screens/manage_nodes.py`
- Modify: `tests/test_ui/test_setup_screens.py`
- Modify: `tests/test_ui/test_manage_screens.py` (if it exists; check first)

- [ ] **Step 1: Write failing tests for the Settings Interfaces button**

`SettingsScreen` is already imported at the top of `test_setup_screens.py` — no import change needed.

Add to `tests/test_ui/test_setup_screens.py`:

```python
@pytest.mark.asyncio
async def test_settings_interfaces_button():
    app = _ScreenTestApp(SettingsScreen)
    async with app.run_test() as pilot:
        await pilot.click("#interfaces_btn")
        await pilot.pause()
    assert app.dismiss_result == "interfaces"
```

Run:

```bash
uv run pytest tests/test_ui/test_setup_screens.py::test_settings_interfaces_button -v 2>&1 | tail -10
```

Expected: FAIL — no `#interfaces_btn` in `SettingsScreen`.

- [ ] **Step 2: Add Interfaces button to SettingsScreen**

In `open_packet/ui/tui/screens/settings.py`, add the "Interfaces" button before "Close":

```python
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Settings")
            yield Button("Operator", id="operator_btn")
            yield Button("Node", id="node_btn")
            yield Button("Interfaces", id="interfaces_btn")
            yield Button("Close", id="close_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "operator_btn":
            self.dismiss("operator")
        elif event.button.id == "node_btn":
            self.dismiss("node")
        elif event.button.id == "interfaces_btn":
            self.dismiss("interfaces")
        else:
            self.dismiss(None)
```

- [ ] **Step 3: Run settings test**

```bash
uv run pytest tests/test_ui/test_setup_screens.py::test_settings_interfaces_button -v 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 4: Write failing InterfaceManageScreen test**

Add to `tests/test_ui/test_setup_screens.py`:

```python
from open_packet.ui.tui.screens.manage_interfaces import InterfaceManageScreen


class _ManageTestApp(App):
    """Wrapper app that opens InterfaceManageScreen with a real DB."""
    def __init__(self, db, **kwargs):
        super().__init__(**kwargs)
        self._db = db
        self.dismiss_result = _SENTINEL

    def on_mount(self):
        def capture(result):
            self.dismiss_result = result
        self.push_screen(InterfaceManageScreen(self._db), callback=capture)


@pytest.mark.asyncio
async def test_interface_manage_shows_existing(node_db):
    node_db.insert_interface(Interface(label="My TNC", iface_type="kiss_tcp",
                                       host="localhost", port=8910))
    app = _ManageTestApp(node_db)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Label text appears somewhere in the screen
        assert app.query("Label")  # screen mounted
        await pilot.click("#close_btn")
        await pilot.pause()
    assert app.dismiss_result is False


@pytest.mark.asyncio
async def test_interface_manage_close_returns_false(node_db):
    app = _ManageTestApp(node_db)
    async with app.run_test() as pilot:
        await pilot.click("#close_btn")
        await pilot.pause()
    assert app.dismiss_result is False
```

Run:

```bash
uv run pytest tests/test_ui/test_setup_screens.py -k "interface_manage" -v 2>&1 | tail -10
```

Expected: FAIL — `ModuleNotFoundError: No module named ...manage_interfaces`

- [ ] **Step 5: Implement InterfaceManageScreen**

Create `open_packet/ui/tui/screens/manage_interfaces.py`:

```python
# open_packet/ui/tui/screens/manage_interfaces.py
from __future__ import annotations
from typing import Optional
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from textual.containers import Vertical, Horizontal, VerticalScroll
from open_packet.store.database import Database
from open_packet.store.models import Interface


class InterfaceManageScreen(ModalScreen):
    DEFAULT_CSS = """
    InterfaceManageScreen {
        align: center middle;
    }
    InterfaceManageScreen > Vertical {
        width: 70;
        height: auto;
        max-height: 80%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    InterfaceManageScreen VerticalScroll {
        height: auto;
        max-height: 20;
    }
    InterfaceManageScreen .row {
        height: 3;
    }
    InterfaceManageScreen .row-label {
        width: 1fr;
        content-align: left middle;
    }
    InterfaceManageScreen .row Button {
        width: auto;
        min-width: 10;
        margin: 0 0 0 1;
    }
    InterfaceManageScreen .footer-row {
        height: 3;
        margin-top: 1;
        align: right middle;
    }
    InterfaceManageScreen .footer-row Button {
        width: auto;
        min-width: 10;
        margin: 0 0 0 1;
    }
    """

    def __init__(self, db: Database, **kwargs):
        super().__init__(**kwargs)
        self._db = db
        self._needs_restart = False

    def compose(self) -> ComposeResult:
        interfaces = self._db.list_interfaces()
        with Vertical():
            yield Label("Interfaces")
            with VerticalScroll(id="iface_list"):
                if interfaces:
                    for iface in interfaces:
                        summary = f"{iface.label}  [{iface.iface_type}]"
                        if iface.host:
                            summary += f"  {iface.host}:{iface.port}"
                        elif iface.device:
                            summary += f"  {iface.device}"
                        with Horizontal(classes="row", id=f"row_{iface.id}"):
                            yield Label(summary, classes="row-label")
                            yield Button("Edit", id=f"edit_{iface.id}")
                            yield Button("Delete", id=f"delete_{iface.id}",
                                         variant="error")
                else:
                    yield Label("No interfaces configured.")
            with Horizontal(classes="footer-row"):
                yield Button("Add New", id="add_btn", variant="primary")
                yield Button("Close", id="close_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "add_btn":
            from open_packet.ui.tui.screens.setup_interface import InterfaceSetupScreen
            self.app.push_screen(InterfaceSetupScreen(), callback=self._on_add)
        elif btn_id == "close_btn":
            self.dismiss(self._needs_restart)
        elif btn_id.startswith("edit_"):
            iface_id = int(btn_id.split("_")[-1])
            self._edit(iface_id)
        elif btn_id.startswith("delete_"):
            iface_id = int(btn_id.split("_")[-1])
            self._db.delete_interface(iface_id)
            self._needs_restart = True
            self.call_later(self.recompose)

    def _edit(self, iface_id: int) -> None:
        iface = self._db.get_interface(iface_id)
        if iface:
            from open_packet.ui.tui.screens.setup_interface import InterfaceSetupScreen
            self.app.push_screen(
                InterfaceSetupScreen(iface),
                callback=lambda result: self._on_edit(result),
            )

    def _on_add(self, result: Optional[Interface]) -> None:
        if result is None:
            return
        self._db.insert_interface(result)
        self._needs_restart = True
        self.recompose()

    def _on_edit(self, result: Optional[Interface]) -> None:
        if result is None:
            return
        self._db.update_interface(result)
        self._needs_restart = True
        self.recompose()

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(self._needs_restart)
```

- [ ] **Step 6: Run interface manage tests**

```bash
uv run pytest tests/test_ui/test_setup_screens.py -k "interface_manage or interface_setup or settings_interfaces" -v 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 7: Update NodeManageScreen push sites**

In `open_packet/ui/tui/screens/manage_nodes.py`, update `on_button_pressed` and `_edit` to pass `interfaces=` and `db=` to `NodeSetupScreen`:

```python
    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "add_btn":
            from open_packet.ui.tui.screens.setup_node import NodeSetupScreen
            self.app.push_screen(
                NodeSetupScreen(interfaces=self._db.list_interfaces(), db=self._db),
                callback=self._on_add,
            )
        elif btn_id == "close_btn":
            self.dismiss(self._needs_restart)
        elif btn_id.startswith("set_active_"):
            node_id = int(btn_id.split("_")[-1])
            self._set_active(node_id)
        elif btn_id.startswith("edit_"):
            node_id = int(btn_id.split("_")[-1])
            self._edit(node_id)

    def _edit(self, node_id: int) -> None:
        node = self._db.get_node(node_id)
        if node:
            from open_packet.ui.tui.screens.setup_node import NodeSetupScreen
            self.app.push_screen(
                NodeSetupScreen(node, interfaces=self._db.list_interfaces(), db=self._db),
                callback=lambda result: self._on_edit(result),
            )
```

- [ ] **Step 8: Run full test suite**

```bash
uv run pytest --tb=short 2>&1 | tail -15
```

Expected: all tests pass.

- [ ] **Step 9: Commit**

```bash
git add \
  open_packet/ui/tui/screens/manage_interfaces.py \
  open_packet/ui/tui/screens/settings.py \
  open_packet/ui/tui/screens/manage_nodes.py \
  tests/test_ui/test_setup_screens.py
git commit -m "feat: add InterfaceManageScreen, wire Settings Interfaces button, update NodeManageScreen push sites"
```

---

## Final verification

- [ ] **Run the complete test suite one last time**

```bash
uv run pytest -v 2>&1 | tail -30
```

Expected: all tests pass, no failures.
