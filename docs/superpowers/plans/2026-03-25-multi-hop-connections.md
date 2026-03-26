# Multi-Hop Connections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-hop path routing and neighbor discovery to open-packet, enabling BPQ `C`-command hop traversal, AX.25 digipeater VIA paths, and end-of-cycle prompts to add or shorten discovered node paths.

**Architecture:** A `NodeHop` dataclass (callsign + optional BPQ port) is serialized as JSON into a new `hop_path` column on `nodes`. The engine resolves the path during `_do_check_mail`: for `path_route` it connects to the first hop and uses `BPQNode.connect_node()` to traverse the rest via `C` commands; for `digipeat` it encodes hops as AX.25 VIA addresses. After disconnect, the engine emits a `NeighborsDiscoveredEvent` the TUI uses to prompt the user about new or shorter-path nodes.

**Tech Stack:** Python, SQLite (via existing `Database`/`Store`), Textual TUI, AX.25 v2.2 (KISS), BPQ32 BBS protocol, PyYAML config.

---

## File Map

**New files:**
- `open_packet/ui/tui/screens/shorter_path_confirm.py` — modal dialog: "shorter path discovered, update?"

**Modified files:**
- `open_packet/store/models.py` — add `NodeHop` dataclass; add `hop_path`, `path_strategy`, `auto_forward` to `Node`
- `open_packet/store/database.py` — schema migrations for new `nodes` columns + new `node_neighbors` table; update `insert_node` / `get_node` / `get_default_node` / `update_node` / `list_nodes`
- `open_packet/store/store.py` — add `upsert_node_neighbor`, `get_node_neighbors`
- `open_packet/config/config.py` — add `NodesConfig`; update `AppConfig` + `load_config`
- `open_packet/link/base.py` — add optional `via_path` keyword to `connect()`
- `open_packet/link/telnet.py` — accept and ignore `via_path`
- `open_packet/ax25/frame.py` — update `_addr_field` + `encode_sabm` to support VIA address list
- `open_packet/ax25/connection.py` — update `connect()` to accept `via_path` and pass it to `encode_sabm`
- `open_packet/node/base.py` — add `list_linked_nodes()` abstract method
- `open_packet/node/bpq.py` — update `__init__` + `connect_node()`; add `parse_nodes_list()` + `list_linked_nodes()`
- `open_packet/engine/events.py` — add `NeighborsDiscoveredEvent`; update `Event` union
- `open_packet/engine/engine.py` — discovery phase, auto-forward phase, updated `_do_check_mail`
- `open_packet/ui/tui/app.py` — handle `NeighborsDiscoveredEvent`; update `_start_engine` to pass hop path to `BPQNode`
- `open_packet/ui/tui/screens/setup_node.py` — hop path editor, strategy selector, `auto_forward` checkbox

**Test files touched:**
- `tests/test_store/test_store.py` — `node_neighbors` upsert tests
- `tests/test_node/test_bpq.py` — hop traversal + `list_linked_nodes` tests
- `tests/test_ax25/test_frame.py` — VIA address field encoding
- `tests/test_ax25/test_connection.py` — `connect()` with `via_path`
- `tests/test_config/test_config.py` — `NodesConfig` defaults + parsing
- `tests/test_engine/test_engine.py` — discovery phase event emission

---

## Task 1: `NodeHop` dataclass and updated `Node` model

**Files:**
- Modify: `open_packet/store/models.py`
- Test: `tests/test_store/test_store.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_store/test_store.py`:

```python
from open_packet.store.models import NodeHop, Node
import json

def test_nodehop_defaults():
    h = NodeHop(callsign="W0RELAY-1")
    assert h.port is None

def test_nodehop_with_port():
    h = NodeHop(callsign="W0RELAY-1", port=3)
    assert h.port == 3

def test_node_has_hop_path():
    n = Node(label="x", callsign="W0BPQ", ssid=0, node_type="bpq")
    assert n.hop_path == []
    assert n.path_strategy == "path_route"
    assert n.auto_forward is False

def test_nodehop_json_roundtrip():
    hops = [NodeHop(callsign="W0RELAY-1", port=3), NodeHop(callsign="W0DIST")]
    serialized = json.dumps([{"callsign": h.callsign, "port": h.port} for h in hops])
    parsed = [NodeHop(**d) for d in json.loads(serialized)]
    assert parsed[0].callsign == "W0RELAY-1"
    assert parsed[0].port == 3
    assert parsed[1].port is None
```

- [ ] **Step 2: Run tests to confirm failure**

```
uv run pytest tests/test_store/test_store.py::test_nodehop_defaults tests/test_store/test_store.py::test_node_has_hop_path -v
```

Expected: `ImportError` or `AttributeError` — `NodeHop` doesn't exist yet.

- [ ] **Step 3: Add `NodeHop` and update `Node` in `models.py`**

In `open_packet/store/models.py`, add before the `Message` dataclass:

```python
@dataclass
class NodeHop:
    callsign: str
    port: int | None = None
```

Update `Node` (add three new fields with defaults after `created_at`):

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
    hop_path: list["NodeHop"] = field(default_factory=list)
    path_strategy: str = "path_route"
    auto_forward: bool = False
```

Add `from dataclasses import dataclass, field` if `field` isn't already imported (it is via existing `field` usage for `Bulletin` — check the import line and add `field` if missing).

- [ ] **Step 4: Run tests to confirm pass**

```
uv run pytest tests/test_store/test_store.py::test_nodehop_defaults tests/test_store/test_store.py::test_nodehop_with_port tests/test_store/test_store.py::test_node_has_hop_path tests/test_store/test_store.py::test_nodehop_json_roundtrip -v
```

Expected: 4 PASSED.

- [ ] **Step 5: Run full suite to confirm no regressions**

```
uv run pytest -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add open_packet/store/models.py tests/test_store/test_store.py
git commit -m "feat: add NodeHop dataclass and hop_path/path_strategy/auto_forward to Node"
```

---

## Task 2: DB schema migrations and `node_neighbors` table

**Files:**
- Modify: `open_packet/store/database.py`
- Test: `tests/test_store/test_store.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_store/test_store.py`:

```python
def test_nodes_table_has_hop_path_column(db):
    cols = [r[1] for r in db._conn.execute("PRAGMA table_info(nodes)").fetchall()]
    assert "hop_path" in cols
    assert "path_strategy" in cols
    assert "auto_forward" in cols

def test_node_neighbors_table_exists(db):
    assert "node_neighbors" in db.table_names()

def test_node_neighbors_table_has_columns(db):
    cols = [r[1] for r in db._conn.execute("PRAGMA table_info(node_neighbors)").fetchall()]
    for c in ("id", "node_id", "callsign", "port", "first_seen", "last_seen"):
        assert c in cols
```

- [ ] **Step 2: Run to confirm failure**

```
uv run pytest tests/test_store/test_store.py::test_nodes_table_has_hop_path_column tests/test_store/test_store.py::test_node_neighbors_table_exists -v
```

Expected: FAIL — columns and table don't exist yet.

- [ ] **Step 3: Add `node_neighbors` to `_create_schema` and migrations to `initialize`**

In `open_packet/store/database.py`, add the `node_neighbors` CREATE TABLE to `_create_schema()`:

```python
            CREATE TABLE IF NOT EXISTS node_neighbors (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id     INTEGER NOT NULL REFERENCES nodes(id),
                callsign    TEXT NOT NULL,
                port        INTEGER,
                first_seen  TEXT NOT NULL,
                last_seen   TEXT NOT NULL,
                UNIQUE(node_id, callsign)
            );
```

Add three migrations in `initialize()`, after the existing bulletin migrations:

```python
for sql in [
    "ALTER TABLE nodes ADD COLUMN hop_path TEXT NOT NULL DEFAULT '[]'",
    "ALTER TABLE nodes ADD COLUMN path_strategy TEXT NOT NULL DEFAULT 'path_route'",
    "ALTER TABLE nodes ADD COLUMN auto_forward INTEGER NOT NULL DEFAULT 0",
]:
    try:
        self._conn.execute(sql)
        self._conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists
