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

Both `hop_path` and `path_strategy` are persisted via two new columns on the `nodes` table (schema migration). `hop_path` is stored as a JSON array; `auto_forward` as an INTEGER (0/1).

### `NodeHop` dataclass (new, `store/models.py`)

```python
@dataclass
class NodeHop:
    callsign: str
    port: int | None = None
```

Serialized to/from JSON for the `hop_path` column. `port` is the BPQ radio port number; `None` means use the node's default port.

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

Upserted on each discovery pass: insert on first sight, update `last_seen` on repeat. Enables path-length comparison for existing nodes.

### Global config — new `nodes` section

```yaml
nodes:
  auto_discover: true
```

Added to `AppConfig` / `config.yaml`. When `false`, the neighbor discovery phase is skipped globally on every sync. Default is `true`.

---

## Protocol Layer

### `NodeHop` — BPQ `C` command format

| Condition | Command sent |
|---|---|
| `port` is set | `C <port> <callsign>\r` |
| `port` is `None` | `C <callsign>\r` |

### `BPQNode.connect_node()` — Path Route strategy

Before issuing `BBS`, iterate `hop_path`:

1. Send the `C` command for the current hop
2. Call `_recv_until_prompt()` — wait for node prompt ending in `>`
3. On timeout or unexpected response, raise `NodeError`

After all hops are traversed, send `BBS` and complete the existing login sequence.

### New `BPQNode.list_linked_nodes() -> list[NodeHop]`

Called at the node prompt before entering BBS (only when `auto_discover` is enabled):

1. Send `NODES\r`
2. Read until prompt
3. Parse output into a list of `NodeHop(callsign, port)` pairs
4. Return the list — does not write to DB

### `AX25Connection.connect()` — Digipeat strategy

Gains an optional `via_path: list[NodeHop]` parameter. When provided, encodes the hop callsigns as VIA addresses in the SABM frame. BPQ port numbers in each `NodeHop` are ignored for this strategy — VIA routing is purely callsign-based at the AX.25 layer.

Direct connections (empty `hop_path`) are unaffected.

---

## Engine

### Discovery phase (new, runs before Phase 1 of existing sync)

Conditional on `config.nodes.auto_discover`:

1. Connect to node and traverse hop path (per strategy)
2. At node prompt, call `node.list_linked_nodes()`
3. Upsert results into `node_neighbors`
4. Classify results into two buckets:
   - **New neighbors** — callsigns not previously in `node_neighbors` for this node
   - **Shorter-path candidates** — callsigns that already exist as `Node` records in the DB where `len(primary_node.hop_path) + 1 < len(existing_node.hop_path)`
5. Continue into BBS (`BBS` command) and existing sync phases

### End-of-cycle event

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

1. Load `node_neighbors` for this node from DB
2. For each neighbor, build a derived hop path: `primary_node.hop_path + [neighbor_hop]`
3. Establish a new connection (same interface) with this derived path
4. Run the existing four sync phases (retrieve messages, send outbox, post bulletins, retrieve bulletins)
5. Disconnect

---

## TUI

### Node setup screen — new fields

- **Hop path editor**: ordered list widget; each row shows `[port] callsign` (port blank if not set). Rows can be added, removed, and reordered.
- **Strategy selector**: radio buttons — `Path Route` / `Digipeat`
- **Auto Forward**: checkbox (per-node)

Auto Forward is only relevant when `auto_discover` is globally enabled; the UI may grey it out otherwise.

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

- Unit tests for `BPQNode.connect_node()` with a mock connection verifying correct `C` command sequence for single and multi-hop paths, with and without port numbers
- Unit tests for `BPQNode.list_linked_nodes()` parsing various `NODES` output formats
- Unit tests for `AX25Connection.connect()` verifying VIA field encoding when `via_path` is provided
- Unit tests for `Store` upsert behavior on `node_neighbors` (insert new, update `last_seen` on repeat)
- Unit tests for shorter-path comparison logic in the engine
- Integration test for the end-of-cycle event emission with both new and shorter-path buckets populated
