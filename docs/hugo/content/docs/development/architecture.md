---
title: "Architecture"
description: "Codebase layers and design principles"
weight: 1
---

# Architecture

open-packet is structured in layers, each communicating only with its immediate neighbours via well-defined interfaces.

```
Transport (tcp.py / serial.py)   — raw byte I/O
  └─ Link / KISSLink (kiss.py)   — KISS framing; implements ConnectionBase
       └─ AX25Connection          — AX.25 v2.2 state machine; implements ConnectionBase
            └─ BPQNode            — BBS protocol (L/R/S/K commands); implements NodeBase
                 └─ Engine        — command/event loop running in a daemon thread
                      ├─ Store    — SQLite message persistence
                      └─ TUI      — Textual app, polls Engine event queue every 100ms
```

## Transport Layer (`transport/`)

Provides raw byte I/O over TCP (`tcp.py`) or serial (`serial.py`). Each transport implements a simple interface for reading and writing bytes.

## Link Layer (`link/`)

`KISSLink` wraps a transport and implements KISS framing — the standard protocol for connecting a TNC to a host computer. It implements `ConnectionBase`, the common interface used by higher layers.

## AX.25 Layer (`ax25/`)

`AX25Connection` implements the AX.25 v2.2 data-link state machine:
- SABM/UA connect/disconnect handshake
- I-frame data transfer with Go-Back-N windowing
- T1 (retransmission) and T3 (keep-alive) timers
- Automatic retransmission on timeout

## Node Layer (`node/`)

`BPQNode` sits on top of `AX25Connection` and speaks the BPQ32 BBS text protocol:
- `L` — list messages
- `R` — read message
- `S` — send message
- `K` — kill (delete) message

`connect_node()` handles the BBS handshake: sends `BBS\r`, waits for a prompt, and responds to name prompts with the operator callsign.

## Engine (`engine/`)

The `Engine` runs in a background daemon thread. It owns the node connection and orchestrates sync operations.

**Communication with the TUI:**
- TUI → Engine: `Command` objects via `queue.Queue`
- Engine → TUI: `Event` objects via a second `queue.Queue`, polled every 100 ms

### Commands (`commands.py`)

| Command | Description |
|---------|-------------|
| `ConnectCommand` | Establish connection to the BBS |
| `DisconnectCommand` | Disconnect from the BBS |
| `CheckMailCommand` | Run a full send/receive sync |
| `SendMessageCommand` | Queue a personal message for sending |
| `DeleteMessageCommand` | Delete a message from BBS and local DB |
| `PostBulletinCommand` | Post a bulletin to the BBS |

### Events (`events.py`)

| Event | Description |
|-------|-------------|
| `ConnectionStatusEvent` | Connection state changed (disconnected/connecting/connected/syncing/error) |
| `MessageReceivedEvent` | A new message was received during sync |
| `SyncCompleteEvent` | A send/receive cycle finished |
| `ErrorEvent` | An error occurred |
| `ConsoleEvent` | A raw AX.25 frame for the console panel |
| `NeighborsDiscoveredEvent` | Neighbor nodes discovered via network topology |

### Adding a New Capability

1. Add a `Command` dataclass to `commands.py`
2. Add an `Event` dataclass to `events.py`
3. Add a `_do_<command>()` handler in `Engine`
4. Add an `_handle_event()` branch in `OpenPacketApp` (`ui/tui/app.py`)

## Store (`store/`)

SQLite-backed message persistence.

- `models.py` — plain dataclasses: `Operator`, `Node`, `Interface`, `Message`, `Bulletin`, `BBSFile`
- `database.py` — raw SQLite DDL, schema migrations, low-level insert/query helpers
- `store.py` — higher-level query methods used by the engine and TUI

### Schema Migrations

Migrations use `ALTER TABLE ... ADD COLUMN` in `Database.initialize()` with `except sqlite3.OperationalError: pass`. Always use `self._conn.execute()` for migrations — never `executescript()` (which issues an implicit COMMIT).

### Message State Matrix

| Type | `queued` | `sent` |
|------|----------|--------|
| Received from BBS | 0 | 0 |
| Composed, awaiting send | 1 | 0 |
| Composed, transmitted | 1 | 1 |

### Bulletin Body Sentinel

`Bulletin.body` is `Optional[str]`:
- `None` — header-only, body not yet retrieved
- `"\x00"` (NUL byte) — stored in SQLite to represent None (since the column is `NOT NULL`)
- A non-empty string — the retrieved body

Do not replace `"\x00"` with `""` — empty string is a valid retrieved body.

## TUI (`ui/tui/`)

Built with [Textual](https://textual.textualize.io/).

| Module | Description |
|--------|-------------|
| `app.py` | Top-level `App`; owns engine, store, and active operator |
| `screens/main.py` | Primary layout; key bindings |
| `widgets/folder_tree.py` | Uses `node.data` (not label string) for folder routing |
| `widgets/console_panel.py` | Receives `ConsoleEvent` objects; displays frame traffic |

The TUI calls `self._store` directly for lightweight read operations that don't require connectivity (e.g. `mark_message_read`). Only operations needing a BBS connection go through the engine command queue.