```

- [ ] **Step 4: Run tests to confirm pass**

```
uv run pytest tests/test_store/test_store.py::test_nodes_table_has_hop_path_column tests/test_store/test_store.py::test_node_neighbors_table_exists tests/test_store/test_store.py::test_node_neighbors_table_has_columns -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Update node read/write methods in `database.py` to handle new columns**

Add a helper at module level in `database.py`:

```python
import json as _json

def _hops_to_json(hops) -> str:
    return _json.dumps([{"callsign": h.callsign, "port": h.port} for h in hops])

def _json_to_hops(s: str):
    from open_packet.store.models import NodeHop
    try:
        return [NodeHop(**d) for d in _json.loads(s or "[]")]
    except Exception:
        return []
```

Update `insert_node`:

```python
def insert_node(self, node: Node) -> Node:
    assert self._conn
    cur = self._conn.execute(
        """INSERT INTO nodes
           (label, callsign, ssid, node_type, is_default, interface_id,
            hop_path, path_strategy, auto_forward)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (node.label, node.callsign, node.ssid, node.node_type,
         int(node.is_default), node.interface_id,
         _hops_to_json(node.hop_path), node.path_strategy, int(node.auto_forward)),
    )
    self._conn.commit()
    return self.get_node(cur.lastrowid)
```

Update `_row_to_node` helper (extract from `get_node`, `get_default_node`, `list_nodes` — they all repeat the same construction). Replace all three with a shared helper:

```python
def _row_to_node(self, row) -> Node:
    return Node(
        id=row["id"], label=row["label"], callsign=row["callsign"],
        ssid=row["ssid"], node_type=row["node_type"],
        is_default=bool(row["is_default"]),
        interface_id=row["interface_id"],
        hop_path=_json_to_hops(row["hop_path"] if "hop_path" in row.keys() else "[]"),
        path_strategy=row["path_strategy"] if "path_strategy" in row.keys() else "path_route",
        auto_forward=bool(row["auto_forward"]) if "auto_forward" in row.keys() else False,
    )
```

Update `get_node`, `get_default_node`, `list_nodes` to use `self._row_to_node(row)`.

Update `update_node`:

```python
def update_node(self, node: Node) -> None:
    assert self._conn
    assert node.id is not None
    self._conn.execute(
        """UPDATE nodes SET label=?, callsign=?, ssid=?, node_type=?,
           is_default=?, interface_id=?, hop_path=?, path_strategy=?, auto_forward=?
           WHERE id=?""",
        (node.label, node.callsign, node.ssid, node.node_type,
         int(node.is_default), node.interface_id,
         _hops_to_json(node.hop_path), node.path_strategy, int(node.auto_forward),
         node.id),
    )
    self._conn.commit()
```

- [ ] **Step 6: Write and run a roundtrip test**

Add to `tests/test_store/test_store.py`:

```python
def test_node_hop_path_roundtrip(db):
    from open_packet.store.models import NodeHop
    node = Node(
        label="Relay BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
        hop_path=[NodeHop("W0RELAY", port=3)],
        path_strategy="path_route",
        auto_forward=True,
    )
    inserted = db.insert_node(node)
    fetched = db.get_node(inserted.id)
    assert fetched.hop_path[0].callsign == "W0RELAY"
    assert fetched.hop_path[0].port == 3
    assert fetched.path_strategy == "path_route"
    assert fetched.auto_forward is True

def test_node_hop_path_defaults_on_existing_rows(db):
    # Simulate a node inserted without the new columns (migration scenario)
    # by directly inserting a minimal row
    db._conn.execute(
        "INSERT INTO nodes (label, callsign, ssid, node_type, is_default) VALUES (?, ?, ?, ?, ?)",
        ("Old Node", "W0OLD", 0, "bpq", 0),
    )
    db._conn.commit()
    node = db.get_default_node()  # may be None; use list_nodes
    nodes = db.list_nodes()
    old = next(n for n in nodes if n.callsign == "W0OLD")
    assert old.hop_path == []
    assert old.path_strategy == "path_route"
    assert old.auto_forward is False
```

Run:
```
uv run pytest tests/test_store/test_store.py::test_node_hop_path_roundtrip tests/test_store/test_store.py::test_node_hop_path_defaults_on_existing_rows -v
```

Expected: 2 PASSED.

- [ ] **Step 7: Run full suite**

```
uv run pytest -q
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add open_packet/store/models.py open_packet/store/database.py tests/test_store/test_store.py
git commit -m "feat: db migrations for node hop_path/path_strategy/auto_forward and node_neighbors table"
```

---

## Task 3: Store `node_neighbors` methods

**Files:**
- Modify: `open_packet/store/store.py`
- Test: `tests/test_store/test_store.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_store/test_store.py` (use the existing `db` fixture and add a `store` fixture):

```python
from open_packet.store.store import Store

@pytest.fixture
def store(db):
    return Store(db)

@pytest.fixture
def sample_node(db):
    node = Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True)
    return db.insert_node(node)

def test_upsert_neighbor_inserts_new(store, sample_node):
    store.upsert_node_neighbor(sample_node.id, "W0RELAY-1", port=3)
    neighbors = store.get_node_neighbors(sample_node.id)
    assert len(neighbors) == 1
    assert neighbors[0].callsign == "W0RELAY-1"
    assert neighbors[0].port == 3

def test_upsert_neighbor_updates_last_seen(store, sample_node):
    store.upsert_node_neighbor(sample_node.id, "W0RELAY-1", port=3)
    n1 = store.get_node_neighbors(sample_node.id)[0]
    import time; time.sleep(0.01)
    store.upsert_node_neighbor(sample_node.id, "W0RELAY-1", port=3)
    n2 = store.get_node_neighbors(sample_node.id)[0]
    assert n2.last_seen >= n1.last_seen

def test_upsert_neighbor_does_not_duplicate(store, sample_node):
    store.upsert_node_neighbor(sample_node.id, "W0RELAY-1", port=3)
    store.upsert_node_neighbor(sample_node.id, "W0RELAY-1", port=3)
    assert len(store.get_node_neighbors(sample_node.id)) == 1

def test_get_node_neighbors_returns_nodehop(store, sample_node):
    from open_packet.store.models import NodeHop
    store.upsert_node_neighbor(sample_node.id, "W0DIST", port=None)
    neighbors = store.get_node_neighbors(sample_node.id)
    assert isinstance(neighbors[0], NodeHop)
    assert neighbors[0].port is None
```

- [ ] **Step 2: Run to confirm failure**

```
uv run pytest tests/test_store/test_store.py::test_upsert_neighbor_inserts_new -v
```

Expected: `AttributeError` — `store.upsert_node_neighbor` doesn't exist.

- [ ] **Step 3: Add `upsert_node_neighbor` and `get_node_neighbors` to `store.py`**

`Store` already exposes `self._conn` via an existing property (`return self._db._conn`), so the methods below use the same pattern as all other `Store` methods.

Add to `open_packet/store/store.py`:

```python
def upsert_node_neighbor(self, node_id: int, callsign: str, port: int | None) -> None:
    assert self._conn
    now = datetime.now(timezone.utc).isoformat()
    self._conn.execute(
        """INSERT INTO node_neighbors (node_id, callsign, port, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(node_id, callsign) DO UPDATE SET last_seen=excluded.last_seen""",
        (node_id, callsign, port, now, now),
    )
    self._conn.commit()

def get_node_neighbors(self, node_id: int) -> list:
    assert self._conn
    from open_packet.store.models import NodeHop
    rows = self._conn.execute(
        "SELECT callsign, port FROM node_neighbors WHERE node_id=? ORDER BY callsign",
        (node_id,),
    ).fetchall()
    return [NodeHop(callsign=r["callsign"], port=r["port"]) for r in rows]
```

- [ ] **Step 4: Run tests to confirm pass**

```
uv run pytest tests/test_store/test_store.py::test_upsert_neighbor_inserts_new tests/test_store/test_store.py::test_upsert_neighbor_updates_last_seen tests/test_store/test_store.py::test_upsert_neighbor_does_not_duplicate tests/test_store/test_store.py::test_get_node_neighbors_returns_nodehop -v
```

