---
title: "Configuration"
weight: 2
---

# Configuration Reference

The open-packet configuration file lives at `~/.config/open-packet/config.yaml`. You can also pass a custom path as the first argument:

```bash
open-packet /path/to/my-config.yaml
```

## Full Example

```yaml
connection:
  type: kiss_tcp            # Connection type (see below)
  host: localhost           # TCP hostname (kiss_tcp only)
  port: 8001                # TCP port (kiss_tcp only)
  # device: /dev/ttyUSB0   # Serial device (kiss_serial only)
  # baud: 9600             # Baud rate (kiss_serial only)

store:
  db_path: ~/.local/share/open-packet/messages.db
  export_path: ~/.local/share/open-packet/export

ui:
  console_visible: false
  console_buffer: 500
  # console_log: ~/.local/share/open-packet/console.log
```

## `connection` Section

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `type` | string | — | Connection type: `kiss_tcp`, `kiss_serial` |
| `host` | string | — | Hostname or IP address (`kiss_tcp` only) |
| `port` | integer | — | TCP port number (`kiss_tcp` only) |
| `device` | string | — | Serial device path (`kiss_serial` only) |
| `baud` | integer | `9600` | Baud rate (`kiss_serial` only) |

### Connection Types

| Type | Description |
|------|-------------|
| `kiss_tcp` | Connect to a KISS TNC over TCP — compatible with [Direwolf](https://github.com/wb2osz/direwolf), Soundmodem, and hardware TNCs with a TCP interface |
| `kiss_serial` | Connect to a KISS TNC over a serial port — for hardware TNCs connected via USB or RS-232 |

## `store` Section

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `db_path` | string | `~/.local/share/open-packet/messages.db` | Path to the SQLite message database |
| `export_path` | string | `~/.local/share/open-packet/export` | Directory where downloaded BBS files are saved |

## `ui` Section

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `console_visible` | boolean | `false` | Show the AX.25 frame console panel on startup |
| `console_buffer` | integer | `500` | Number of lines to retain in the console ring buffer |
| `console_log` | string | _(none)_ | If set, log all frame traffic to this file. Omit to disable |

{{< hint info >}}
Operator identity (callsign, SSID) and BBS node configuration are **not** stored in the config file. They are managed through the Settings screen (**Ctrl+S**) and stored in the SQLite database.
{{< /hint >}}
