# Multi-Hop Connections Design

**Date:** 2026-03-25
**Status:** Approved

## Overview

Add support for multi-hop connections through intermediate BPQ nodes. A node can have an ordered list of callsign+port hops and a traversal strategy. During sync the engine optionally discovers each node's neighbors, stores them, and at the end of the cycle prompts the user to add new nodes or accept shorter paths for existing ones. Nodes with `auto_forward` enabled also sync mail via their discovered neighbors.

---

## Data Model

### `Node` model — new fields

| Field | Type | Default | Description |
|---|---|---|---|
| `hop_path` | `list[NodeHop]` | `[]` | Ordered intermediate hops to traverse before reaching this node |
| `path_strategy` | `str` | `"path_route"` | `"path_route"` (BPQ `C` commands) or `"digipeat"` (AX.25 VIA) |
| `auto_forward` | `bool` | `False` | If True, engine also syncs via this node's discovered neighbors |

`hop_path`, `path_strategy`, and `auto_forward` are persisted via new columns on the `nodes` table (schema migration). `hop_path` is stored as a JSON array of `{callsign, port}` objects; `auto_forward` as an INTEGER (0/1).

### `NodeHop` dataclass (new, `store/models.py`)

```python
@dataclass
class NodeHop:
    callsign: str
    port: int | None = None
```

Serialized to/from JSON for the `hop_path` column. `port` is the BPQ radio port number at the preceding node; `None` means use that node's default port.

### `node_neighbors` table (new)

```sql
CREATE TABLE node_neighbors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id     INTEGER NOT NULL REFERENCES nodes(id),
    callsign    TEXT NOT NULL,
    port        INTEGER,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    UNIQUE(node_id, callsign)
)
```

Upserted on each discovery pass: insert on first sight, update `last_seen` on repeat. Used for path-length comparison against existing `Node` records.

### Global config — new `nodes` section

A new `NodesConfig` dataclass is added to `open_packet/config/config.py`:

```python
@dataclass
class NodesConfig:
    auto_discover: bool = True
```

`AppConfig` gains a `nodes: NodesConfig` field. `load_config()` reads the optional `nodes:` key from `config.yaml` and constructs `NodesConfig` from it (defaults apply when the key is absent). Example `config.yaml`:

```yaml
nodes:
  auto_discover: true   # omit or set false to disable neighbor discovery globally
```

When `auto_discover` is `false`, the neighbor discovery phase is skipped on every sync for all nodes. Default is `true`.

---

## Protocol Layer

### Connection target for Path Route

For both `path_route` and `digipeat` strategies, `ConnectionBase.connect()` is called with the **final destination node's callsign and SSID** — the same as today. The two strategies diverge in how the path is handled after (or instead of) that call:

- **`path_route`**: `ConnectionBase.connect()` is called against the first hop's callsign (or the destination if `hop_path` is empty). `BPQNode.connect_node()` then issues `C` commands to traverse each remaining hop before issuing `BBS`. The engine is responsible for passing the first hop's callsign to `connection.connect()` when `hop_path` is non-empty.
- **`digipeat`**: `ConnectionBase.connect()` is called against the final destination, and the VIA addresses (derived from `hop_path`) are encoded into the SABM frame at the AX.25 layer. No application-layer `C` commands are used.

### `NodeHop` — BPQ `C` command format (Path Route only)

| Condition | Command sent |
|---|---|
| `port` is set | `C <port> <callsign>\r` |
| `port` is `None` | `C <callsign>\r` |

### `BPQNode.connect_node()` — Path Route strategy

`BPQNode` accepts optional `hop_path: list[NodeHop]` and `path_strategy: str` parameters at construction. `connect_node()` issues `C` commands only when `path_strategy == "path_route"` **and** `hop_path` is non-empty. For the `"digipeat"` strategy, no `C` commands are issued regardless of `hop_path` content — the engine passes `hop_path=[]` to `BPQNode` for digipeat nodes, since the AX.25 layer handles routing entirely.

When `path_strategy == "path_route"` and `hop_path` is non-empty, `connect_node()` traverses the remaining hops (starting from index 1, since the link layer already connected to `hop_path[0]`) before issuing `BBS`:

1. For each hop in `hop_path[1:]`: send the `C` command and call `_recv_until_prompt()`
2. On timeout or unexpected response: raise `NodeError` immediately. No cleanup of intermediate hops is performed — dropping the underlying link-layer connection is sufficient; intermediate BPQ nodes will time out their sessions independently.
3. After all hops: send `BBS` and complete the existing login sequence.

When `hop_path` is empty, `connect_node()` behaves exactly as today (sends `BBS` immediately).

### New `BPQNode.list_linked_nodes() -> list[NodeHop]`

Called at the node prompt before entering BBS (only when `auto_discover` is enabled). Issues the `NODES` command, which BPQ32 responds to with a table of known/linked nodes.

**Example `NODES` output:**

```
Nodes
Callsign  Port  Quality  Hops
W0RELAY-1    3      200     1
W0DIST       1      150     2
:
```

**Parsing rules:**

- Skip lines that do not match the pattern: one or more non-space tokens as callsign, followed by integer fields
- Extract `callsign` (field 0) and `port` (field 1, integer). If field 1 is not a valid integer, set `port = None`
- Stop on the prompt line (ends with `>`)
- Return a `list[NodeHop]`; return `[]` if the command produces no parseable rows

The exact column order may vary across BPQ versions. The parser should be tolerant of whitespace and extra columns.