Expected: 4 PASSED.

- [ ] **Step 5: Run full suite**

```
uv run pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add open_packet/store/store.py tests/test_store/test_store.py
git commit -m "feat: add upsert_node_neighbor and get_node_neighbors to Store"
```

---

## Task 4: `NodesConfig` global config

**Files:**
- Modify: `open_packet/config/config.py`
- Test: `tests/test_config/test_config.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_config/test_config.py`:

```python
from open_packet.config.config import AppConfig, load_config, NodesConfig

def test_nodes_config_default():
    cfg = AppConfig()
    assert cfg.nodes.auto_discover is True

def test_nodes_config_from_yaml(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("store:\n  db_path: /tmp/x.db\nnodes:\n  auto_discover: false\n")
    cfg = load_config(str(f))
    assert cfg.nodes.auto_discover is False

def test_nodes_config_absent_key_defaults_true(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("store:\n  db_path: /tmp/x.db\n")
    cfg = load_config(str(f))
    assert cfg.nodes.auto_discover is True
```

- [ ] **Step 2: Run to confirm failure**

```
uv run pytest tests/test_config/test_config.py::test_nodes_config_default -v
```

Expected: `ImportError` or `AttributeError`.

- [ ] **Step 3: Add `NodesConfig` and wire into `AppConfig` + `load_config`**

In `open_packet/config/config.py`:

```python
@dataclass
class NodesConfig:
    auto_discover: bool = True
```

Update `AppConfig`:

```python
@dataclass
class AppConfig:
    store: StoreConfig = field(default_factory=StoreConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    nodes: NodesConfig = field(default_factory=NodesConfig)
```

Add helper:

```python
def _parse_nodes(raw: dict) -> NodesConfig:
    return NodesConfig(
        auto_discover=bool(raw.get("auto_discover", True)),
    )
```

Update `load_config`:

```python
return AppConfig(
    store=_parse_store(raw.get("store", {})),
    ui=_parse_ui(raw.get("ui", {})),
    nodes=_parse_nodes(raw.get("nodes", {})),
)
```

- [ ] **Step 4: Run tests to confirm pass**

```
uv run pytest tests/test_config/ -v
```

Expected: all pass.

- [ ] **Step 5: Run full suite**

```
uv run pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add open_packet/config/config.py tests/test_config/test_config.py
git commit -m "feat: add NodesConfig with auto_discover to AppConfig"
```

---

## Task 5: AX.25 VIA address encoding

**Files:**
- Modify: `open_packet/ax25/frame.py`
- Modify: `open_packet/ax25/connection.py`
- Modify: `open_packet/link/base.py`
- Modify: `open_packet/link/telnet.py`
- Test: `tests/test_ax25/test_frame.py`
- Test: `tests/test_ax25/test_connection.py`

- [ ] **Step 1: Write failing tests for VIA frame encoding**

Add to `tests/test_ax25/test_frame.py`:

```python
from open_packet.ax25.frame import encode_sabm, decode_frame, FrameType
from open_packet.ax25.address import decode_address

def test_encode_sabm_no_via():
    """Baseline: 14-byte address field, last bit set on source."""
    raw = encode_sabm("W0BPQ", 1, "KD9ABC", 0)
    src = decode_address(raw[7:14])
    assert src.last is True
    assert len(raw) == 15  # 14-byte addr + 1-byte ctrl

def test_encode_sabm_with_via():
    """With one VIA hop: 21-byte address field, source last=False, VIA last=True."""
    raw = encode_sabm("W0BPQ", 1, "KD9ABC", 0, via=[("W0RELAY", 1)])
    assert len(raw) == 22  # 21-byte addr + 1 ctrl
    src = decode_address(raw[7:14])
    assert src.last is False
    via = decode_address(raw[14:21])
    assert via.callsign.strip() == "W0RELAY"
    assert via.ssid == 1
    assert via.last is True

def test_encode_sabm_with_two_via():
    """Two VIA hops: first VIA last=False, second VIA last=True."""
    raw = encode_sabm("W0BPQ", 1, "KD9ABC", 0, via=[("W0R1", 0), ("W0R2", 0)])
    assert len(raw) == 29  # 28-byte addr + 1 ctrl
    v1 = decode_address(raw[14:21])
    v2 = decode_address(raw[21:28])
    assert v1.last is False
    assert v2.last is True
```

- [ ] **Step 2: Run to confirm failure**

```
uv run pytest tests/test_ax25/test_frame.py::test_encode_sabm_with_via -v
```

Expected: `TypeError` — `encode_sabm` doesn't accept `via`.

- [ ] **Step 3: Update `_addr_field` and `encode_sabm` in `frame.py`**

Replace `_addr_field`:

```python
def _addr_field(dest: str, dest_ssid: int, src: str, src_ssid: int,
                command: bool, via: list[tuple[str, int]] | None = None) -> bytes:
    """Build address field. via is list of (callsign, ssid) tuples."""
    via = via or []
    src_last = len(via) == 0
    result = encode_address(dest, dest_ssid, last=False, c_bit=command)
    result += encode_address(src, src_ssid, last=src_last, c_bit=not command)
    for i, (v_call, v_ssid) in enumerate(via):
        result += encode_address(v_call, v_ssid, last=(i == len(via) - 1))
    return result
```

Update `encode_sabm`:

```python
def encode_sabm(dest: str, dest_ssid: int, src: str, src_ssid: int,
                poll: bool = True,
                via: list[tuple[str, int]] | None = None) -> bytes:
    ctrl = U_SABM | (P_BIT if poll else 0)
    return _addr_field(dest, dest_ssid, src, src_ssid, command=True, via=via) + bytes([ctrl])
```

- [ ] **Step 4: Run frame tests**

```
uv run pytest tests/test_ax25/test_frame.py -v
```

Expected: all pass including the 3 new tests.

- [ ] **Step 5: Update `ConnectionBase.connect()` signature**

In `open_packet/link/base.py`:

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from open_packet.store.models import NodeHop


class ConnectionError(Exception):
    pass


class ConnectionBase(ABC):
    @abstractmethod
    def connect(self, callsign: str, ssid: int,
                via_path: "list[NodeHop] | None" = None) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def send_frame(self, data: bytes) -> None: ...

    @abstractmethod
    def receive_frame(self, timeout: float = 5.0) -> bytes: ...
```

- [ ] **Step 6: Update `TelnetLink.connect()` to accept and ignore `via_path`**

In `open_packet/link/telnet.py`, change the signature:

```python
def connect(self, callsign: str, ssid: int, via_path=None) -> None:
    """Connect to Telnet BPQ node and log in. callsign/ssid/via_path are ignored."""
```

- [ ] **Step 6b: Update existing mock helpers to accept `via_path=None`**

`ConnectionBase.connect()` now has `via_path=None`. Any test mock that implements `connect(self, callsign, ssid)` will raise `TypeError` if called with the keyword argument. Update both:

In `tests/test_ax25/test_connection.py`, `MockKISS`:
```python
def connect(self, callsign, ssid, via_path=None):
    self.connected = True
```

In `tests/test_node/test_bpq.py`, `MockConn`:
```python
def connect(self, callsign, ssid, via_path=None): pass
```

In `tests/test_link/test_telnet.py` (if any mock implements `connect`): add `via_path=None` similarly.

Run the full suite immediately after this step to confirm no regressions:
```
uv run pytest -q
```

- [ ] **Step 7: Add a helper to parse SSID from callsign string and update `AX25Connection.connect()`**

In `open_packet/ax25/connection.py`, add a module-level helper:

```python
def _split_callsign(s: str) -> tuple[str, int]:
    """Split 'W0RELAY-1' → ('W0RELAY', 1). No dash → ssid 0."""
    if "-" in s:
        call, ssid_str = s.rsplit("-", 1)
        try:
            return call.upper(), int(ssid_str)
        except ValueError:
            pass
    return s.upper(), 0
