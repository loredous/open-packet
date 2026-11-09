---
title: "Configuration"
description: "Full configuration file reference"
weight: 2
---

# Configuration Reference

open-packet is configured via command-line flags or environment variables. There is no config file.

## Command-Line Flags

```bash
open-packet [OPTIONS]

  --db-path PATH       Path to the SQLite message database
  --log-path PATH      Path to the application log file
  --console-log PATH   Path to log all AX.25 frame traffic (omit to disable)
  --forms-dir PATH     Path to the forms directory
```

## Environment Variables

Each flag has a corresponding environment variable. The flag takes precedence when both are set.

| Flag | Environment Variable | Default |
|------|---------------------|---------|
| `--db-path` | `OPEN_PACKET_DB_PATH` | `~/.local/share/open-packet/messages.db` |
| `--log-path` | `OPEN_PACKET_LOG_PATH` | `~/.local/share/open-packet/open-packet.log` |
| `--console-log` | `OPEN_PACKET_CONSOLE_LOG` | _(disabled)_ |
| `--forms-dir` | `OPEN_PACKET_FORMS_DIR` | _(built-in forms)_ |

## Examples

```bash
# Use a custom database path
open-packet --db-path ~/ham/messages.db

# Log AX.25 frame traffic to a file
open-packet --console-log ~/ham/frames.log

# Set via environment variable
OPEN_PACKET_DB_PATH=~/ham/messages.db open-packet
```

> [!NOTE]
> Operator identity (callsign, SSID), BBS node configuration, and interface settings are **not** configured here. They are managed through the Settings screen (**Ctrl+S**) and stored in the SQLite database.
