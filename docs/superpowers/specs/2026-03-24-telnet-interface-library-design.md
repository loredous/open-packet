# TelnetLink + Interface Library Design

## Goal

Add Telnet-based BBS connectivity and a shared radio interface library. All connection configs (Telnet, KISS TCP, KISS Serial) are stored in the database as `Interface` records. Nodes reference an Interface via FK. Connection details are configured entirely through the TUI — the YAML config file's `connection` section is removed.

## Architecture

A new `Interface` model sits alongside `Operator` and `Node` in the store. `app.py._start_engine()` reads the node's Interface record and uses a `match` statement to build the right `ConnectionBase` implementation. A new `TelnetLink` is added for Telnet connections; the existing KISS/AX.25 path is unchanged in function, just wired differently. `BPQNode` requires no changes.

## Data Model

### New `Interface` dataclass (`store/models.py`)

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

### `Node` model change (`store/models.py`)

Add `interface_id: Optional[int] = None`.

### Database (`store/database.py`)

New `interfaces` table (DDL in `initialize()`):

```sql
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
)
```

Migration for existing `nodes` table:

```python
try:
    self._conn.execute("ALTER TABLE nodes ADD COLUMN interface_id INTEGER REFERENCES interfaces(id)")
except sqlite3.OperationalError:
    pass
```

New Database methods: `insert_interface(iface) -> Interface`, `get_interface(id) -> Interface`, `list_interfaces() -> list[Interface]`, `update_interface(iface) -> None`, `delete_interface(id) -> None`.

Existing `Node` database methods must also be updated:

- `insert_node()` — add `interface_id` to the INSERT column list and bound values tuple
- `update_node()` — add `interface_id = ?` to the SET clause
- `get_node()`, `get_default_node()`, `list_nodes()` — row mapper must read `interface_id=row["interface_id"]` when constructing `Node` objects

### Config (`config/config.py`)

Remove `TCPConnectionConfig`, `SerialConnectionConfig`, and the `connection` field from `AppConfig`. Keep `store` and `ui` sections. Remove `VALID_CONNECTION_TYPES`.

`AppConfig` becomes:

```python
@dataclass
class AppConfig:
    store: StoreConfig
    ui: UIConfig = field(default_factory=UIConfig)
```

`load_config()` no longer expects or validates a `connection` section. If an existing YAML file has a `connection` key it is silently ignored.

`main()` in `app.py` continues to load a config YAML (for `store` and `ui` settings), but no longer passes connection information to the app. `OpenPacketApp.__init__` signature loses any connection-related parameters; it reads only `config.store` and `config.ui`.

### Existing tests to migrate

- `tests/test_config/test_config.py` — all tests reference `config.connection.*` and construct YAML with `connection:` sections. Delete these tests; replace with a single test confirming `load_config` parses `store` and `ui` only (no connection field on result).
- `tests/test_ui/test_tui.py` — the `app_config` fixture passes `connection=TCPConnectionConfig(...)`. Remove the `connection` argument; the fixture constructs `AppConfig(store=..., ui=...)` only.
- `tests/test_ui/test_setup_screens.py` — the `base_config` fixture likewise passes `connection=...`. Same fix: remove the `connection` argument.

## Connection Layer

### New `open_packet/link/telnet.py`

`TelnetLink` implements `ConnectionBase`:

- `__init__(host, port, username, password)` — stores params, `_sock = None`
- `connect(callsign, ssid)` — callsign/ssid ignored; opens TCP socket. Login sequence loops on `recv()` accumulating into a buffer until each expected token is found (TCP may split responses across packets):
  1. Read until buffer contains `user:` → send `username\r\n`, clear buffer
  2. Read until buffer contains `password:` → send `password\r\n`, clear buffer
  3. Read until buffer stripped of IAC bytes ends with `>` (BPQ node prompt)
  Each read loop applies `_strip_iac()` before checking. Raises `ConnectionError` on timeout or if expected token not received.
- `send_frame(data)` — `self._sock.sendall(data)`
- `receive_frame(timeout)` — sets socket timeout, calls `recv(4096)`, strips IAC bytes from the result (see below), returns `b""` on `socket.timeout`
- `disconnect()` — closes and nulls the socket