```

Update `AX25Connection.connect()`:

```python
def connect(self, callsign: str, ssid: int, via_path=None) -> None:
    self._dest_call = callsign
    self._dest_ssid = ssid
    self._kiss.connect(callsign, ssid)
    via_tuples = None
    if via_path:
        via_tuples = [_split_callsign(h.callsign) for h in via_path]
    self._establish_data_link(via=via_tuples)
```

Update `_establish_data_link` to accept and pass through `via`:

```python
def _establish_data_link(self, via: list[tuple[str, int]] | None = None) -> None:
    self.state = LinkState.AWAITING_CONNECTION
    self.RC = 0
    self._clear_exception_conditions()
    self._send_sabm(poll=True, via=via)
    self._t1.start(self._t1_timeout)
    # ... rest unchanged, but also pass via= to retransmit attempts:
```

Update `_send_sabm` to pass `via`:

```python
def _send_sabm(self, poll: bool = True, via=None) -> None:
    raw = encode_sabm(self._dest_call, self._dest_ssid,
                      self._my_call, self._my_ssid, poll=poll, via=via)
    self._kiss.send_frame(raw)
    logger.debug("→ SABM (P=%s, via=%s)", poll, via)
```

Also store `via` on the instance for retransmit in `_establish_data_link`:

```python
def _establish_data_link(self, via=None) -> None:
    self._via = via  # store for retry
    self.state = LinkState.AWAITING_CONNECTION
    self.RC = 0
    self._clear_exception_conditions()
    self._send_sabm(poll=True, via=via)
    self._t1.start(self._t1_timeout)

    deadline = time.monotonic() + self._t1_timeout * (self._n2 + 1)
    while time.monotonic() < deadline:
        raw = self._kiss.receive_frame(timeout=1.0)
        if not raw:
            if self._t1.expired:
                if self.RC >= self._n2:
                    self.state = LinkState.DISCONNECTED
                    raise ConnectionError(f"No UA after {self._n2} SABM attempts")
                self.RC += 1
                self._send_sabm(poll=True, via=via)  # ← pass via here
                self._t1.start(self._t1_timeout)
            continue
        # ... rest of the loop unchanged
```

Also initialize `self._via = None` in `__init__`.

- [ ] **Step 8: Write a connection test for VIA path**

Add to `tests/test_ax25/test_connection.py`:

```python
from open_packet.store.models import NodeHop
from open_packet.ax25.address import decode_address

def test_connect_with_via_path_encodes_via_in_sabm():
    kiss = MockKISS()
    conn = AX25Connection(kiss=kiss, my_callsign=MY_CALL, my_ssid=MY_SSID)
    # Inject UA to satisfy the handshake
    from open_packet.ax25.frame import encode_ua
    ua = encode_ua(MY_CALL, MY_SSID, DEST_CALL, DEST_SSID, final=True)
    kiss.inject(ua)
    via = [NodeHop(callsign="W0RELAY-1")]
    conn.connect(DEST_CALL, DEST_SSID, via_path=via)
    sabm_raw = kiss.sent[0]
    # Address field should be 21 bytes (dest 7 + src 7 + via 7)
    src_addr = decode_address(sabm_raw[7:14])
    assert src_addr.last is False  # source not last when via present
    via_addr = decode_address(sabm_raw[14:21])
    assert via_addr.callsign.strip() == "W0RELAY"
    assert via_addr.ssid == 1
    assert via_addr.last is True
```

- [ ] **Step 9: Run all AX.25 tests**

```
uv run pytest tests/test_ax25/ -v
```

Expected: all pass.

- [ ] **Step 10: Run full suite**

```
uv run pytest -q
```

- [ ] **Step 11: Commit**

```bash
git add open_packet/ax25/frame.py open_packet/ax25/connection.py \
        open_packet/link/base.py open_packet/link/telnet.py \
        tests/test_ax25/test_frame.py tests/test_ax25/test_connection.py
git commit -m "feat: AX.25 VIA path encoding in SABM and ConnectionBase.connect() via_path param"
```

---

## Task 6: `BPQNode` hop traversal and `list_linked_nodes`

**Files:**
- Modify: `open_packet/node/base.py`
- Modify: `open_packet/node/bpq.py`
- Test: `tests/test_node/test_bpq.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_node/test_bpq.py`:

```python
from open_packet.store.models import NodeHop

NODES_OUTPUT = """\
Nodes
Callsign  Port  Quality  Hops
W0RELAY-1    3      200     1
W0DIST       1      150     2
:
BPQ>
"""

def test_parse_nodes_list():
    from open_packet.node.bpq import parse_nodes_list
    hops = parse_nodes_list(NODES_OUTPUT)
    assert len(hops) == 2
    assert hops[0].callsign == "W0RELAY-1"
    assert hops[0].port == 3
    assert hops[1].callsign == "W0DIST"
    assert hops[1].port == 1

def test_parse_nodes_list_missing_port():
    from open_packet.node.bpq import parse_nodes_list
    output = "Nodes\nW0RELAY-1    bad   200   1\nBPQ>\n"
    hops = parse_nodes_list(output)
    assert hops[0].port is None

def test_parse_nodes_list_empty():
    from open_packet.node.bpq import parse_nodes_list
    assert parse_nodes_list("No nodes\nBPQ>\n") == []

def test_list_linked_nodes_sends_nodes_command():
    conn = MockConn(responses=[
        (NODES_OUTPUT).encode(),
    ])
    node = BPQNode(connection=conn, node_callsign="W0BPQ", node_ssid=1,
                   my_callsign="KD9ABC", my_ssid=0)
    hops = node.list_linked_nodes()
    assert conn.sent[0] == b"NODES\r"
    assert len(hops) == 2

def test_connect_node_single_hop_sends_only_bbs():
    """Single hop: hop_path[1:] is empty, so no C command — only BBS\r.
    hop_path[0] is the link-layer target; connect_node only traverses [1:]."""
    conn = MockConn(responses=[b"BPQ>"])
    node = BPQNode(
        connection=conn, node_callsign="W0BPQ", node_ssid=1,
        my_callsign="KD9ABC", my_ssid=0,
        hop_path=[NodeHop(callsign="W0RELAY", port=3)],
        path_strategy="path_route",
    )
    node.connect_node()
    assert conn.sent[0] == b"BBS\r"

def test_connect_node_path_route_two_hops():
    """Two hops: connect_node traverses hop_path[1:] only — one C command then BBS."""
    conn = MockConn(responses=[b"W0HOP2>", b"BPQ>"])
    node = BPQNode(
        connection=conn, node_callsign="W0BPQ", node_ssid=1,
        my_callsign="KD9ABC", my_ssid=0,
        hop_path=[NodeHop("W0HOP1", port=2), NodeHop("W0HOP2", port=1)],
        path_strategy="path_route",
    )
    node.connect_node()
    # hop_path[0] handled by link layer; hop_path[1:] = [W0HOP2:1]
    assert conn.sent[0] == b"C 1 W0HOP2\r"
    assert conn.sent[1] == b"BBS\r"

def test_connect_node_path_route_two_hops_no_port():
    """Second hop with no port: C command has no port prefix."""
    conn = MockConn(responses=[b"W0HOP2>", b"BPQ>"])
    node = BPQNode(
        connection=conn, node_callsign="W0BPQ", node_ssid=1,
        my_callsign="KD9ABC", my_ssid=0,
        hop_path=[NodeHop("W0HOP1"), NodeHop("W0HOP2")],
        path_strategy="path_route",
    )
    node.connect_node()
    assert conn.sent[0] == b"C W0HOP2\r"

def test_connect_node_digipeat_no_c_commands():
    """Digipeat strategy: connect_node sends BBS only regardless of hop_path."""
    conn = MockConn(responses=[b"BPQ>"])
    node = BPQNode(
        connection=conn, node_callsign="W0BPQ", node_ssid=1,
        my_callsign="KD9ABC", my_ssid=0,
        hop_path=[NodeHop(callsign="W0RELAY", port=3)],
        path_strategy="digipeat",
    )
    node.connect_node()
    assert conn.sent[0] == b"BBS\r"
