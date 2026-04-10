---
title: "open-packet Documentation"
type: docs
---

# open-packet

**open-packet** is an open-source amateur radio packet messaging client for Linux. It connects to a BBS node over AX.25 packet radio via a KISS TNC, syncing your personal messages and bulletins to a local SQLite database and presenting them through a terminal user interface (TUI).

> [!NOTE]
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

{{% columns %}}
- ### Getting Started
  New to open-packet? Start here.

  [Installation & Setup →]({{< relref "/user-guide/getting-started" >}})

- ### User Guide
  Learn how to use each feature.

  [User Guide →]({{< relref "/user-guide" >}})

- ### Reference
  Configuration and keyboard shortcuts.

  [Reference →]({{< relref "/reference" >}})
{{% /columns %}}

---

## Screenshot

![open-packet TUI showing the message inbox](images/screenshot-inbox.png)

*The open-packet terminal user interface showing the message inbox.*