**Port field caveat:** The `Port` column in BPQ `NODES` output reflects the port on which the neighbor was *heard*, which may differ from the correct outbound port for a `C` command to that neighbor. The discovered port is used as a pre-filled suggestion in the new-neighbor TUI prompt, but the prompt labels it "Suggested port (verify before saving)" and the user can edit it before confirming.

### `ConnectionBase` and `AX25Connection` — Digipeat strategy

`ConnectionBase.connect()` gains an optional keyword parameter:

```python
def connect(self, callsign: str, ssid: int, via_path: list[NodeHop] | None = None) -> None: ...
```

`TelnetLink.connect()` accepts but ignores `via_path` (telnet has no VIA concept). `AX25Connection.connect()` uses it: when `via_path` is non-empty, each hop's callsign is encoded as a VIA address in the SABM frame. BPQ port numbers in each `NodeHop` are ignored for this strategy.

Direct connections (`via_path=None` or `[]`) are unaffected on all implementations.

---

## Engine

### Discovery phase (new, runs before Phase 1 of existing sync)

Conditional on `config.nodes.auto_discover`:

1. Connect using strategy-appropriate call (see Protocol Layer above)
2. At node prompt, call `node.list_linked_nodes()`
3. Upsert results into `node_neighbors`
4. Classify results into two buckets:
   - **New neighbors** — callsigns not previously in `node_neighbors` for this node
   - **Shorter-path candidates** — callsigns that already exist as `Node` records in the DB **on the same `interface_id`** as the primary node, where `len(primary_node.hop_path) + 1 < len(existing_node.hop_path)`. Cross-interface comparisons are skipped (path length is not meaningful across different RF links or transports).
5. Continue into BBS (`BBS` command) and existing sync phases

### End-of-cycle event

`NeighborsDiscoveredEvent` is added to the `Event` union in `events.py`:

```python
Event = ConnectionStatusEvent | MessageReceivedEvent | SyncCompleteEvent | ErrorEvent | MessageQueuedEvent | ConsoleEvent | NeighborsDiscoveredEvent
```

After disconnect (in the `finally` block alongside the existing disconnect logic), if either bucket is non-empty, emit:

```python
NeighborsDiscoveredEvent(
    node_id: int,
    new_neighbors: list[NodeHop],
    shorter_path_candidates: list[tuple[Node, list[NodeHop]]],
)
```

The engine does not block waiting for user decisions. The TUI handles all prompting asynchronously.

### Auto-forward phase (new Phase 5, conditional on `node.auto_forward`)

After the existing four sync phases and disconnect, if `node.auto_forward` is `True`:

1. Load `node_neighbors` for this node from the store
2. For each neighbor, build a derived hop path: `derived = primary_node.hop_path + [neighbor_hop]`
3. Re-use `self._connection`. Connect using the primary node's `path_strategy`:
   - **`path_route`**: call `self._connection.connect(derived[0].callsign, derived[0].ssid_or_0)`. Construct a temporary `BPQNode` with `hop_path=derived[1:]` and `path_strategy="path_route"`, so `connect_node()` traverses the remaining hops with `C` commands.
   - **`digipeat`**: call `self._connection.connect(neighbor_hop.callsign, 0, via_path=primary_node.hop_path)`. Construct a temporary `BPQNode` with `hop_path=[]` and `path_strategy="digipeat"`.
4. Run the existing four sync phases against that temporary node
5. Call `self._connection.disconnect()` after each neighbor

This reuses the existing stateful `ConnectionBase` instance (which supports reconnect after disconnect, as demonstrated by the existing `_do_check_mail` flow).

---

## TUI

### Node setup screen — new fields

- **Hop path editor**: ordered list widget; each row shows `[port] callsign` (port blank if not set). Rows can be added, removed, and reordered.
- **Strategy selector**: radio buttons — `Path Route` / `Digipeat`
- **Auto Forward**: checkbox (per-node)

Auto Forward is only relevant when `auto_discover` is globally enabled; the UI greys it out when `config.nodes.auto_discover` is `False`.

### End-of-cycle neighbor prompt flow

When `NeighborsDiscoveredEvent` arrives in `_poll_events()`:

1. The app builds a sequential prompt queue — one entry per new neighbor, one entry per shorter-path candidate.
2. Prompts are shown as modal screens, one at a time (dismiss triggers the next).

**New neighbor prompt** — a pre-filled node setup screen:
- Callsign pre-populated
- `hop_path` pre-set to `primary_node.hop_path + [neighbor_hop]`
- Strategy and other fields editable
- User confirms to add the node to DB, or skips

**Shorter path prompt** — a confirmation dialog:
- Shows the existing node name and current path length vs. discovered shorter path
- "Update" accepts the new `hop_path`; "Skip" leaves the node unchanged

If the user dismisses the app mid-queue (e.g. quits), remaining prompts are dropped — discovered data is already stored in `node_neighbors` for the next session.

---

## Testing

- Unit tests for `BPQNode.connect_node()` with a mock connection verifying correct `C` command sequence for single and multi-hop paths, with and without port numbers, using `hop_path[1:]` traversal
- Unit tests for `BPQNode.list_linked_nodes()` parsing sample `NODES` output: standard format, missing port field, empty output
- Unit tests for `AX25Connection.connect()` verifying VIA field encoding when `via_path` is provided
- Unit tests for `Store` upsert behavior on `node_neighbors` (insert new, update `last_seen` on repeat)
- Unit tests for shorter-path comparison logic: same interface matches, cross-interface skipped, equal-length path skipped
- Integration test for end-of-cycle event emission with both new and shorter-path buckets populated
- Unit test verifying `NeighborsDiscoveredEvent` is present in the `Event` union