```

- [ ] **Step 2: Run to confirm failure**

```
uv run pytest tests/test_node/test_bpq.py::test_parse_nodes_list tests/test_node/test_bpq.py::test_connect_node_path_route_single_hop -v
```

Expected: `ImportError` for `parse_nodes_list`, `TypeError` for unknown kwargs on `BPQNode`.

- [ ] **Step 3: Add `list_linked_nodes` abstract method to `NodeBase`**

In `open_packet/node/base.py`, add to the class:

```python
@abstractmethod
def list_linked_nodes(self) -> list: ...
```

- [ ] **Step 4: Update `BPQNode` in `bpq.py`**

Add `parse_nodes_list` module-level function:

```python
def parse_nodes_list(text: str) -> list:
    from open_packet.store.models import NodeHop
    hops = []
    for line in text.splitlines():
        if line.rstrip().endswith(">"):
            break
        parts = line.split()
        if len(parts) < 2:
            continue
        callsign = parts[0]
        # Real callsigns always contain at least one digit — filters out header
        # lines like "Callsign", "Nodes", "Hops".
        if not re.search(r'\d', callsign):
            continue
        try:
            port = int(parts[1])
        except (ValueError, IndexError):
            port = None
        hops.append(NodeHop(callsign=callsign, port=port))
    return hops
```

Update `BPQNode.__init__`:

```python
def __init__(self, connection: ConnectionBase, node_callsign: str,
             node_ssid: int, my_callsign: str, my_ssid: int,
             hop_path=None, path_strategy: str = "path_route"):
    self._conn = connection
    self._node_callsign = node_callsign
    self._node_ssid = node_ssid
    self._my_callsign = my_callsign
    self._my_ssid = my_ssid
    self._hop_path = hop_path or []
    self._path_strategy = path_strategy
```

Update `connect_node`:

```python
def connect_node(self) -> None:
    # Traverse hop_path[1:] with C commands for path_route strategy.
    # hop_path[0] is already handled by the link layer (connection.connect()).
    if self._path_strategy == "path_route" and len(self._hop_path) > 1:
        for hop in self._hop_path[1:]:
            if hop.port is not None:
                self._send_text(f"C {hop.port} {hop.callsign}")
            else:
                self._send_text(f"C {hop.callsign}")
            response = self._recv_until_prompt()
            if not response.rstrip().endswith(">"):
                raise NodeError(f"No prompt after C command to {hop.callsign}. Got: {response!r}")

    # Navigate to BBS
    self._send_text("BBS")
    response = self._recv_until_prompt()
    if "Connected to BBS" not in response and not response.rstrip().endswith(">"):
        raise NodeError(f"Failed to connect to BBS. Got: {response!r}")
    if not response.rstrip().endswith(">"):
        self._send_text("")
        response = self._recv_until_prompt()
    if "name" in response.lower():
        self._send_text(self._my_callsign)
        response = self._recv_until_prompt()
    if not response.rstrip().endswith(">"):
        raise NodeError(f"No BBS prompt received. Got: {response!r}")
```

Add `list_linked_nodes`:

```python
def list_linked_nodes(self) -> list:
    self._send_text("NODES")
    response = self._recv_until_prompt()
    return parse_nodes_list(response)
```

- [ ] **Step 5: Run node tests**

```
uv run pytest tests/test_node/test_bpq.py -v
```

Expected: all pass.

- [ ] **Step 6: Run full suite**

```
uv run pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add open_packet/node/base.py open_packet/node/bpq.py tests/test_node/test_bpq.py
git commit -m "feat: BPQNode hop traversal, list_linked_nodes, parse_nodes_list"
```

---

## Task 7: `NeighborsDiscoveredEvent`

**Files:**
- Modify: `open_packet/engine/events.py`
- Test: `tests/test_engine/test_engine.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_engine/test_engine.py`:

```python
from open_packet.engine.events import Event, NeighborsDiscoveredEvent
from open_packet.store.models import NodeHop

def test_neighbors_discovered_event_in_union():
    import typing
    args = typing.get_args(Event)
    assert NeighborsDiscoveredEvent in args

def test_neighbors_discovered_event_fields():
    from open_packet.store.models import Node
    node = Node(label="x", callsign="W0BPQ", ssid=0, node_type="bpq", id=1)
    evt = NeighborsDiscoveredEvent(
        node_id=1,
        new_neighbors=[NodeHop("W0RELAY-1", port=3)],
        shorter_path_candidates=[(node, [NodeHop("W0RELAY-1", port=3)])],
    )
    assert evt.node_id == 1
    assert evt.new_neighbors[0].callsign == "W0RELAY-1"
    assert evt.shorter_path_candidates[0][0].callsign == "W0BPQ"
```

- [ ] **Step 2: Run to confirm failure**

```
uv run pytest tests/test_engine/test_engine.py::test_neighbors_discovered_event_in_union -v
```

Expected: `ImportError`.

- [ ] **Step 3: Add event to `events.py`**

In `open_packet/engine/events.py`, add before the `Event` union:

```python
@dataclass
class NeighborsDiscoveredEvent:
    node_id: int
    new_neighbors: list  # list[NodeHop]
    shorter_path_candidates: list  # list[tuple[Node, list[NodeHop]]]
```

Update the `Event` union:

```python
Event = (ConnectionStatusEvent | MessageReceivedEvent | SyncCompleteEvent
         | ErrorEvent | MessageQueuedEvent | ConsoleEvent | NeighborsDiscoveredEvent)
```

- [ ] **Step 4: Run tests**

```
uv run pytest tests/test_engine/test_engine.py::test_neighbors_discovered_event_in_union tests/test_engine/test_engine.py::test_neighbors_discovered_event_fields -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Run full suite**

```
uv run pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add open_packet/engine/events.py tests/test_engine/test_engine.py
git commit -m "feat: add NeighborsDiscoveredEvent to events and Event union"
```

---

## Task 8: Engine discovery phase and neighbor classification

**Files:**
- Modify: `open_packet/engine/engine.py`
- Test: `tests/test_engine/test_engine.py`

- [ ] **Step 1: Write failing tests**

Look at the existing `test_engine.py` for the `MockNode` and `MockStore` patterns. Add:

```python
# Assumes existing MockNode, MockStore, MockConnection fixtures in the file.
# If they don't exist, add minimal ones:

class MockNodeWithNeighbors:
    """Like MockNode but list_linked_nodes returns a fixed list."""
    def __init__(self, neighbors):
        self._neighbors = neighbors
        self.connected = False
        self.messages = []
        self.bulletins = []

    def connect_node(self): self.connected = True
    def list_messages(self): return []
    def read_message(self, bbs_id): return None
    def send_message(self, *a): pass
    def delete_message(self, *a): pass
    def list_bulletins(self, **kw): return []
    def read_bulletin(self, bbs_id): return None
    def post_bulletin(self, *a): pass
    def list_linked_nodes(self): return self._neighbors


def test_discovery_phase_upserts_neighbors(engine_with_discovery):
    """When auto_discover=True, check_mail upserts discovered neighbors."""
    engine, store, mock_node = engine_with_discovery
    engine._cmd_queue.put(CheckMailCommand())
    import time; time.sleep(0.3)
    neighbors = store.get_node_neighbors(engine._node_record.id)
    assert any(n.callsign == "W0RELAY-1" for n in neighbors)

def test_discovery_phase_emits_new_neighbor_event(engine_with_discovery):
    engine, store, mock_node = engine_with_discovery
    engine._cmd_queue.put(CheckMailCommand())
    import time; time.sleep(0.3)
    events = []
    while not engine._evt_queue.empty():
        events.append(engine._evt_queue.get_nowait())
    neighbor_events = [e for e in events if isinstance(e, NeighborsDiscoveredEvent)]
    assert len(neighbor_events) == 1
    assert neighbor_events[0].new_neighbors[0].callsign == "W0RELAY-1"

def test_discovery_phase_skipped_when_disabled(engine_no_discovery):
    engine, store, mock_node = engine_no_discovery
    engine._cmd_queue.put(CheckMailCommand())
    import time; time.sleep(0.3)
    neighbors = store.get_node_neighbors(engine._node_record.id)
    assert neighbors == []
```

