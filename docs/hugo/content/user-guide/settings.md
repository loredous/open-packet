---
title: "Settings"
weight: 7
---

# Settings

Operator identity, BBS node configuration, and interface settings are stored in the local SQLite database and managed through the Settings screen. The config file covers only connection and storage settings.

## Opening Settings

Press **Ctrl+S** to open the Settings screen.

![Settings screen screenshot](/images/screenshot-settings.png)

## Operators

An **operator** represents your amateur radio identity — your callsign and SSID. You can configure multiple operators if you operate multiple callsigns.

### Adding an Operator

1. Open Settings (**Ctrl+S**)
2. Select **Operators**
3. Choose **Add Operator**
4. Enter your callsign, SSID, and a label
5. Save

### Setting the Default Operator

Select an operator and choose **Set as Default**. The default operator's callsign is shown in the status bar and used for all outgoing messages unless overridden.

## Nodes

A **node** is a BBS or packet node you connect to for messaging. Each node is associated with an interface (the connection to your TNC).

### Adding a Node

1. Open Settings (**Ctrl+S**)
2. Select **Nodes**
3. Choose **Add Node**
4. Enter:
   - **Label** — a friendly name for this node
   - **Callsign** — the node's callsign (e.g. `W1AW-10`)
   - **SSID** — the node's SSID
   - **Type** — `bpq` for BPQ32 nodes
   - **Interface** — which interface (TNC connection) to use
5. Save

### Node Path Settings

For nodes that require a specific digipeater path, you can configure:
- **Hop path** — a list of intermediate nodes (digipeaters) to route through
- **Path strategy** — how to route traffic to this node (`path_route` or direct)
- **Auto-forward** — whether to automatically check for shorter paths to this node

## Interfaces

An **interface** defines how open-packet connects to your TNC. This maps to the physical or network connection to your radio.

### Interface Types

| Type | Description |
|------|-------------|
| `kiss_tcp` | KISS TNC over TCP (e.g. Direwolf on localhost) |
| `kiss_serial` | KISS TNC over serial port |
| `telnet` | Telnet connection to a node |

### Adding an Interface

1. Open Settings (**Ctrl+S**)
2. Select **Interfaces**
3. Choose **Add Interface**
4. Select the interface type and fill in the connection details
5. Save

## General Settings

General settings include:
- **Console visibility** — show the AX.25 frame console on startup
- **Console buffer** — number of lines to retain in the console

These can also be set via CLI flags or environment variables — see the [Configuration Reference]({{< relref "/reference/configuration" >}}).
