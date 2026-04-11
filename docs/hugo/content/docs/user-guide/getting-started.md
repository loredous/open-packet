---
title: "Getting Started"
description: "Install, configure, and launch open-packet for the first time"
weight: 1
---

# Getting Started

## Requirements

- **Linux** (Windows and macOS are currently untested but may work)
- **Python 3.11** or newer
- **A KISS-capable TNC** connected via TCP or serial port. If you don't have hardware, [Direwolf](https://github.com/wb2osz/direwolf) is a good software TNC.

## Installation

Install open-packet with `uv`:

```bash
uv tool install git+https://github.com/loredous/open-packet
```

## First Launch

Run open-packet:

```bash
open-packet
```

On first launch, you will be prompted to:

1. **Set up your operator** — enter your amateur radio callsign and SSID
2. **Configure a BBS node** — enter the callsign and type of your BBS node
3. **Set up an interface** — configure the connection to your TNC

These can be changed later in the [Settings]({{< relref "settings" >}}) screen.

## Interface Overview

![open-packet main interface](/images/screenshot-main.png)

The main interface consists of:

| Area | Description |
|------|-------------|
| **Status bar** (top) | Shows connection status, operator callsign, and active node |
| **Folder tree** (left) | Navigate between Inbox, Outbox, Archive, Sent, Bulletins, and Files |
| **Message list** (center-top) | Lists messages in the current folder |
| **Message body** (center-bottom) | Shows the full content of the selected message |
| **Footer** (bottom) | Displays available keyboard shortcuts for the current context |
| **Console panel** (hidden) | Shows raw AX.25 frame traffic — toggle with `` ` `` |

## Your First Send/Receive

Press **Ctrl+C** to connect to the BBS and synchronise. open-packet will:

1. Connect to the configured TNC
2. Establish an AX.25 link to the BBS node
3. Retrieve new personal messages
4. Retrieve bulletin headers for subscribed categories
5. Send any queued outgoing messages
6. Disconnect

The status bar shows the current connection state throughout this process.