The test fixtures (`engine_with_discovery`, `engine_no_discovery`) should be defined as `pytest.fixture` functions that build an `Engine` with a temp DB, a `MockNodeWithNeighbors`, and appropriate `NodesConfig`.

- [ ] **Step 2: Add fixtures and run to confirm failure**

Add to `tests/test_engine/test_engine.py`:

```python
import pytest, queue, tempfile, os
from open_packet.config.config import AppConfig, NodesConfig
from open_packet.engine.engine import Engine
from open_packet.store.database import Database
from open_packet.store.store import Store
from open_packet.store.models import Operator, Node, NodeHop
from open_packet.engine.commands import CheckMailCommand
from open_packet.engine.events import NeighborsDiscoveredEvent

class MockConnection:
    def connect(self, *a, **kw): pass
    def disconnect(self): pass
    def send_frame(self, d): pass
    def receive_frame(self, timeout=5.0): return b""

def _make_engine(neighbors, auto_discover):
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    db = Database(f.name)
    db.initialize()
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="me", is_default=True))
    node_rec = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1,
                                    node_type="bpq", is_default=True))
    store = Store(db)
    mock_node = MockNodeWithNeighbors(neighbors)
    cfg = AppConfig(nodes=NodesConfig(auto_discover=auto_discover))
    cmd_q, evt_q = queue.Queue(), queue.Queue()
    engine = Engine(
        command_queue=cmd_q, event_queue=evt_q, store=store,
        operator=op, node_record=node_rec,
        connection=MockConnection(), node=mock_node,
        config=cfg,
    )
    engine.start()
    return engine, store, mock_node

@pytest.fixture
def engine_with_discovery():
    engine, store, node = _make_engine(
        neighbors=[NodeHop("W0RELAY-1", port=3)],
        auto_discover=True,
    )
    yield engine, store, node
    engine.stop()

@pytest.fixture
def engine_no_discovery():
    engine, store, node = _make_engine(
        neighbors=[NodeHop("W0RELAY-1", port=3)],
        auto_discover=False,
    )
    yield engine, store, node
    engine.stop()
```

Run:
```
uv run pytest tests/test_engine/test_engine.py::test_discovery_phase_upserts_neighbors -v
```

Expected: `TypeError` — `Engine.__init__` doesn't accept `config`.

- [ ] **Step 3: Update `Engine.__init__` to accept `config` and implement discovery phase**

In `open_packet/engine/engine.py`, update `__init__`:

```python
def __init__(
    self,
    command_queue, event_queue, store, operator, node_record,
    connection, node, export_path=None, config=None,
):
    # ... existing assignments ...
    from open_packet.config.config import AppConfig
    self._config = config or AppConfig()
```

Add a `_discover_neighbors` method:

```python
def _discover_neighbors(self) -> tuple[list, list]:
    """Returns (new_neighbors, shorter_path_candidates).
    Calls node.list_linked_nodes(), upserts all, classifies results.
    Must be called while at the node prompt (before BBS)."""
    from open_packet.store.models import NodeHop
    hops = self._node.list_linked_nodes()
    new_neighbors = []
    shorter_path_candidates = []
    existing_in_db = {
        n.callsign: n
        for n in self._store._db.list_nodes()
        if n.interface_id == self._node_record.interface_id and n.id != self._node_record.id
    }
    known_callsigns = {
        h.callsign for h in self._store.get_node_neighbors(self._node_record.id)
    }
    for hop in hops:
        self._store.upsert_node_neighbor(self._node_record.id, hop.callsign, hop.port)
        if hop.callsign not in known_callsigns:
            new_neighbors.append(hop)
        if hop.callsign in existing_in_db:
            existing = existing_in_db[hop.callsign]
            derived_len = len(self._node_record.hop_path) + 1
            if derived_len < len(existing.hop_path):
                derived_path = self._node_record.hop_path + [hop]
                shorter_path_candidates.append((existing, derived_path))
    return new_neighbors, shorter_path_candidates
```

Update `_do_check_mail` to call `_discover_neighbors` before entering BBS, and emit the event in `finally`:

```python
def _do_check_mail(self) -> None:
    node_addr = f"{self._node_record.callsign}-{self._node_record.ssid}"
    self._set_status(ConnectionStatus.CONNECTING)
    self._emit(ConsoleEvent(">", f"Connecting to {node_addr}..."))
    new_neighbors = []
    shorter_path_candidates = []
    try:
        # Determine connection target for path_route
        if (self._node_record.path_strategy == "path_route"
                and self._node_record.hop_path):
            first = self._node_record.hop_path[0]
            from open_packet.ax25.connection import _split_callsign
            call, ssid = _split_callsign(first.callsign)
            self._connection.connect(call, ssid)
        else:
            via = self._node_record.hop_path if self._node_record.path_strategy == "digipeat" else None
            self._connection.connect(
                self._node_record.callsign,
                self._node_record.ssid,
                via_path=via or None,
            )

        self._emit(ConsoleEvent("<", f"Connected to {node_addr}"))
        self._set_status(ConnectionStatus.SYNCING)

        # Discovery phase (at node prompt, before BBS)
        if self._config.nodes.auto_discover:
            new_neighbors, shorter_path_candidates = self._discover_neighbors()

        self._node.connect_node()

        # ... existing Phase 1-4 unchanged ...
```

In the `finally` block, after disconnect, emit the event:

```python
    finally:
        self._connection.disconnect()
        self._emit(ConsoleEvent("<", "Disconnected"))
        self._set_status(ConnectionStatus.DISCONNECTED)
        if new_neighbors or shorter_path_candidates:
            self._emit(NeighborsDiscoveredEvent(
                node_id=self._node_record.id,
                new_neighbors=new_neighbors,
                shorter_path_candidates=shorter_path_candidates,
            ))
```

Import `NeighborsDiscoveredEvent` at top of `engine.py`.

- [ ] **Step 4: Run discovery tests**

