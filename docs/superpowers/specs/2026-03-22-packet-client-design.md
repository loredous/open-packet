# open-packet Design Specification

**Date:** 2026-03-22
**Status:** Approved
**Project:** open-packet — Amateur Radio Packet Messaging Client

---

## Overview

open-packet is an open-source Python client for managing amateur radio packet messaging. It functions similarly to an email client but operates over AX.25 packet radio. The initial release targets Linux and provides a terminal user interface (TUI), with a modular architecture designed to support future web, API, and GUI interfaces.

The project targets the broader amateur radio community. The TUI is aimed at experienced CLI users; the modular design accommodates future interfaces for less technical operators.

---

## Architecture

### Design Principle

A **Core Engine + Plugin Interfaces** approach. The engine runs in a background thread and orchestrates all packet radio operations. Each swappable layer is defined by an abstract base class (ABC). The TUI communicates with the engine via thread-safe command and event queues — the same seam that future web and GUI interfaces will use.

### Module Structure

```
open_packet/
├── transport/        # Byte pipes: SerialTransport, TCPTransport (TransportBase ABC)
├── link/             # Link layer: KISSLink (uses TransportBase + AX.25 framing)
│                     # Future: VARALink, TelnetLink, DMRLink
├── ax25/             # AX.25 frame encode/decode (used internally by KISSLink)
├── session/          # ConnectionBase ABC — connected channel abstraction
├── node/             # BBS protocol drivers (NodeBase ABC) — BPQ first
├── store/            # SQLite message store + flat-file export
├── config/           # YAML config loader + Pydantic validation
├── engine/           # Core engine: orchestrates all layers, owns in-memory state
└── ui/               # UIBase ABC + Textual TUI implementation
```

### Layer Stack (PoC)

```
NodeBase → ConnectionBase (KISSLink → TransportBase → serial/TCP) → AX.25 frames
```

Future link layers slot in at the `ConnectionBase` level:

```
NodeBase → ConnectionBase (TelnetLink → TCP socket)   # no AX.25
NodeBase → ConnectionBase (VARALink → VARA modem)     # future
```

---

## Module Contracts

### TransportBase (transport/)

Abstracts the physical byte pipe.

- `connect()` / `disconnect()`
- `send_bytes(data: bytes)`
- `receive_bytes() -> bytes`

Implementations: `SerialTransport`, `TCPTransport`

### ConnectionBase (session/)

Abstracts a connected, framed channel to a remote node. The node layer talks only to `ConnectionBase` and has no knowledge of AX.25.

- `connect(callsign: str, ssid: int)`
- `disconnect()`
- `send_frame(data: bytes)`
- `receive_frame() -> bytes`

Implementations: `KISSLink` (PoC), `TelnetLink`, `VARALink` (roadmap)

### NodeBase (node/)

Abstracts the BBS protocol. Receives a `ConnectionBase` instance.

- `connect_node(callsign: str, ssid: int)`
- `list_messages() -> list[MessageHeader]`
- `read_message(id: str) -> Message`
- `send_message(msg: Message)`
- `delete_message(id: str)`
- `list_bulletins(category: str) -> list[MessageHeader]`
- `read_bulletin(id: str) -> Message`

Implementations: `BPQNode` (PoC)

### UIBase (ui/)

Abstracts the user interface. Communicates with the engine via queues.

- `send_command(cmd: Command)`
- `on_event(event: Event)`

Implementations: `TextualTUI` (PoC), REST API + Web UI (roadmap)

### Engine Command/Event Types

**Commands (UI → Engine):**
- `ConnectCommand`, `DisconnectCommand`
- `CheckMailCommand`
- `SendMessageCommand`
- `DeleteMessageCommand`

**Events (Engine → UI):**
- `ConnectionStatusEvent`
- `MessageReceivedEvent`
- `SyncCompleteEvent`
- `ErrorEvent`

---

## Data Model

### SQLite Database

Default path: `~/.local/share/open-packet/messages.db`

**`operators`**
```
id, callsign, ssid, label, is_default, created_at
```

**`messages`** — personal messages
```
id, operator_id, bbs_id, from_call, to_call, subject, body,
timestamp, read, sent, deleted, synced_at
```

**`bulletins`** — read-only broadcast messages
```
id, operator_id, bbs_id, category, from_call, subject, body,
timestamp, read, synced_at
```

- `operator_id` is a foreign key to `operators`, keeping each operator's mail separate.
- Sync state (last sync time, message counts, connection status) is held as in-memory state on the engine instance and surfaced to the UI via events. No `sync_log` table at PoC.

### Flat-File Export

Optional export to a configurable directory, organized as:

```
export/
├── inbox/KD9ABC/2026-03-22-001-subject.txt
├── sent/
└── bulletins/WX/
```

---

## Configuration

### Split: YAML (machine config) + SQLite (operator config)

Operator identity (callsign, SSIDs) lives in the SQLite `operators` table to support future multi-operator use via a web UI. All other configuration is in YAML.

### YAML Config

Default path: `~/.config/open-packet/config.yaml`

