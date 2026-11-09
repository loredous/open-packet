---
title: "open-packet Documentation"
description: "Open-source amateur radio packet messaging client for Linux"
---

# open-packet

**open-packet** is an open-source amateur radio packet messaging client for Linux. It connects to a BBS node over AX.25 packet radio via a KISS TNC, syncing your personal messages and bulletins to a local SQLite database and presenting them through a terminal user interface (TUI).

> **Early development:** v0.1 — expect breaking changes between releases.

## Features

- **Messages** — read, compose, reply, archive, and delete personal packet messages
- **Bulletins** — browse bulletin categories and retrieve full bulletin bodies on demand
- **BBS Files** — list and download files from BBS file directories
- **ICS Forms** — compose and send structured ICS/standard forms messages
- **Terminal Connect** — open a raw terminal session to any AX.25 node
- **Multiple Operators & Nodes** — manage multiple callsigns and BBS nodes in a single installation
- **Offline-first** — all messages are stored locally in SQLite; connectivity is only needed to sync

## Quick Navigation

### [Getting Started]({{< relref "/docs/user-guide/getting-started" >}})
New to open-packet? Start here with installation and first-launch setup.

### [User Guide]({{< relref "/docs/user-guide" >}})
Learn how to use messages, bulletins, BBS files, forms, and the terminal.

### [Reference]({{< relref "/docs/reference" >}})
Configuration file reference and keyboard shortcuts.

### [Development]({{< relref "/docs/development" >}})
Architecture overview and contribution guide.