```
uv run pytest tests/test_engine/test_engine.py::test_discovery_phase_upserts_neighbors tests/test_engine/test_engine.py::test_discovery_phase_emits_new_neighbor_event tests/test_engine/test_engine.py::test_discovery_phase_skipped_when_disabled -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Update `app.py` to pass `config` to `Engine` and update `_start_engine` to pass `hop_path`/`path_strategy` to `BPQNode`**

In `open_packet/ui/tui/app.py`, update the `Engine(...)` construction in `_start_engine` to pass `config=self.config`.

Update `BPQNode(...)` construction to pass `hop_path` and `path_strategy` from `node_record`:

```python
node = BPQNode(
    connection=connection,
    node_callsign=node_record.callsign,
    node_ssid=node_record.ssid,
    my_callsign=operator.callsign,
    my_ssid=operator.ssid,
    hop_path=node_record.hop_path,
    path_strategy=node_record.path_strategy,
)
```

- [ ] **Step 6: Run full suite**

```
uv run pytest -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add open_packet/engine/engine.py open_packet/ui/tui/app.py tests/test_engine/test_engine.py
git commit -m "feat: engine discovery phase — neighbor upsert, classification, NeighborsDiscoveredEvent"
```

---

## Task 9: Engine auto-forward phase

**Files:**
- Modify: `open_packet/engine/engine.py`
- Test: `tests/test_engine/test_engine.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_engine/test_engine.py`:

```python
def test_auto_forward_syncs_via_neighbors(tmp_path):
    """When auto_forward=True on a node, engine re-connects to each stored neighbor."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    db = Database(f.name); db.initialize()
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="me", is_default=True))
    node_rec = db.insert_node(Node(
        label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
        is_default=True, auto_forward=True,
    ))
    store = Store(db)
    # Pre-seed a neighbor
    store.upsert_node_neighbor(node_rec.id, "W0RELAY-1", port=3)

    connect_calls = []
    class TrackingConnection:
        def connect(self, *a, **kw): connect_calls.append((a, kw))
        def disconnect(self): pass
        def send_frame(self, d): pass
        def receive_frame(self, timeout=5.0): return b""

    mock_node = MockNodeWithNeighbors([])
    cfg = AppConfig(nodes=NodesConfig(auto_discover=False))
    cmd_q, evt_q = queue.Queue(), queue.Queue()
    engine = Engine(
        command_queue=cmd_q, event_queue=evt_q, store=store,
        operator=op, node_record=node_rec,
        connection=TrackingConnection(), node=mock_node, config=cfg,
    )
    engine.start()
    cmd_q.put(CheckMailCommand())
    import time; time.sleep(0.3)
    engine.stop()
    db.close()
    os.unlink(f.name)
    # Should have connected at least twice: primary + auto-forward neighbor
    assert len(connect_calls) >= 2
```

- [ ] **Step 2: Run to confirm failure**

```
uv run pytest tests/test_engine/test_engine.py::test_auto_forward_syncs_via_neighbors -v
```

Expected: FAIL — only one connect call (auto-forward not implemented).

- [ ] **Step 3: Add auto-forward phase to `_do_check_mail` in `engine.py`**

After the `finally` block of the existing sync (so after the primary disconnect), add:

```python
    # Phase 5: Auto-forward via discovered neighbors
    if self._node_record.auto_forward:
        self._do_auto_forward()
```

Add the method:

```python
def _do_auto_forward(self) -> None:
    neighbors = self._store.get_node_neighbors(self._node_record.id)
    for hop in neighbors:
        derived_path = self._node_record.hop_path + [hop]
        try:
            from open_packet.ax25.connection import _split_callsign
            from open_packet.node.bpq import BPQNode
            if self._node_record.path_strategy == "path_route":
                call, ax25_ssid = _split_callsign(derived_path[0].callsign)
                self._connection.connect(call, ax25_ssid)
                temp_node = BPQNode(
                    connection=self._connection,
                    node_callsign=self._node_record.callsign,
                    node_ssid=self._node_record.ssid,
                    my_callsign=self._operator.callsign,
                    my_ssid=self._operator.ssid,
                    hop_path=derived_path[1:],
                    path_strategy="path_route",
                )
            else:  # digipeat
                call, ax25_ssid = _split_callsign(hop.callsign)
                via = self._node_record.hop_path or None
                self._connection.connect(call, ax25_ssid, via_path=via)
                temp_node = BPQNode(
                    connection=self._connection,
                    node_callsign=self._node_record.callsign,
                    node_ssid=self._node_record.ssid,
                    my_callsign=self._operator.callsign,
                    my_ssid=self._operator.ssid,
                    hop_path=[],
                    path_strategy="digipeat",
                )
            self._emit(ConsoleEvent(">", f"Auto-forwarding via {hop.callsign}"))
            temp_node.connect_node()
            self._run_sync_phases(temp_node)
        except Exception as e:
            logger.exception("Auto-forward to %s failed", hop.callsign)
            self._emit(ConsoleEvent("!", f"Auto-forward to {hop.callsign} failed: {e}"))
        finally:
            try:
                self._connection.disconnect()
            except Exception:
                pass
```

Extract the four sync phases from `_do_check_mail` into `_run_sync_phases(node)` to avoid duplication. Move phases 1–4 out of the inline body:

```python
def _run_sync_phases(self, node) -> tuple[int, int, int]:
    """Run the four mail sync phases. Returns (retrieved, sent, bulletins_retrieved).
    Does NOT emit SyncCompleteEvent — caller is responsible for that."""
    retrieved = 0
    headers = node.list_messages()
    # ... (move existing phase 1–4 logic here, replacing self._node with node)
    return retrieved, sent, bulletins_retrieved
```

Update `_do_check_mail` to call `self._run_sync_phases(self._node)` and emit exactly one `SyncCompleteEvent` with the returned counts — same as today.

For the auto-forward phase in `_do_auto_forward`: call `self._run_sync_phases(temp_node)` but do **not** emit `SyncCompleteEvent` for each neighbor — emit only a `ConsoleEvent` summary per neighbor. This keeps the TUI status bar update tied to the primary sync only.

- [ ] **Step 4: Run test**

```
uv run pytest tests/test_engine/test_engine.py::test_auto_forward_syncs_via_neighbors -v
```

Expected: PASS.

- [ ] **Step 5: Run full suite**

```
uv run pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add open_packet/engine/engine.py tests/test_engine/test_engine.py
git commit -m "feat: engine auto-forward phase syncs mail via discovered neighbors"
```

---

## Task 10: Node setup screen — hop path editor, strategy, `auto_forward`

**Files:**
- Modify: `open_packet/ui/tui/screens/setup_node.py`
- Test: `tests/test_ui/test_setup_screens.py`

- [ ] **Step 1: Write failing tests for hop text helpers**

The `_hops_to_text` and `_text_to_hops` helpers will be module-level functions in `setup_node.py` (not methods), so they can be tested without a Textual pilot. Add to `tests/test_ui/test_setup_screens.py`:

```python
from open_packet.ui.tui.screens.setup_node import _hops_to_text, _text_to_hops
from open_packet.store.models import NodeHop

def test_hops_to_text_empty():
    assert _hops_to_text([]) == ""

def test_hops_to_text_with_port():
    assert _hops_to_text([NodeHop("W0RELAY", port=3)]) == "W0RELAY:3"

def test_hops_to_text_no_port():
    assert _hops_to_text([NodeHop("W0RELAY")]) == "W0RELAY"

def test_hops_to_text_multiple():
    result = _hops_to_text([NodeHop("W0R1", port=1), NodeHop("W0R2")])
    assert result == "W0R1:1\nW0R2"

def test_text_to_hops_empty():
    assert _text_to_hops("") == []

def test_text_to_hops_with_port():
    hops = _text_to_hops("W0RELAY:3")
    assert hops[0].callsign == "W0RELAY"
    assert hops[0].port == 3

def test_text_to_hops_no_port():
    hops = _text_to_hops("W0RELAY")
    assert hops[0].callsign == "W0RELAY"
    assert hops[0].port is None

def test_text_to_hops_invalid_port_falls_back():
    hops = _text_to_hops("W0RELAY:notanint")
    assert hops[0].callsign == "W0RELAY:notanint"
    assert hops[0].port is None
```

Run:
```
uv run pytest tests/test_ui/test_setup_screens.py::test_hops_to_text_empty tests/test_ui/test_setup_screens.py::test_text_to_hops_with_port -v
```

Expected: `ImportError` — functions don't exist yet.

- [ ] **Step 2: Update `NodeSetupScreen` to persist and load new fields**

In `setup_node.py`, the `on_button_pressed` save path currently constructs a `Node` without `hop_path`, `path_strategy`, or `auto_forward`. Update it to include those three fields from new UI widgets.

Add to the `Vertical` in `compose()`, after the existing `default_switch`:

```python
yield Label("Path Strategy:", classes="section")
yield Select(
    [("Path Route", "path_route"), ("Digipeat", "digipeat")],
    value=n.path_strategy if n else "path_route",
    id="strategy_select",
)

yield Label("Hop Path (one per line, format: CALLSIGN or CALLSIGN:PORT):",
            classes="section")
yield TextArea(
    self._hops_to_text(n.hop_path if n else []),
    id="hop_path_area",
)
yield Label("", id="hop_path_error", classes="error")

yield Label("Auto Forward:", classes="section")
yield Switch(value=n.auto_forward if n else False, id="auto_forward_switch")
```

Add a module-level `TextArea` import and helper methods:

```python
from textual.widgets import Button, Input, Label, Switch, Select, TextArea

def _hops_to_text(hops) -> str:
    lines = []
    for h in hops:
        lines.append(f"{h.callsign}:{h.port}" if h.port is not None else h.callsign)
    return "\n".join(lines)

def _text_to_hops(text: str) -> list:
    from open_packet.store.models import NodeHop
    hops = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            parts = line.rsplit(":", 1)
            try:
                hops.append(NodeHop(callsign=parts[0].strip(), port=int(parts[1])))
            except ValueError:
                hops.append(NodeHop(callsign=line))
        else:
            hops.append(NodeHop(callsign=line))
    return hops
```

Update the save path in `on_button_pressed`:

```python
hop_path = _text_to_hops(self.query_one("#hop_path_area", TextArea).text)
path_strategy = str(self.query_one("#strategy_select", Select).value)
auto_forward = self.query_one("#auto_forward_switch", Switch).value

self.dismiss(Node(
    label=label,
    callsign=callsign,
    ssid=ssid,
    node_type="bpq",
    is_default=is_default,
    interface_id=interface_id,
    id=self._node.id if self._node else None,
    hop_path=hop_path,
    path_strategy=path_strategy,
    auto_forward=auto_forward,
))
```

- [ ] **Step 3: Run full suite**

```
uv run pytest -q
```

Expected: all pass. (The new widgets are additive; existing tests should still work.)

- [ ] **Step 4: Commit**

```bash
git add open_packet/ui/tui/screens/setup_node.py
git commit -m "feat: node setup screen adds hop path editor, strategy selector, auto_forward toggle"
```

---

## Task 11: TUI `NeighborsDiscoveredEvent` handling and prompt queue

**Files:**
- Create: `open_packet/ui/tui/screens/shorter_path_confirm.py`
- Modify: `open_packet/ui/tui/app.py`

- [ ] **Step 1: Write failing tests for prompt queue logic**

Add to `tests/test_engine/test_engine.py` (pure unit test, no Textual pilot needed):

```python
def test_queue_neighbor_prompts_builds_correct_entries():
    """_queue_neighbor_prompts builds one 'new' entry and one 'shorter' entry."""
    from open_packet.engine.events import NeighborsDiscoveredEvent
    from open_packet.store.models import NodeHop, Node

    existing = Node(label="BBS2", callsign="W0DIST", ssid=0, node_type="bpq",
                    hop_path=[NodeHop("W0LONG1"), NodeHop("W0LONG2"), NodeHop("W0DIST")],
                    id=99)
    new_hop = NodeHop("W0NEW-1", port=2)
    shorter_hop = NodeHop("W0DIST", port=1)
    evt = NeighborsDiscoveredEvent(
        node_id=1,
        new_neighbors=[new_hop],
        shorter_path_candidates=[(existing, [shorter_hop])],
    )
    # Build the prompts list manually using the same logic as _queue_neighbor_prompts
    prompts = []
    for hop in evt.new_neighbors:
        prompts.append(("new", hop, None))
    for existing_node, new_path in evt.shorter_path_candidates:
        prompts.append(("shorter", None, (existing_node, new_path)))

    assert len(prompts) == 2
    assert prompts[0][0] == "new"
    assert prompts[0][1].callsign == "W0NEW-1"
    assert prompts[1][0] == "shorter"
    assert prompts[1][1] is None  # must be None, not an unbound variable
    assert prompts[1][2][0].callsign == "W0DIST"
```

Run:
```
uv run pytest tests/test_engine/test_engine.py::test_queue_neighbor_prompts_builds_correct_entries -v
```

Expected: PASS immediately (this tests the logic pattern, not the method itself). If it fails, the event dataclass has a problem.

- [ ] **Step 2: Create `ShorterPathConfirmScreen`**

Create `open_packet/ui/tui/screens/shorter_path_confirm.py`:

```python
from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from textual.containers import Vertical, Horizontal


class ShorterPathConfirmScreen(ModalScreen):
    DEFAULT_CSS = """
    ShorterPathConfirmScreen { align: center middle; }
    ShorterPathConfirmScreen Vertical {
        width: 60; height: auto; border: solid $primary;
        background: $surface; padding: 1 2;
    }
    """

    def __init__(self, node_label: str, current_len: int,
                 new_path_summary: str, **kwargs):
        super().__init__(**kwargs)
        self._node_label = node_label
        self._current_len = current_len
        self._new_path_summary = new_path_summary

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"Shorter path discovered for [b]{self._node_label}[/b]")
            yield Label(f"Current path: {self._current_len} hop(s)")
            yield Label(f"Shorter path: {self._new_path_summary}")
            yield Label("Update to shorter path?")
            with Horizontal():
                yield Button("Update", variant="primary", id="update_btn")
                yield Button("Skip", id="skip_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "update_btn")

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)
```

- [ ] **Step 2: Add `NeighborsDiscoveredEvent` handling to `app.py`**

In `open_packet/ui/tui/app.py`, import the new event and screen:

```python
from open_packet.engine.events import (
    ConnectionStatusEvent, MessageReceivedEvent, SyncCompleteEvent,
    ErrorEvent, ConnectionStatus, MessageQueuedEvent, ConsoleEvent,
    NeighborsDiscoveredEvent,
)
from open_packet.ui.tui.screens.shorter_path_confirm import ShorterPathConfirmScreen
```

Add a `_pending_neighbor_prompts: list` instance variable in `__init__`:

```python
self._pending_neighbor_prompts: list = []
```

Add handling in `_handle_event`:

```python
elif isinstance(event, NeighborsDiscoveredEvent):
    self._queue_neighbor_prompts(event)
```

Add the queuing and prompt-chain methods:

```python
def _queue_neighbor_prompts(self, event: NeighborsDiscoveredEvent) -> None:
    """Build a sequential queue of prompts and start showing them."""
    if not self._store or not self._active_node:
        return
    prompts = []
    for hop in event.new_neighbors:
        prompts.append(("new", hop, None))
    for existing_node, new_path in event.shorter_path_candidates:
        prompts.append(("shorter", None, (existing_node, new_path)))
    self._pending_neighbor_prompts = prompts
    self._show_next_neighbor_prompt()

def _show_next_neighbor_prompt(self) -> None:
    if not self._pending_neighbor_prompts:
        return
    kind, hop, extra = self._pending_neighbor_prompts.pop(0)
    if kind == "new":
        from open_packet.ui.tui.screens.setup_node import NodeSetupScreen
        node_rec = self._active_node
        pre_hop_path = list(node_rec.hop_path) + [hop]
        # Build a pre-filled Node stub for the setup screen
        from open_packet.store.models import Node
        stub = Node(
            label=hop.callsign,
            callsign=hop.callsign,
            ssid=0,
            node_type="bpq",
            hop_path=pre_hop_path,
            path_strategy=node_rec.path_strategy,
            interface_id=node_rec.interface_id,
        )
        self.push_screen(
            NodeSetupScreen(
                node=stub,
                interfaces=self._db.list_interfaces() if self._db else [],
                db=self._db,
            ),
            callback=self._on_new_neighbor_result,
        )
    else:
        existing_node, new_path = extra
        summary = " → ".join(
            f"{h.callsign}:{h.port}" if h.port else h.callsign for h in new_path
        )
        self.push_screen(
            ShorterPathConfirmScreen(
                node_label=existing_node.label,
                current_len=len(existing_node.hop_path),
                new_path_summary=summary,
            ),
            callback=lambda accepted, n=existing_node, p=new_path:
                self._on_shorter_path_result(accepted, n, p),
        )

def _on_new_neighbor_result(self, result) -> None:
    if result is not None and self._db:
        self._save_node(result)
    self._show_next_neighbor_prompt()

def _on_shorter_path_result(self, accepted: bool, node, new_path) -> None:
    if accepted and self._db:
        node.hop_path = new_path
        self._db.update_node(node)
    self._show_next_neighbor_prompt()
```

- [ ] **Step 3: Run full suite**

```
uv run pytest -q
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add open_packet/ui/tui/screens/shorter_path_confirm.py open_packet/ui/tui/app.py
git commit -m "feat: TUI neighbor prompt queue for new nodes and shorter-path candidates"
```

---

## Task 12: Final integration check

- [ ] **Step 1: Run full test suite**

```
uv run pytest -v
```

Expected: all 200+ tests pass, no regressions.

- [ ] **Step 2: Verify `test.yaml` config still works**

```
uv run open-packet test.yaml
```

Confirm the app launches, the node setup screen shows the new hop path / strategy / auto_forward fields, and existing functionality (inbox, send, bulletins) is unaffected.

- [ ] **Step 3: Commit any last cleanups and tag**

```bash
git add -p   # review any stray changes
git commit -m "feat: multi-hop connections — complete implementation"
```