**IAC stripping** — applied in both `connect()` login reads and `receive_frame()` to handle any server-initiated Telnet commands mid-session:

```python
import re
_IAC_RE = re.compile(b'\xff[\xf0-\xfa]|'   # 2-byte: IAC + single-byte cmd (NOP, GA, etc.)
                      b'\xff[\xfb-\xfe].')   # 3-byte: IAC WILL/WONT/DO/DONT + option
def _strip_iac(data: bytes) -> bytes:
    return _IAC_RE.sub(b'', data)
```

This handles both 2-byte commands (`\xff\xf9` GA, `\xff\xf1` NOP, etc.) and 3-byte option negotiations (`\xff\xfb\x03` WILL SUPPRESS-GO-AHEAD, `\xff\xfb\x01` WILL ECHO, etc.). Sub-negotiation sequences (SB...SE) are not expected from BPQ and are not handled; if encountered they would leave a trailing `\xf0` byte which `BPQNode`'s prompt detection (checks for trailing `>`) would simply not match, causing a timeout — an acceptable failure mode.

After `TelnetLink.connect()` returns, `BPQNode.connect_node()` runs unchanged — it sends `BBS\r` and waits for a prompt ending in `>`.

### `app.py._start_engine()` change

Replace the current transport/KISS/AX25 construction block with:

```python
iface = db.get_interface(node_record.interface_id)
match iface.iface_type:
    case "telnet":
        connection = TelnetLink(iface.host, iface.port, iface.username, iface.password)
    case "kiss_tcp":
        transport = TCPTransport(host=iface.host, port=iface.port)
        connection = AX25Connection(KISSLink(transport), my_callsign=operator.callsign, my_ssid=operator.ssid)
    case "kiss_serial":
        transport = SerialTransport(device=iface.device, baud=iface.baud)
        connection = AX25Connection(KISSLink(transport), my_callsign=operator.callsign, my_ssid=operator.ssid)
    case _:
        raise ValueError(f"Unknown interface type: {iface.iface_type!r}")
```

### `app.py._on_settings_result()` change

Add an `"interfaces"` branch:

```python
elif result == "interfaces":
    if self._db:
        from open_packet.ui.tui.screens.manage_interfaces import InterfaceManageScreen
        self.push_screen(InterfaceManageScreen(self._db), callback=self._on_manage_result)
```

`InterfaceManageScreen` dismisses with `True` (needs restart) or `False`. The existing `_on_manage_result` callback handles this — no change needed there.

## TUI Changes

### `NodeSetupScreen` redesign (`screens/setup_node.py`)

Constructor signature: `NodeSetupScreen(node: Optional[Node] = None, interfaces: list[Interface] = None, **kwargs)`. Callers must pass the list of existing interfaces fetched from `self._db.list_interfaces()` before pushing the screen. An empty list is valid — it results in "— New interface —" being the only option in the interface selector.

All push sites for `NodeSetupScreen` must be updated to pass `interfaces=`:

- `app.py._init_engine()` — pass `interfaces=self._db.list_interfaces()` (db is assigned before this push)
- `app.py._on_operator_setup_result()` — pass `interfaces=self._db.list_interfaces()` (db is always set here)
- `app.py._on_settings_result()` "node" fallback branch — pushes when `self._db` is falsy; pass `interfaces=[]`
- `manage_nodes.py` Add action — pass `interfaces=self._db.list_interfaces()`
- `manage_nodes.py` Edit action — pass `interfaces=self._db.list_interfaces()`

`None` is never passed as `interfaces`; the parameter default of `None` is a sentinel only. Internally the screen treats `None` and `[]` equivalently (shows only "— New interface —").

Keep existing fields (label, callsign, SSID, is_default). Add a connection section below:

1. **Connection type** — `Select` widget with options: `("Telnet", "telnet")`, `("KISS TCP", "kiss_tcp")`, `("KISS Serial", "kiss_serial")`
2. **Interface selector** — `Select` widget populated with existing interfaces of the selected type (label + id), plus a `("— New interface —", None)` option (default). Repopulates when connection type changes. If no interfaces of the selected type exist, only "— New interface —" is shown.
3. **Inline interface fields** — shown when "New interface" is selected, hidden when an existing interface is chosen:
   - Telnet: Host, Port, Username, Password
   - KISS TCP: Host, Port
   - KISS Serial: Device, Baud
   - All types: Interface Label (optional; auto-generated as `"{callsign} via {host}"` or `"{callsign} via {device}"` if blank)
4. **Validation** — on save:
   - If existing interface selected: use its id directly
   - If new interface: validate required fields for the type, insert Interface record, use new id
   - Node is saved with `interface_id` set

Required fields by type:
- Telnet: Host (non-empty), Port (integer > 0), Username (non-empty), Password (non-empty)
- KISS TCP: Host (non-empty), Port (integer > 0)
- KISS Serial: Device (non-empty), Baud (integer > 0)

### `SettingsScreen` (`screens/settings.py`)

Add an "Interfaces" button (`id="interfaces_btn"`). Dismiss with `"interfaces"` when pressed.

### New `InterfaceManageScreen` (`screens/manage_interfaces.py`)

Follows the same pattern as `OperatorManageScreen`/`NodeManageScreen`. Displays a list of Interface records with Add, Edit, Delete actions. Edit pushes `InterfaceSetupScreen` with the selected interface. Dismisses with `True` if any change was made (caller uses `_on_manage_result` which triggers `_restart_engine` when `True`), `False` otherwise.

Constructor: `InterfaceManageScreen(db: Database)`.

### New `InterfaceSetupScreen` (`screens/setup_interface.py`)

Modal for standalone create/edit of an Interface (used by `InterfaceManageScreen`). Same fields and validation as the inline section in `NodeSetupScreen`. Dismisses with an `Interface` object on save, `None` on cancel.

Constructor: `InterfaceSetupScreen(interface: Optional[Interface] = None, **kwargs)`.

## Error Handling

- `TelnetLink.connect()` raises `ConnectionError` if login fails or prompt not received within timeout
- Engine catches this and emits `ErrorEvent`, sets status to `ConnectionStatus.ERROR` (existing behavior)
- `_start_engine()` raises `ValueError` for unknown interface type — programmer error, not a runtime condition

## Testing

### `tests/test_link/test_telnet.py` (new)
- Mock socket; verify IAC bytes (`\xff\xfb\x03\xff\xfb\x01`) are stripped before prompt matching in `connect()`
- Verify 2-byte IAC (`\xff\xf9`) is stripped by `receive_frame()`
- Verify username/password sent in correct sequence
- `receive_frame` returns `b""` on `socket.timeout`
- `connect()` raises `ConnectionError` if no `>` prompt received within timeout

### `tests/test_ui/test_setup_screens.py` changes
- Delete `app_config` fixture's `connection=` argument (it now constructs `AppConfig(store=..., ui=...)`)
- Add: `NodeSetupScreen` with Telnet type + new interface: creates Interface record + Node with matching `interface_id`
- Add: `NodeSetupScreen` with existing interface pre-populated: node saved with correct `interface_id`, no new Interface created
- Add: connection type switch repopulates interface selector
- Add: `InterfaceSetupScreen` valid input dismisses with `Interface` object; cancel dismisses with `None`
- Add: missing required fields (e.g. blank host) do not dismiss

### `tests/test_ui/test_tui.py` changes
- Remove `connection=TCPConnectionConfig(...)` from `app_config` fixture

### `tests/test_config/test_config.py` changes
- Delete all existing tests (they all test `connection` field parsing)
- Add: `load_config` parses a YAML with only `store` + `ui` sections correctly; `connection` key in YAML is silently ignored

### `tests/test_store/test_database.py` additions
- Interface CRUD: insert returns object with id set; get by id; list returns all; update changes fields; delete removes record
- Migration: calling `initialize()` on a DB with an existing `nodes` table (no `interface_id` column) adds the column without error
- Node inserted with `interface_id` FK round-trips correctly