```yaml
connection:
  type: kiss_tcp          # kiss_tcp | kiss_serial
  host: localhost         # TCP only
  port: 8001              # TCP only
  # device: /dev/ttyUSB0  # serial only
  # baud: 9600            # serial only

node:
  type: bpq
  callsign: W0BPQ-1

store:
  db_path: ~/.local/share/open-packet/messages.db
  export_path: ~/.local/share/open-packet/export

ui:
  console_visible: false
  console_buffer: 500     # ring buffer size (lines)
  console_log: ~/.local/share/open-packet/console.log  # omit to disable
```

Config is loaded at startup and validated with Pydantic. Invalid config surfaces a clear error to stderr and exits before the engine starts.

---

## TUI Layout

Built with **Textual**. Three-panel mail client layout with a collapsible console panel.

```
┌─────────────────────────────────────────────────────┐
│ open-packet  KD9ABC-1  ●  Connected to W0BPQ-1      │  ← status bar
├──────────────┬──────────────────────────────────────┤
│ FOLDERS      │ SUBJECT          FROM      DATE       │
│              ├──────────────────────────────────────┤
│ ▶ Inbox (3)  │                                      │
│   Sent       │   (message body pane)                │
│   Bulletins  │                                      │
│     WX       │                                      │
│     NTS      │                                      │
├──────────────┴──────────────────────────────────────┤
│ CONSOLE                                        [hide]│
│ >> KD9ABC-1>W0BPQ-1: [SABM]                         │
│ << W0BPQ-1>KD9ABC-1: [UA]                           │
│ _                                                    │
├─────────────────────────────────────────────────────┤
│ [C]heck Mail  [N]ew  [D]elete  [R]eply  [`]Console  │
└─────────────────────────────────────────────────────┘
```

**Panels:**
- **Left** — folder tree: Inbox, Sent, Bulletins (expandable by category)
- **Top-right** — message list for selected folder
- **Bottom-right** — message body for selected message
- **Header** — callsign, SSID, connection status, last sync time (from engine in-memory state)
- **Console** — collapsible; shows timestamped AX.25 frame traffic (`>>` outbound, `<<` inbound); ring buffer of configurable size; optionally logged to file; input line reserved for future manual command mode
- **Footer** — context-sensitive key bindings

A compose screen overlays the full terminal for new messages and replies.

---

## Error Handling

- **Connection failures** (TNC unreachable, serial port missing) — engine emits `ErrorEvent`; TUI displays in status bar and console. No auto-retry at PoC.
- **Session failures** (AX.25 disconnect mid-session, node timeout) — engine transitions to disconnected state, emits `ConnectionStatusEvent` + `ErrorEvent`. Partial sync is preserved.
- **BBS protocol errors** (unexpected node response, parse failure) — `NodeBase` raises a typed exception; engine catches, emits `ErrorEvent`, aborts current operation cleanly.
- **Config/DB errors** — caught at startup before the engine starts; printed to stderr with actionable guidance; process exits cleanly.
- **Application log** — rotating text log at `~/.local/share/open-packet/open-packet.log` for all application-level errors and events.
- **Console log** — optional rotating log of raw frame traffic at a configurable path (see config); separate from the application log.

---

## Testing Strategy

- **Unit tests** — AX.25 frame encode/decode, KISS framing, BBS protocol parser, store CRUD, config loading/validation. Each module tested in isolation.
- **Integration tests** — engine + store + mock `ConnectionBase` replaying captured BBS session transcripts. Validates that a full check-mail cycle produces correct database state.
- **TUI tests** — Textual's built-in test harness; covers key bindings, console panel toggle, message navigation.
- **No hardware required** — all tests run against mock transports. Real TNC/BBS testing is manual and documented separately.
- **Test runner:** `pytest` via `uv run pytest`

---

## Build & Package Management

- **Tool:** [uv](https://docs.astral.sh/uv/)
- **Project definition:** `pyproject.toml`
- **Key dependencies:** Textual (TUI), Pydantic (config validation), pyserial (serial transport)
- **Commands:** `uv sync`, `uv run open-packet`, `uv run pytest`, `uv build`

---

## Feature Roadmap

### v0.1 — Proof of Concept
- KISS transport over serial and TCP/IP
- AX.25 framing and session management
- BPQ BBS driver: list, read, send, delete personal messages + read bulletins
- SQLite store with operator profiles and flat-file export
- Textual TUI: three-panel layout + collapsible console panel
- YAML config + Pydantic validation
- Rotating application log + optional console frame log
- uv-managed project, pytest test suite

### v0.2 — Connectivity Expansion
- Digipeater path support in AX.25 session layer
- Multi-node patching (connect A → B → C)
- Scripted connection sequences (YAML-defined)
- TelnetLink implementation (BBS over TCP, no AX.25)

### v0.3 — Automation & Daemon Mode
- Scheduled sync (configurable interval)
- `sync_log` table added to SQLite
- Unattended operation with systemd unit file example

### v0.4 — Interface Expansion
- REST API interface (FastAPI-based UIBase implementation)
- Web UI (served by the API layer)
- Multi-operator session support via web UI

### v0.5 — Protocol Expansion
- VARA modem link layer
- Additional node software drivers (Winlink, custom BBS)
- DMR data frame link layer (research/experimental)
