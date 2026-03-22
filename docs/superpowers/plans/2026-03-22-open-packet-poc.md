# open-packet PoC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the open-packet v0.1 proof-of-concept — a Linux TUI client that connects to a BPQ BBS node over AX.25/KISS, retrieves and sends personal messages and bulletins, and stores them in SQLite.

**Architecture:** A core engine runs in a background thread, orchestrating a KISS transport → AX.25 framing → ConnectionBase → BPQ node driver → SQLite store pipeline. The Textual TUI communicates with the engine via thread-safe command/event queues. Each layer is defined by an ABC to enable future swappable implementations.

**Tech Stack:** Python 3.11+, uv (build/package), Textual (TUI), pyserial (serial transport), PyYAML (config parsing), pytest + pytest-asyncio (testing). No Pydantic — config validation uses manual checks with plain dataclasses to keep the dependency footprint minimal.

---

## File Map

```
open_packet/
├── __init__.py
├── transport/
│   ├── __init__.py
│   ├── base.py           # TransportBase ABC
│   ├── tcp.py            # TCPTransport
│   └── serial.py         # SerialTransport
├── ax25/
│   ├── __init__.py
│   ├── address.py        # AX.25 callsign+SSID encode/decode
│   └── frame.py          # AX.25 UI frame encode/decode
├── link/
│   ├── __init__.py
│   ├── base.py           # ConnectionBase ABC
│   └── kiss.py           # KISSLink (TransportBase + AX.25 → ConnectionBase)
├── node/
│   ├── __init__.py
│   ├── base.py           # NodeBase ABC + MessageHeader/Message dataclasses
│   └── bpq.py            # BPQNode: BPQ BBS protocol driver
├── store/
│   ├── __init__.py
│   ├── models.py         # Operator, Node, Message, Bulletin dataclasses
│   ├── database.py       # SQLite connection + schema creation
│   └── store.py          # Store: all CRUD operations
├── config/
│   ├── __init__.py
│   └── config.py         # Dataclass config models + YAML loader + manual validation
├── engine/
│   ├── __init__.py
│   ├── commands.py       # Command dataclasses (UI → Engine)
│   ├── events.py         # Event dataclasses (Engine → UI)
│   └── engine.py         # Engine: background thread, orchestration
└── ui/
    ├── __init__.py
    ├── base.py           # UIBase ABC
    └── tui/
        ├── __init__.py
        ├── app.py                    # Main Textual Application
        ├── screens/
        │   ├── __init__.py
        │   ├── main.py               # MainScreen: three-panel layout
        │   └── compose.py            # ComposeScreen: new message overlay
        └── widgets/
            ├── __init__.py
            ├── status_bar.py         # Header: callsign, status, last sync
            ├── folder_tree.py        # Left panel: Inbox/Sent/Bulletins tree
            ├── message_list.py       # Top-right: message headers table
            ├── message_body.py       # Bottom-right: message body viewer
            └── console_panel.py      # Bottom: collapsible frame traffic log

tests/
├── conftest.py
├── test_ax25/
│   ├── test_address.py
│   └── test_frame.py
├── test_link/
│   └── test_kiss.py
├── test_transport/
│   └── test_tcp.py
├── test_node/
│   └── test_bpq.py
├── test_store/
│   └── test_store.py
├── test_config/
│   └── test_config.py
├── test_engine/
│   └── test_engine.py
└── test_ui/
    └── test_tui.py

pyproject.toml
README.md
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `open_packet/__init__.py` (and all `__init__.py` files in the map above)
- Create: `tests/conftest.py`

- [ ] **Step 1: Initialize the project with uv**

```bash
cd /path/to/open-packet
uv init --name open-packet --python 3.11
```

This creates `pyproject.toml`. Replace its contents with:

```toml
[project]
name = "open-packet"
version = "0.1.0"
description = "Amateur radio packet messaging client"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "textual>=0.60.0",
    "pyserial>=3.5",
    "pyyaml>=6.0",
]

[project.scripts]
open-packet = "open_packet.ui.tui.app:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.uv]
dev-dependencies = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "textual-dev>=0.60.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Install dependencies**

```bash
uv sync
```

Expected: dependencies installed into `.venv/`

- [ ] **Step 3: Create the package directory tree**

```bash
mkdir -p open_packet/{transport,ax25,link,node,store,config,engine,ui/tui/{screens,widgets}}
mkdir -p tests/{test_ax25,test_link,test_transport,test_node,test_store,test_config,test_engine,test_ui}
```

- [ ] **Step 4: Create all `__init__.py` files**

Create an empty `__init__.py` in every directory listed in the file map above, plus every `tests/` subdirectory.

```bash
find open_packet tests -type d | xargs -I{} touch {}/__init__.py
```

- [ ] **Step 5: Create `tests/conftest.py`**

```python
# tests/conftest.py
import pytest
```

- [ ] **Step 6: Create a minimal `README.md`**

```markdown
# open-packet

Amateur radio packet messaging client.

## Quick Start

```bash
uv sync
uv run open-packet
```

## Development

```bash
uv run pytest
```
```

- [ ] **Step 7: Verify pytest runs**

```bash
uv run pytest
```

Expected: "no tests ran" — zero failures, zero errors.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml README.md open_packet/ tests/
git commit -m "feat: project scaffolding with uv, package structure, and test layout"
```

---

## Task 2: Config Module

**Files:**
- Create: `open_packet/config/config.py`
- Create: `tests/test_config/test_config.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config/test_config.py
import pytest
import tempfile
import os
from open_packet.config.config import AppConfig, load_config, ConfigError

VALID_YAML = """
connection:
  type: kiss_tcp
  host: localhost
  port: 8001

store:
  db_path: /tmp/test.db
  export_path: /tmp/export

ui:
  console_visible: false
  console_buffer: 500
"""

SERIAL_YAML = """
connection:
  type: kiss_serial
  device: /dev/ttyUSB0
  baud: 9600

store:
  db_path: /tmp/test.db
  export_path: /tmp/export

ui:
  console_visible: false
  console_buffer: 500
"""

def write_yaml(content: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(content)
    f.close()
    return f.name


def test_load_valid_tcp_config():
    path = write_yaml(VALID_YAML)
    try:
        config = load_config(path)
        assert config.connection.type == "kiss_tcp"
        assert config.connection.host == "localhost"
        assert config.connection.port == 8001
        assert config.store.db_path == "/tmp/test.db"
        assert config.ui.console_buffer == 500
        assert config.ui.console_visible is False
        assert config.ui.console_log is None
    finally:
        os.unlink(path)


def test_load_valid_serial_config():
    path = write_yaml(SERIAL_YAML)
    try:
        config = load_config(path)
        assert config.connection.type == "kiss_serial"
        assert config.connection.device == "/dev/ttyUSB0"
        assert config.connection.baud == 9600
    finally:
        os.unlink(path)


def test_missing_file_raises():
    with pytest.raises(ConfigError, match="not found"):
        load_config("/nonexistent/path/config.yaml")


def test_invalid_connection_type_raises():
    bad_yaml = VALID_YAML.replace("kiss_tcp", "invalid_type")
    path = write_yaml(bad_yaml)
    try:
        with pytest.raises(ConfigError):
            load_config(path)
    finally:
        os.unlink(path)


def test_console_log_optional():
    yaml_with_log = VALID_YAML + "\n  console_log: /tmp/console.log\n"
    path = write_yaml(yaml_with_log)
    try:
        config = load_config(path)
        assert config.ui.console_log == "/tmp/console.log"
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_config/ -v
```

Expected: ImportError — `open_packet.config.config` does not exist yet.

- [ ] **Step 3: Implement the config module**

```python
# open_packet/config/config.py
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import yaml

VALID_CONNECTION_TYPES = {"kiss_tcp", "kiss_serial"}


class ConfigError(Exception):
    pass


@dataclass
class TCPConnectionConfig:
    type: str
    host: str = "localhost"
    port: int = 8001


@dataclass
class SerialConnectionConfig:
    type: str
    device: str = ""
    baud: int = 9600


@dataclass
class StoreConfig:
    db_path: str = "~/.local/share/open-packet/messages.db"
    export_path: str = "~/.local/share/open-packet/export"


@dataclass
class UIConfig:
    console_visible: bool = False
    console_buffer: int = 500
    console_log: Optional[str] = None


@dataclass
class AppConfig:
    connection: TCPConnectionConfig | SerialConnectionConfig
    store: StoreConfig = field(default_factory=StoreConfig)
    ui: UIConfig = field(default_factory=UIConfig)


def _parse_connection(raw: dict) -> TCPConnectionConfig | SerialConnectionConfig:
    conn_type = raw.get("type", "")
    if conn_type not in VALID_CONNECTION_TYPES:
        raise ConfigError(
            f"Invalid connection type '{conn_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_CONNECTION_TYPES))}"
        )
    if conn_type == "kiss_tcp":
        return TCPConnectionConfig(
            type=conn_type,
            host=str(raw.get("host", "localhost")),
            port=int(raw.get("port", 8001)),
        )
    else:
        if "device" not in raw:
            raise ConfigError("kiss_serial connection requires 'device' field")
        return SerialConnectionConfig(
            type=conn_type,
            device=str(raw["device"]),
            baud=int(raw.get("baud", 9600)),
        )


def _parse_store(raw: dict) -> StoreConfig:
    return StoreConfig(
        db_path=str(raw.get("db_path", StoreConfig.db_path)),
        export_path=str(raw.get("export_path", StoreConfig.export_path)),
    )


def _parse_ui(raw: dict) -> UIConfig:
    return UIConfig(
        console_visible=bool(raw.get("console_visible", False)),
        console_buffer=int(raw.get("console_buffer", 500)),
        console_log=raw.get("console_log"),
    )


def load_config(path: str) -> AppConfig:
    expanded = os.path.expanduser(path)
    if not os.path.exists(expanded):
        raise ConfigError(f"Config file not found: {expanded}")
    with open(expanded) as f:
        raw = yaml.safe_load(f) or {}
    if "connection" not in raw:
        raise ConfigError("Config missing required 'connection' section")
    try:
        return AppConfig(
            connection=_parse_connection(raw["connection"]),
            store=_parse_store(raw.get("store", {})),
            ui=_parse_ui(raw.get("ui", {})),
        )
    except (TypeError, ValueError) as e:
        raise ConfigError(f"Invalid config value: {e}") from e
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_config/ -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add open_packet/config/config.py tests/test_config/test_config.py
git commit -m "feat: config module with manual validation and YAML loading"
```

---

## Task 3: AX.25 Address Encoding

**Files:**
- Create: `open_packet/ax25/address.py`
- Create: `tests/test_ax25/test_address.py`

AX.25 addresses encode each character of a callsign by shifting its ASCII value left by 1 bit. The 7th byte is the SSID byte: `0b01100000 | (ssid << 1) | end_flag` where `end_flag=1` marks the last address in the chain.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ax25/test_address.py
from open_packet.ax25.address import encode_address, decode_address, AX25Address


def test_encode_callsign_no_ssid():
    # "KD9ABC" with SSID 0, not last address
    encoded = encode_address("KD9ABC", ssid=0, last=False)
    assert len(encoded) == 7
    # Each char shifted left by 1
    assert encoded[0] == ord("K") << 1
    assert encoded[1] == ord("D") << 1
    assert encoded[2] == ord("9") << 1
    assert encoded[3] == ord("A") << 1
    assert encoded[4] == ord("B") << 1
    assert encoded[5] == ord("C") << 1
    # SSID byte: 0b01100000 | (0 << 1) | 0 = 0x60
    assert encoded[6] == 0x60


def test_encode_callsign_with_ssid():
    encoded = encode_address("KD9ABC", ssid=1, last=True)
    # SSID byte: 0b01100000 | (1 << 1) | 1 = 0x63
    assert encoded[6] == 0x63


def test_encode_short_callsign_padded():
    # Callsigns shorter than 6 chars must be space-padded
    encoded = encode_address("W0BPQ", ssid=0, last=False)
    assert len(encoded) == 7
    assert encoded[4] == ord("Q") << 1
    assert encoded[5] == ord(" ") << 1  # padded


def test_decode_address():
    encoded = encode_address("KD9ABC", ssid=1, last=True)
    addr = decode_address(encoded)
    assert addr.callsign == "KD9ABC"
    assert addr.ssid == 1
    assert addr.last is True


def test_decode_short_callsign():
    encoded = encode_address("W0BPQ", ssid=0, last=False)
    addr = decode_address(encoded)
    assert addr.callsign == "W0BPQ"
    assert addr.ssid == 0
    assert addr.last is False
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_ax25/test_address.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement address encoding**

```python
# open_packet/ax25/address.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class AX25Address:
    callsign: str
    ssid: int
    last: bool


def encode_address(callsign: str, ssid: int, last: bool) -> bytes:
    padded = callsign.upper().ljust(6)[:6]
    encoded = bytes(ord(c) << 1 for c in padded)
    ssid_byte = 0b01100000 | ((ssid & 0x0F) << 1) | (1 if last else 0)
    return encoded + bytes([ssid_byte])


def decode_address(data: bytes) -> AX25Address:
    if len(data) < 7:
        raise ValueError(f"Address field must be 7 bytes, got {len(data)}")
    callsign = "".join(chr(b >> 1) for b in data[:6]).rstrip()
    ssid_byte = data[6]
    ssid = (ssid_byte >> 1) & 0x0F
    last = bool(ssid_byte & 0x01)
    return AX25Address(callsign=callsign, ssid=ssid, last=last)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_ax25/test_address.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add open_packet/ax25/address.py tests/test_ax25/test_address.py
git commit -m "feat: AX.25 address encode/decode"
```

---

## Task 4: AX.25 Frame Encode/Decode

**Files:**
- Create: `open_packet/ax25/frame.py`
- Create: `tests/test_ax25/test_frame.py`

For the PoC we only need **UI frames** (unnumbered information): control=0x03, PID=0xF0. The frame layout is: destination (7 bytes) + source (7 bytes) + control (1 byte) + PID (1 byte) + info (variable).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ax25/test_frame.py
from open_packet.ax25.frame import AX25Frame, encode_frame, decode_frame


def test_encode_ui_frame():
    frame = AX25Frame(
        destination="W0BPQ",
        destination_ssid=1,
        source="KD9ABC",
        source_ssid=0,
        info=b"Hello",
    )
    data = encode_frame(frame)
    assert isinstance(data, bytes)
    # Destination is first 7 bytes
    assert len(data) >= 16  # 7 + 7 + 1 + 1 + 5


def test_round_trip():
    original = AX25Frame(
        destination="W0BPQ",
        destination_ssid=1,
        source="KD9ABC",
        source_ssid=0,
        info=b"Test message",
    )
    data = encode_frame(original)
    decoded = decode_frame(data)
    assert decoded.destination == "W0BPQ"
    assert decoded.destination_ssid == 1
    assert decoded.source == "KD9ABC"
    assert decoded.source_ssid == 0
    assert decoded.info == b"Test message"


def test_empty_info():
    frame = AX25Frame(
        destination="W0BPQ",
        destination_ssid=0,
        source="KD9ABC",
        source_ssid=1,
        info=b"",
    )
    data = encode_frame(frame)
    decoded = decode_frame(data)
    assert decoded.info == b""


def test_decode_sets_last_flags_correctly():
    frame = AX25Frame(
        destination="W0BPQ",
        destination_ssid=0,
        source="KD9ABC",
        source_ssid=0,
        info=b"x",
    )
    data = encode_frame(frame)
    # Source address last bit must be set (end of address field)
    # Destination last bit must NOT be set
    assert data[6] & 0x01 == 0   # destination not last
    assert data[13] & 0x01 == 1  # source is last
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_ax25/test_frame.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement frame encode/decode**

```python
# open_packet/ax25/frame.py
from __future__ import annotations
from dataclasses import dataclass, field

from open_packet.ax25.address import encode_address, decode_address

# UI frame constants
CONTROL_UI = 0x03
PID_NO_LAYER3 = 0xF0


@dataclass
class AX25Frame:
    destination: str
    destination_ssid: int
    source: str
    source_ssid: int
    info: bytes = field(default=b"")
    control: int = CONTROL_UI
    pid: int = PID_NO_LAYER3


def encode_frame(frame: AX25Frame) -> bytes:
    dest = encode_address(frame.destination, frame.destination_ssid, last=False)
    src = encode_address(frame.source, frame.source_ssid, last=True)
    return dest + src + bytes([frame.control, frame.pid]) + frame.info


def decode_frame(data: bytes) -> AX25Frame:
    if len(data) < 16:
        raise ValueError(f"Frame too short: {len(data)} bytes")
    destination_addr = decode_address(data[0:7])
    source_addr = decode_address(data[7:14])
    control = data[14]
    pid = data[15]
    info = data[16:]
    return AX25Frame(
        destination=destination_addr.callsign,
        destination_ssid=destination_addr.ssid,
        source=source_addr.callsign,
        source_ssid=source_addr.ssid,
        info=info,
        control=control,
        pid=pid,
    )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_ax25/ -v
```

Expected: all AX.25 tests pass.

- [ ] **Step 5: Commit**

```bash
git add open_packet/ax25/frame.py tests/test_ax25/test_frame.py
git commit -m "feat: AX.25 UI frame encode/decode"
```

---

## Task 5: Transport Layer

**Files:**
- Create: `open_packet/transport/base.py`
- Create: `open_packet/transport/tcp.py`
- Create: `open_packet/transport/serial.py`
- Create: `tests/test_transport/test_tcp.py`

The transport layer is the raw byte pipe. `TCPTransport` connects to a host/port (used for Dire Wolf, soundmodem, etc.). `SerialTransport` opens a serial port (used for hardware TNCs).

- [ ] **Step 1: Write the failing tests (TCP only — serial requires hardware)**

```python
# tests/test_transport/test_tcp.py
import socket
import threading
import pytest
from open_packet.transport.tcp import TCPTransport
from open_packet.transport.base import TransportError


def make_echo_server(host: str, port: int) -> threading.Thread:
    """Minimal echo server for testing."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(1)
    server.settimeout(2)

    def serve():
        try:
            conn, _ = server.accept()
            conn.settimeout(1)
            try:
                while True:
                    data = conn.recv(1024)
                    if not data:
                        break
                    conn.sendall(data)
            except (socket.timeout, ConnectionResetError):
                pass
            finally:
                conn.close()
        except socket.timeout:
            pass
        finally:
            server.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    return t


def test_tcp_connect_send_receive():
    host, port = "127.0.0.1", 15432
    make_echo_server(host, port)
    import time; time.sleep(0.05)

    t = TCPTransport(host=host, port=port)
    t.connect()
    try:
        t.send_bytes(b"\xc0\x00hello\xc0")
        data = t.receive_bytes(timeout=1.0)
        assert data == b"\xc0\x00hello\xc0"
    finally:
        t.disconnect()


def test_tcp_connect_failure_raises():
    t = TCPTransport(host="127.0.0.1", port=19999)
    with pytest.raises(TransportError, match="connect"):
        t.connect()


def test_tcp_send_without_connect_raises():
    t = TCPTransport(host="127.0.0.1", port=8001)
    with pytest.raises(TransportError, match="not connected"):
        t.send_bytes(b"data")
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_transport/ -v
```

Expected: ImportError.

- [ ] **Step 3: Implement TransportBase**

```python
# open_packet/transport/base.py
from __future__ import annotations
from abc import ABC, abstractmethod


class TransportError(Exception):
    pass


class TransportBase(ABC):
    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def send_bytes(self, data: bytes) -> None: ...

    @abstractmethod
    def receive_bytes(self, timeout: float = 5.0) -> bytes: ...
```

- [ ] **Step 4: Implement TCPTransport**

```python
# open_packet/transport/tcp.py
from __future__ import annotations
import socket
from open_packet.transport.base import TransportBase, TransportError


class TCPTransport(TransportBase):
    def __init__(self, host: str, port: int):
        self._host = host
        self._port = port
        self._sock: socket.socket | None = None

    def connect(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        try:
            sock.connect((self._host, self._port))
        except (ConnectionRefusedError, OSError) as e:
            sock.close()
            raise TransportError(f"Failed to connect to {self._host}:{self._port}: {e}") from e
        self._sock = sock

    def disconnect(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def send_bytes(self, data: bytes) -> None:
        if not self._sock:
            raise TransportError("not connected")
        try:
            self._sock.sendall(data)
        except OSError as e:
            raise TransportError(f"Send failed: {e}") from e

    def receive_bytes(self, timeout: float = 5.0) -> bytes:
        if not self._sock:
            raise TransportError("not connected")
        self._sock.settimeout(timeout)
        try:
            data = self._sock.recv(4096)
            if not data:
                raise TransportError("Connection closed by remote")
            return data
        except socket.timeout:
            return b""
        except OSError as e:
            raise TransportError(f"Receive failed: {e}") from e
```

- [ ] **Step 5: Implement SerialTransport**

```python
# open_packet/transport/serial.py
from __future__ import annotations
import serial
from open_packet.transport.base import TransportBase, TransportError


class SerialTransport(TransportBase):
    def __init__(self, device: str, baud: int = 9600):
        self._device = device
        self._baud = baud
        self._port: serial.Serial | None = None

    def connect(self) -> None:
        try:
            self._port = serial.Serial(
                port=self._device,
                baudrate=self._baud,
                timeout=5.0,
            )
        except serial.SerialException as e:
            raise TransportError(f"Failed to open {self._device}: {e}") from e

    def disconnect(self) -> None:
        if self._port and self._port.is_open:
            try:
                self._port.close()
            except serial.SerialException:
                pass
        self._port = None

    def send_bytes(self, data: bytes) -> None:
        if not self._port or not self._port.is_open:
            raise TransportError("not connected")
        try:
            self._port.write(data)
        except serial.SerialException as e:
            raise TransportError(f"Send failed: {e}") from e

    def receive_bytes(self, timeout: float = 5.0) -> bytes:
        if not self._port or not self._port.is_open:
            raise TransportError("not connected")
        self._port.timeout = timeout
        try:
            return self._port.read(4096)
        except serial.SerialException as e:
            raise TransportError(f"Receive failed: {e}") from e
```

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/test_transport/ -v
```

Expected: 3 tests pass.

- [ ] **Step 7: Commit**

```bash
git add open_packet/transport/ tests/test_transport/
git commit -m "feat: transport layer with TCPTransport and SerialTransport"
```

---

## Task 6: KISS Framing + ConnectionBase

**Files:**
- Create: `open_packet/link/base.py`
- Create: `open_packet/link/kiss.py`
- Create: `tests/test_link/test_kiss.py`

KISS encapsulates AX.25 frames for transmission over a serial or TCP byte pipe. Special bytes: FEND=0xC0 (frame delimiter), FESC=0xDB (escape), TFEND=0xDC (escaped FEND), TFESC=0xDD (escaped FESC). A data frame: `FEND 0x00 <escaped_data> FEND`.

`KISSLink` wraps a `TransportBase`, providing the `ConnectionBase` interface (send/receive AX.25 frames). It maintains a receive buffer to handle partial reads and multi-frame packets.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_link/test_kiss.py
import pytest
from open_packet.link.kiss import kiss_encode, kiss_decode, KISSLink
from open_packet.transport.base import TransportBase, TransportError
from open_packet.ax25.frame import AX25Frame, encode_frame


# --- KISS encode/decode unit tests ---

def test_kiss_encode_simple():
    data = b"\x01\x02\x03"
    encoded = kiss_encode(data)
    assert encoded == b"\xc0\x00\x01\x02\x03\xc0"


def test_kiss_encode_escapes_fend():
    data = b"\xc0"
    encoded = kiss_encode(data)
    assert encoded == b"\xc0\x00\xdb\xdc\xc0"


def test_kiss_encode_escapes_fesc():
    data = b"\xdb"
    encoded = kiss_encode(data)
    assert encoded == b"\xc0\x00\xdb\xdd\xc0"


def test_kiss_decode_simple():
    packet = b"\xc0\x00\x01\x02\x03\xc0"
    decoded = kiss_decode(packet)
    assert decoded == b"\x01\x02\x03"


def test_kiss_decode_unescapes_fend():
    packet = b"\xc0\x00\xdb\xdc\xc0"
    decoded = kiss_decode(packet)
    assert decoded == b"\xc0"


def test_kiss_decode_unescapes_fesc():
    packet = b"\xc0\x00\xdb\xdd\xc0"
    decoded = kiss_decode(packet)
    assert decoded == b"\xdb"


def test_kiss_round_trip():
    original = b"Hello\xc0World\xdb!"
    assert kiss_decode(kiss_encode(original)) == original


# --- KISSLink integration using a mock transport ---

class MockTransport(TransportBase):
    def __init__(self, responses: list[bytes]):
        self._responses = list(responses)
        self.sent: list[bytes] = []
        self._connected = False

    def connect(self): self._connected = True
    def disconnect(self): self._connected = False

    def send_bytes(self, data: bytes):
        self.sent.append(data)

    def receive_bytes(self, timeout: float = 5.0) -> bytes:
        if self._responses:
            return self._responses.pop(0)
        return b""


def test_kisslink_send_frame():
    transport = MockTransport(responses=[])
    link = KISSLink(transport=transport)
    link.connect(callsign="W0BPQ", ssid=1)

    frame = AX25Frame(
        destination="W0BPQ", destination_ssid=1,
        source="KD9ABC", source_ssid=0,
        info=b"L\r",
    )
    link.send_frame(encode_frame(frame))
    assert len(transport.sent) == 1
    assert transport.sent[0].startswith(b"\xc0")
    assert transport.sent[0].endswith(b"\xc0")


def test_kisslink_receive_frame():
    ax25_data = encode_frame(AX25Frame(
        destination="KD9ABC", destination_ssid=0,
        source="W0BPQ", source_ssid=1,
        info=b"BPQ> ",
    ))
    kiss_packet = kiss_encode(ax25_data)
    transport = MockTransport(responses=[kiss_packet])
    link = KISSLink(transport=transport)
    link.connect(callsign="W0BPQ", ssid=1)

    received = link.receive_frame(timeout=1.0)
    assert received == ax25_data
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_link/ -v
```

Expected: ImportError.

- [ ] **Step 3: Implement ConnectionBase**

```python
# open_packet/link/base.py
from __future__ import annotations
from abc import ABC, abstractmethod


class ConnectionError(Exception):
    pass


class ConnectionBase(ABC):
    @abstractmethod
    def connect(self, callsign: str, ssid: int) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def send_frame(self, data: bytes) -> None: ...

    @abstractmethod
    def receive_frame(self, timeout: float = 5.0) -> bytes: ...
```

- [ ] **Step 4: Implement KISS encode/decode and KISSLink**

```python
# open_packet/link/kiss.py
from __future__ import annotations

from open_packet.link.base import ConnectionBase, ConnectionError
from open_packet.transport.base import TransportBase, TransportError

FEND = 0xC0
FESC = 0xDB
TFEND = 0xDC
TFESC = 0xDD
CMD_DATA = 0x00


def kiss_encode(data: bytes) -> bytes:
    escaped = bytearray()
    for byte in data:
        if byte == FEND:
            escaped += bytes([FESC, TFEND])
        elif byte == FESC:
            escaped += bytes([FESC, TFESC])
        else:
            escaped.append(byte)
    return bytes([FEND, CMD_DATA]) + bytes(escaped) + bytes([FEND])


def kiss_decode(packet: bytes) -> bytes:
    # Strip leading/trailing FEND and CMD byte
    inner = packet.strip(bytes([FEND]))
    if not inner:
        return b""
    # Skip the command byte
    inner = inner[1:]
    result = bytearray()
    i = 0
    while i < len(inner):
        if inner[i] == FESC:
            i += 1
            if i < len(inner):
                if inner[i] == TFEND:
                    result.append(FEND)
                elif inner[i] == TFESC:
                    result.append(FESC)
        else:
            result.append(inner[i])
        i += 1
    return bytes(result)


class KISSLink(ConnectionBase):
    def __init__(self, transport: TransportBase):
        self._transport = transport
        self._buffer = b""

    def connect(self, callsign: str, ssid: int) -> None:
        try:
            self._transport.connect()
        except TransportError as e:
            raise ConnectionError(f"Transport connect failed: {e}") from e

    def disconnect(self) -> None:
        self._transport.disconnect()

    def send_frame(self, data: bytes) -> None:
        try:
            self._transport.send_bytes(kiss_encode(data))
        except TransportError as e:
            raise ConnectionError(f"Send failed: {e}") from e

    def receive_frame(self, timeout: float = 5.0) -> bytes:
        try:
            chunk = self._transport.receive_bytes(timeout=timeout)
        except TransportError as e:
            raise ConnectionError(f"Receive failed: {e}") from e

        self._buffer += chunk
        # Extract one complete KISS frame from the buffer
        start = self._buffer.find(bytes([FEND]))
        if start == -1:
            return b""
        end = self._buffer.find(bytes([FEND]), start + 1)
        if end == -1:
            return b""
        frame = self._buffer[start:end + 1]
        self._buffer = self._buffer[end + 1:]
        return kiss_decode(frame)
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_link/ -v
```

Expected: all KISS tests pass.

- [ ] **Step 6: Commit**

```bash
git add open_packet/link/ tests/test_link/
git commit -m "feat: KISS framing and KISSLink ConnectionBase implementation"
```

---

## Task 7: Store — Models and Schema

**Files:**
- Create: `open_packet/store/models.py`
- Create: `open_packet/store/database.py`
- Create: `tests/test_store/test_store.py` (partial — schema tests only)

- [ ] **Step 1: Write schema tests**

```python
# tests/test_store/test_store.py
import pytest
import tempfile
import os
from open_packet.store.database import Database
from open_packet.store.models import Operator, Node, Message, Bulletin


@pytest.fixture
def db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    database = Database(f.name)
    database.initialize()
    yield database
    database.close()
    os.unlink(f.name)


def test_database_creates_tables(db):
    tables = db.table_names()
    assert "operators" in tables
    assert "nodes" in tables
    assert "messages" in tables
    assert "bulletins" in tables


def test_insert_and_fetch_operator(db):
    op = Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True)
    inserted = db.insert_operator(op)
    assert inserted.id is not None
    fetched = db.get_operator(inserted.id)
    assert fetched.callsign == "KD9ABC"
    assert fetched.ssid == 1
    assert fetched.label == "home"
    assert fetched.is_default is True


def test_insert_and_fetch_node(db):
    node = Node(label="Home BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True)
    inserted = db.insert_node(node)
    assert inserted.id is not None
    fetched = db.get_node(inserted.id)
    assert fetched.callsign == "W0BPQ"
    assert fetched.node_type == "bpq"
    assert fetched.is_default is True


def test_get_default_operator(db):
    db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    op = db.get_default_operator()
    assert op is not None
    assert op.callsign == "KD9ABC"


def test_get_default_node(db):
    db.insert_node(Node(label="Home BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    node = db.get_default_node()
    assert node is not None
    assert node.callsign == "W0BPQ"
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_store/ -v
```

Expected: ImportError.

- [ ] **Step 3: Implement models**

```python
# open_packet/store/models.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Operator:
    callsign: str
    ssid: int
    label: str
    is_default: bool = False
    id: Optional[int] = None
    created_at: Optional[datetime] = None


@dataclass
class Node:
    label: str
    callsign: str
    ssid: int
    node_type: str  # e.g. "bpq"
    is_default: bool = False
    id: Optional[int] = None
    created_at: Optional[datetime] = None


@dataclass
class Message:
    operator_id: int
    node_id: int
    bbs_id: str
    from_call: str
    to_call: str
    subject: str
    body: str
    timestamp: datetime
    read: bool = False
    sent: bool = False
    deleted: bool = False
    id: Optional[int] = None
    synced_at: Optional[datetime] = None


@dataclass
class Bulletin:
    operator_id: int
    node_id: int
    bbs_id: str
    category: str
    from_call: str
    subject: str
    body: str
    timestamp: datetime
    read: bool = False
    id: Optional[int] = None
    synced_at: Optional[datetime] = None
```

- [ ] **Step 4: Implement Database**

```python
# open_packet/store/database.py
from __future__ import annotations
import sqlite3
from datetime import datetime
from typing import Optional

from open_packet.store.models import Operator, Node, Message, Bulletin


class Database:
    def __init__(self, path: str):
        self._path = path
        self._conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def table_names(self) -> list[str]:
        assert self._conn
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return [r["name"] for r in rows]

    def _create_schema(self) -> None:
        assert self._conn
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS operators (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                callsign TEXT NOT NULL,
                ssid INTEGER NOT NULL,
                label TEXT NOT NULL,
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                callsign TEXT NOT NULL,
                ssid INTEGER NOT NULL DEFAULT 0,
                node_type TEXT NOT NULL,
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operator_id INTEGER NOT NULL REFERENCES operators(id),
                node_id INTEGER NOT NULL REFERENCES nodes(id),
                bbs_id TEXT NOT NULL,
                from_call TEXT NOT NULL,
                to_call TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                read INTEGER NOT NULL DEFAULT 0,
                sent INTEGER NOT NULL DEFAULT 0,
                deleted INTEGER NOT NULL DEFAULT 0,
                synced_at TEXT
            );

            CREATE TABLE IF NOT EXISTS bulletins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operator_id INTEGER NOT NULL REFERENCES operators(id),
                node_id INTEGER NOT NULL REFERENCES nodes(id),
                bbs_id TEXT NOT NULL,
                category TEXT NOT NULL,
                from_call TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                read INTEGER NOT NULL DEFAULT 0,
                synced_at TEXT
            );
        """)
        self._conn.commit()

    def insert_operator(self, op: Operator) -> Operator:
        assert self._conn
        cur = self._conn.execute(
            "INSERT INTO operators (callsign, ssid, label, is_default) VALUES (?, ?, ?, ?)",
            (op.callsign, op.ssid, op.label, int(op.is_default)),
        )
        self._conn.commit()
        return self.get_operator(cur.lastrowid)  # type: ignore

    def get_operator(self, id: int) -> Optional[Operator]:
        assert self._conn
        row = self._conn.execute("SELECT * FROM operators WHERE id=?", (id,)).fetchone()
        if not row:
            return None
        return Operator(
            id=row["id"], callsign=row["callsign"], ssid=row["ssid"],
            label=row["label"], is_default=bool(row["is_default"]),
        )

    def get_default_operator(self) -> Optional[Operator]:
        assert self._conn
        row = self._conn.execute(
            "SELECT * FROM operators WHERE is_default=1 LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return Operator(
            id=row["id"], callsign=row["callsign"], ssid=row["ssid"],
            label=row["label"], is_default=bool(row["is_default"]),
        )

    def insert_node(self, node: Node) -> Node:
        assert self._conn
        cur = self._conn.execute(
            "INSERT INTO nodes (label, callsign, ssid, node_type, is_default) VALUES (?, ?, ?, ?, ?)",
            (node.label, node.callsign, node.ssid, node.node_type, int(node.is_default)),
        )
        self._conn.commit()
        return self.get_node(cur.lastrowid)  # type: ignore

    def get_node(self, id: int) -> Optional[Node]:
        assert self._conn
        row = self._conn.execute("SELECT * FROM nodes WHERE id=?", (id,)).fetchone()
        if not row:
            return None
        return Node(
            id=row["id"], label=row["label"], callsign=row["callsign"],
            ssid=row["ssid"], node_type=row["node_type"],
            is_default=bool(row["is_default"]),
        )

    def get_default_node(self) -> Optional[Node]:
        assert self._conn
        row = self._conn.execute(
            "SELECT * FROM nodes WHERE is_default=1 LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return Node(
            id=row["id"], label=row["label"], callsign=row["callsign"],
            ssid=row["ssid"], node_type=row["node_type"],
            is_default=bool(row["is_default"]),
        )
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_store/ -v
```

Expected: all schema/model tests pass.

- [ ] **Step 6: Commit**

```bash
git add open_packet/store/models.py open_packet/store/database.py tests/test_store/test_store.py
git commit -m "feat: SQLite store models and schema (operators, nodes, messages, bulletins)"
```

---

## Task 8: Store — CRUD Operations

**Files:**
- Create: `open_packet/store/store.py`
- Modify: `tests/test_store/test_store.py` (add CRUD tests)

- [ ] **Step 1: Add CRUD tests to the existing test file**

Append to `tests/test_store/test_store.py`:

```python
from open_packet.store.store import Store
from datetime import datetime, timezone


@pytest.fixture
def store(db):
    s = Store(db)
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    node = db.insert_node(Node(label="Home BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    return s, op, node


def test_store_and_list_messages(store):
    s, op, node = store
    msg = Message(
        operator_id=op.id, node_id=node.id, bbs_id="001",
        from_call="W0TEST", to_call="KD9ABC",
        subject="Hello", body="Test body",
        timestamp=datetime.now(timezone.utc),
    )
    s.save_message(msg)
    messages = s.list_messages(operator_id=op.id)
    assert len(messages) == 1
    assert messages[0].subject == "Hello"
    assert messages[0].read is False


def test_mark_message_read(store):
    s, op, node = store
    msg = Message(
        operator_id=op.id, node_id=node.id, bbs_id="002",
        from_call="W0TEST", to_call="KD9ABC",
        subject="Read me", body="Body",
        timestamp=datetime.now(timezone.utc),
    )
    saved = s.save_message(msg)
    s.mark_message_read(saved.id)
    fetched = s.get_message(saved.id)
    assert fetched.read is True


def test_soft_delete_message(store):
    s, op, node = store
    msg = Message(
        operator_id=op.id, node_id=node.id, bbs_id="003",
        from_call="W0TEST", to_call="KD9ABC",
        subject="Delete me", body="Body",
        timestamp=datetime.now(timezone.utc),
    )
    saved = s.save_message(msg)
    s.delete_message(saved.id)
    messages = s.list_messages(operator_id=op.id)
    # Deleted messages excluded from list
    assert all(m.id != saved.id for m in messages)


def test_store_and_list_bulletins(store):
    s, op, node = store
    bul = Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="B001",
        category="WX", from_call="W0WX",
        subject="Weather alert", body="Thunderstorms",
        timestamp=datetime.now(timezone.utc),
    )
    s.save_bulletin(bul)
    bulletins = s.list_bulletins(operator_id=op.id, category="WX")
    assert len(bulletins) == 1
    assert bulletins[0].subject == "Weather alert"


def test_message_not_duplicated(store):
    s, op, node = store
    msg = Message(
        operator_id=op.id, node_id=node.id, bbs_id="004",
        from_call="W0TEST", to_call="KD9ABC",
        subject="Unique", body="Body",
        timestamp=datetime.now(timezone.utc),
    )
    s.save_message(msg)
    s.save_message(msg)  # same bbs_id + node_id — should not duplicate
    messages = s.list_messages(operator_id=op.id)
    assert len(messages) == 1
```

- [ ] **Step 2: Run to verify new tests fail**

```bash
uv run pytest tests/test_store/ -v
```

Expected: new tests fail with ImportError on `Store`.

- [ ] **Step 3: Implement Store**

```python
# open_packet/store/store.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from open_packet.store.database import Database
from open_packet.store.models import Message, Bulletin


class Store:
    def __init__(self, db: Database):
        self._db = db

    @property
    def _conn(self):
        return self._db._conn

    def save_message(self, msg: Message) -> Message:
        assert self._conn
        # Avoid duplicates by bbs_id + node_id
        existing = self._conn.execute(
            "SELECT id FROM messages WHERE bbs_id=? AND node_id=?",
            (msg.bbs_id, msg.node_id),
        ).fetchone()
        if existing:
            return self.get_message(existing["id"])  # type: ignore

        cur = self._conn.execute(
            """INSERT INTO messages
               (operator_id, node_id, bbs_id, from_call, to_call, subject, body,
                timestamp, read, sent, deleted, synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                msg.operator_id, msg.node_id, msg.bbs_id, msg.from_call,
                msg.to_call, msg.subject, msg.body,
                msg.timestamp.isoformat(),
                int(msg.read), int(msg.sent), int(msg.deleted),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()
        return self.get_message(cur.lastrowid)  # type: ignore

    def get_message(self, id: int) -> Optional[Message]:
        assert self._conn
        row = self._conn.execute("SELECT * FROM messages WHERE id=?", (id,)).fetchone()
        if not row:
            return None
        return self._row_to_message(row)

    def list_messages(self, operator_id: int, include_deleted: bool = False) -> list[Message]:
        assert self._conn
        query = "SELECT * FROM messages WHERE operator_id=?"
        params: list = [operator_id]
        if not include_deleted:
            query += " AND deleted=0"
        query += " ORDER BY timestamp DESC"
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_message(r) for r in rows]

    def mark_message_read(self, id: int) -> None:
        assert self._conn
        self._conn.execute("UPDATE messages SET read=1 WHERE id=?", (id,))
        self._conn.commit()

    def mark_message_sent(self, id: int) -> None:
        assert self._conn
        self._conn.execute("UPDATE messages SET sent=1 WHERE id=?", (id,))
        self._conn.commit()

    def delete_message(self, id: int) -> None:
        assert self._conn
        self._conn.execute("UPDATE messages SET deleted=1 WHERE id=?", (id,))
        self._conn.commit()

    def save_bulletin(self, bul: Bulletin) -> Bulletin:
        assert self._conn
        existing = self._conn.execute(
            "SELECT id FROM bulletins WHERE bbs_id=? AND node_id=?",
            (bul.bbs_id, bul.node_id),
        ).fetchone()
        if existing:
            return self._get_bulletin(existing["id"])  # type: ignore

        cur = self._conn.execute(
            """INSERT INTO bulletins
               (operator_id, node_id, bbs_id, category, from_call, subject, body,
                timestamp, read, synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                bul.operator_id, bul.node_id, bul.bbs_id, bul.category,
                bul.from_call, bul.subject, bul.body,
                bul.timestamp.isoformat(), int(bul.read),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()
        return self._get_bulletin(cur.lastrowid)  # type: ignore

    def list_bulletins(self, operator_id: int, category: Optional[str] = None) -> list[Bulletin]:
        assert self._conn
        query = "SELECT * FROM bulletins WHERE operator_id=?"
        params: list = [operator_id]
        if category:
            query += " AND category=?"
            params.append(category)
        query += " ORDER BY timestamp DESC"
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_bulletin(r) for r in rows]

    def _get_bulletin(self, id: int) -> Optional[Bulletin]:
        assert self._conn
        row = self._conn.execute("SELECT * FROM bulletins WHERE id=?", (id,)).fetchone()
        if not row:
            return None
        return self._row_to_bulletin(row)

    def _row_to_message(self, row) -> Message:
        return Message(
            id=row["id"], operator_id=row["operator_id"], node_id=row["node_id"],
            bbs_id=row["bbs_id"], from_call=row["from_call"], to_call=row["to_call"],
            subject=row["subject"], body=row["body"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            read=bool(row["read"]), sent=bool(row["sent"]), deleted=bool(row["deleted"]),
        )

    def _row_to_bulletin(self, row) -> Bulletin:
        return Bulletin(
            id=row["id"], operator_id=row["operator_id"], node_id=row["node_id"],
            bbs_id=row["bbs_id"], category=row["category"], from_call=row["from_call"],
            subject=row["subject"], body=row["body"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            read=bool(row["read"]),
        )
```

- [ ] **Step 4: Run all store tests**

```bash
uv run pytest tests/test_store/ -v
```

Expected: all store tests pass.

- [ ] **Step 5: Commit**

```bash
git add open_packet/store/store.py tests/test_store/test_store.py
git commit -m "feat: Store CRUD operations for messages and bulletins"
```

---

## Task 9: NodeBase and BPQ Protocol Driver

**Files:**
- Create: `open_packet/node/base.py`
- Create: `open_packet/node/bpq.py`
- Create: `tests/test_node/test_bpq.py`

The BPQ BBS protocol is text-based. After connecting, the node sends a prompt (e.g., `BPQ>`). The client sends commands and reads responses terminated by the prompt. Key commands: `L` (list messages), `R <id>` (read), `S <callsign>` (send — prompts for subject, body ending with `/EX`), `K <id>` (kill/delete), `B` (bye/disconnect).

`BPQNode` operates over a `ConnectionBase`. It sends AX.25 UI frames carrying BBS command text and reads the text responses.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_node/test_bpq.py
import pytest
from unittest.mock import MagicMock, call
from open_packet.node.bpq import BPQNode, parse_message_list, parse_message_header
from open_packet.node.base import MessageHeader, NodeError
from open_packet.ax25.frame import encode_frame, decode_frame, AX25Frame


# --- Parser unit tests (no connection needed) ---

LIST_OUTPUT = """\
Msg  To        From      Date   Subject
1    KD9ABC    W0TEST    03/22  Hello there
2    KD9ABC    W0FOO     03/21  Test message
"""

def test_parse_message_list():
    headers = parse_message_list(LIST_OUTPUT)
    assert len(headers) == 2
    assert headers[0].bbs_id == "1"
    assert headers[0].to_call == "KD9ABC"
    assert headers[0].from_call == "W0TEST"
    assert headers[0].subject == "Hello there"


def test_parse_message_header_strips_whitespace():
    headers = parse_message_list(LIST_OUTPUT)
    assert headers[1].bbs_id == "2"
    assert headers[1].from_call == "W0FOO"
    assert headers[1].subject == "Test message"


def test_parse_empty_list():
    assert parse_message_list("No messages\n") == []


# --- BPQNode session tests using a mock connection ---

def make_mock_connection(responses: list[str], source: str = "KD9ABC",
                         source_ssid: int = 0, dest: str = "W0BPQ",
                         dest_ssid: int = 1):
    """
    Returns a mock ConnectionBase whose receive_frame returns AX.25 UI frames
    carrying each response string in sequence, then returns b"" (timeout).
    """
    conn = MagicMock()
    frames = [
        encode_frame(AX25Frame(
            destination=source, destination_ssid=source_ssid,
            source=dest, source_ssid=dest_ssid,
            info=r.encode(),
        ))
        for r in responses
    ] + [b""]

    conn.receive_frame.side_effect = frames
    return conn


def test_bpqnode_list_messages():
    responses = [
        "BPQ> ",  # initial prompt
        LIST_OUTPUT + "BPQ> ",  # response to L command
    ]
    conn = make_mock_connection(responses)
    node = BPQNode(connection=conn, node_callsign="W0BPQ", node_ssid=1,
                   my_callsign="KD9ABC", my_ssid=0)
    node.connect_node()
    headers = node.list_messages()
    assert len(headers) == 2


def test_bpqnode_delete_message():
    responses = [
        "BPQ> ",
        "Message 1 killed\nBPQ> ",
    ]
    conn = make_mock_connection(responses)
    node = BPQNode(connection=conn, node_callsign="W0BPQ", node_ssid=1,
                   my_callsign="KD9ABC", my_ssid=0)
    node.connect_node()
    node.delete_message("1")  # should not raise
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_node/ -v
```

Expected: ImportError.

- [ ] **Step 3: Implement NodeBase**

```python
# open_packet/node/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


class NodeError(Exception):
    pass


@dataclass
class MessageHeader:
    bbs_id: str
    to_call: str
    from_call: str
    subject: str
    date_str: str = ""


@dataclass
class Message:
    header: MessageHeader
    body: str
    timestamp: Optional[datetime] = None


class NodeBase(ABC):
    @abstractmethod
    def connect_node(self) -> None: ...

    @abstractmethod
    def list_messages(self) -> list[MessageHeader]: ...

    @abstractmethod
    def read_message(self, bbs_id: str) -> Message: ...

    @abstractmethod
    def send_message(self, to_call: str, subject: str, body: str) -> None: ...

    @abstractmethod
    def delete_message(self, bbs_id: str) -> None: ...

    @abstractmethod
    def list_bulletins(self, category: str = "") -> list[MessageHeader]: ...

    @abstractmethod
    def read_bulletin(self, bbs_id: str) -> Message: ...
```

- [ ] **Step 4: Implement BPQNode**

```python
# open_packet/node/bpq.py
from __future__ import annotations
import re
import time
from open_packet.link.base import ConnectionBase
from open_packet.node.base import NodeBase, NodeError, MessageHeader, Message
from open_packet.ax25.frame import AX25Frame, encode_frame, decode_frame

PROMPT = "BPQ>"
TIMEOUT = 10.0


def parse_message_list(text: str) -> list[MessageHeader]:
    headers = []
    for line in text.splitlines():
        # Match lines starting with a message number
        m = re.match(
            r'^\s*(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(.+)$', line
        )
        if m:
            headers.append(MessageHeader(
                bbs_id=m.group(1),
                to_call=m.group(2).strip(),
                from_call=m.group(3).strip(),
                date_str=m.group(4).strip(),
                subject=m.group(5).strip(),
            ))
    return headers


def parse_message_header(line: str) -> MessageHeader | None:
    m = re.match(r'^\s*(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(.+)$', line)
    if not m:
        return None
    return MessageHeader(
        bbs_id=m.group(1), to_call=m.group(2).strip(),
        from_call=m.group(3).strip(), date_str=m.group(4).strip(),
        subject=m.group(5).strip(),
    )


class BPQNode(NodeBase):
    def __init__(self, connection: ConnectionBase, node_callsign: str,
                 node_ssid: int, my_callsign: str, my_ssid: int):
        self._conn = connection
        self._node_callsign = node_callsign
        self._node_ssid = node_ssid
        self._my_callsign = my_callsign
        self._my_ssid = my_ssid

    def _send_text(self, text: str) -> None:
        frame = AX25Frame(
            destination=self._node_callsign,
            destination_ssid=self._node_ssid,
            source=self._my_callsign,
            source_ssid=self._my_ssid,
            info=(text + "\r").encode(),
        )
        self._conn.send_frame(encode_frame(frame))

    def _recv_until_prompt(self, timeout: float = TIMEOUT) -> str:
        buffer = ""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = self._conn.receive_frame(timeout=1.0)
            if raw:
                frame = decode_frame(raw)
                buffer += frame.info.decode(errors="replace")
                if PROMPT in buffer:
                    break
        return buffer

    def connect_node(self) -> None:
        response = self._recv_until_prompt()
        if PROMPT not in response:
            raise NodeError(f"No BPQ prompt received. Got: {response!r}")

    def list_messages(self) -> list[MessageHeader]:
        self._send_text("L")
        response = self._recv_until_prompt()
        return parse_message_list(response)

    def read_message(self, bbs_id: str) -> Message:
        self._send_text(f"R {bbs_id}")
        response = self._recv_until_prompt()
        lines = response.splitlines()
        # First few lines are headers, body follows blank line
        body_lines = []
        in_body = False
        header = MessageHeader(bbs_id=bbs_id, to_call="", from_call="", subject="")
        for line in lines:
            if not in_body and line.strip() == "":
                in_body = True
                continue
            if in_body and PROMPT not in line:
                body_lines.append(line)
        return Message(header=header, body="\n".join(body_lines).strip())

    def send_message(self, to_call: str, subject: str, body: str) -> None:
        self._send_text(f"S {to_call}")
        self._recv_until_prompt(timeout=5.0)  # prompt for subject
        self._send_text(subject)
        self._recv_until_prompt(timeout=5.0)  # prompt for body
        for line in body.splitlines():
            self._send_text(line)
        self._send_text("/EX")
        self._recv_until_prompt()

    def delete_message(self, bbs_id: str) -> None:
        self._send_text(f"K {bbs_id}")
        self._recv_until_prompt()

    def list_bulletins(self, category: str = "") -> list[MessageHeader]:
        cmd = f"LB {category}".strip()
        self._send_text(cmd)
        response = self._recv_until_prompt()
        return parse_message_list(response)

    def read_bulletin(self, bbs_id: str) -> Message:
        return self.read_message(bbs_id)
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_node/ -v
```

Expected: all node tests pass.

- [ ] **Step 6: Commit**

```bash
git add open_packet/node/ tests/test_node/
git commit -m "feat: NodeBase ABC and BPQNode BBS protocol driver"
```

---

## Task 10: Engine — Commands, Events, and Core Engine

**Files:**
- Create: `open_packet/engine/commands.py`
- Create: `open_packet/engine/events.py`
- Create: `open_packet/engine/engine.py`
- Create: `tests/test_engine/test_engine.py`

The engine runs in a daemon thread. It reads `Command` objects from a `queue.Queue`, executes operations, and puts `Event` objects on an outbound `queue.Queue`. In-memory state: `connection_status`, `last_sync_time`, `messages_last_sync`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_engine/test_engine.py
import queue
import time
import tempfile
import os
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from open_packet.engine.engine import Engine
from open_packet.engine.commands import CheckMailCommand, DisconnectCommand
from open_packet.engine.events import (
    ConnectionStatusEvent, SyncCompleteEvent, ErrorEvent, ConnectionStatus
)
from open_packet.store.database import Database
from open_packet.store.store import Store
from open_packet.store.models import Operator, Node, Message, Bulletin
from open_packet.node.base import MessageHeader, Message as NodeMessage


@pytest.fixture
def db_and_store():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    db = Database(f.name)
    db.initialize()
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    store = Store(db)
    yield db, store, op, node
    db.close()
    os.unlink(f.name)


def make_mock_node(messages=None, bulletins=None):
    node = MagicMock()
    node.list_messages.return_value = messages or []
    node.list_bulletins.return_value = bulletins or []
    node.read_message.return_value = NodeMessage(
        header=MagicMock(bbs_id="1", from_call="W0TEST", to_call="KD9ABC",
                          subject="Hello", date_str="03/22"),
        body="Test body",
    )
    return node


def test_engine_check_mail_emits_sync_complete(db_and_store):
    db, store, op, node_record = db_and_store
    mock_node = make_mock_node(
        messages=[MessageHeader(bbs_id="1", to_call="KD9ABC",
                                from_call="W0TEST", subject="Hello")]
    )
    mock_connection = MagicMock()

    cmd_queue = queue.Queue()
    evt_queue = queue.Queue()

    engine = Engine(
        command_queue=cmd_queue,
        event_queue=evt_queue,
        store=store,
        operator=op,
        node_record=node_record,
        connection=mock_connection,
        node=mock_node,
    )
    engine.start()

    cmd_queue.put(CheckMailCommand())
    # Wait for sync complete event
    events = []
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            events.append(evt_queue.get(timeout=0.5))
        except queue.Empty:
            break

    engine.stop()

    event_types = [type(e).__name__ for e in events]
    assert "SyncCompleteEvent" in event_types


def test_engine_emits_connection_status(db_and_store):
    db, store, op, node_record = db_and_store
    mock_node = make_mock_node()
    mock_connection = MagicMock()

    cmd_queue = queue.Queue()
    evt_queue = queue.Queue()

    engine = Engine(
        command_queue=cmd_queue, event_queue=evt_queue,
        store=store, operator=op, node_record=node_record,
        connection=mock_connection, node=mock_node,
    )
    engine.start()
    cmd_queue.put(CheckMailCommand())

    events = []
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            events.append(evt_queue.get(timeout=0.5))
        except queue.Empty:
            break

    engine.stop()
    status_events = [e for e in events if isinstance(e, ConnectionStatusEvent)]
    assert len(status_events) >= 1
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_engine/ -v
```

Expected: ImportError.

- [ ] **Step 3: Implement commands**

```python
# open_packet/engine/commands.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class ConnectCommand:
    pass


@dataclass
class DisconnectCommand:
    pass


@dataclass
class CheckMailCommand:
    pass


@dataclass
class SendMessageCommand:
    to_call: str
    subject: str
    body: str


@dataclass
class DeleteMessageCommand:
    message_id: int  # local DB id
    bbs_id: str      # BBS message id for the node command


Command = ConnectCommand | DisconnectCommand | CheckMailCommand | SendMessageCommand | DeleteMessageCommand
```

- [ ] **Step 4: Implement events**

```python
# open_packet/engine/events.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class ConnectionStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    SYNCING = "syncing"
    ERROR = "error"


@dataclass
class ConnectionStatusEvent:
    status: ConnectionStatus
    detail: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MessageReceivedEvent:
    message_id: int
    from_call: str
    subject: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SyncCompleteEvent:
    messages_retrieved: int
    messages_sent: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ErrorEvent:
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


Event = ConnectionStatusEvent | MessageReceivedEvent | SyncCompleteEvent | ErrorEvent
```

- [ ] **Step 5: Implement Engine**

```python
# open_packet/engine/engine.py
from __future__ import annotations
import logging
import queue
import threading
from datetime import datetime, timezone
from typing import Optional

from open_packet.engine.commands import (
    Command, CheckMailCommand, ConnectCommand, DisconnectCommand,
    SendMessageCommand, DeleteMessageCommand,
)
from open_packet.engine.events import (
    ConnectionStatusEvent, ConnectionStatus, MessageReceivedEvent,
    SyncCompleteEvent, ErrorEvent,
)
from open_packet.link.base import ConnectionBase
from open_packet.node.base import NodeBase
from open_packet.store.models import Operator, Node, Message, Bulletin
from open_packet.store.store import Store

logger = logging.getLogger(__name__)


class Engine:
    def __init__(
        self,
        command_queue: queue.Queue,
        event_queue: queue.Queue,
        store: Store,
        operator: Operator,
        node_record: Node,
        connection: ConnectionBase,
        node: NodeBase,
    ):
        self._cmd_queue = command_queue
        self._evt_queue = event_queue
        self._store = store
        self._operator = operator
        self._node_record = node_record
        self._connection = connection
        self._node = node

        # In-memory state
        self._status = ConnectionStatus.DISCONNECTED
        self._last_sync: Optional[datetime] = None
        self._messages_last_sync = 0

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=5.0)

    @property
    def last_sync(self) -> Optional[datetime]:
        return self._last_sync

    @property
    def status(self) -> ConnectionStatus:
        return self._status

    def _emit(self, event) -> None:
        self._evt_queue.put(event)

    def _set_status(self, status: ConnectionStatus, detail: str = "") -> None:
        self._status = status
        self._emit(ConnectionStatusEvent(status=status, detail=detail))

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                cmd = self._cmd_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self._handle(cmd)
            except Exception as e:
                logger.exception("Engine error handling %s", type(cmd).__name__)
                self._emit(ErrorEvent(message=str(e)))
                self._set_status(ConnectionStatus.ERROR, str(e))

    def _handle(self, cmd: Command) -> None:
        if isinstance(cmd, CheckMailCommand):
            self._do_check_mail()
        elif isinstance(cmd, SendMessageCommand):
            self._do_send_message(cmd)
        elif isinstance(cmd, DeleteMessageCommand):
            self._do_delete_message(cmd)
        elif isinstance(cmd, ConnectCommand):
            self._do_connect()
        elif isinstance(cmd, DisconnectCommand):
            self._do_disconnect()

    def _do_connect(self) -> None:
        self._set_status(ConnectionStatus.CONNECTING)
        self._connection.connect(
            callsign=self._node_record.callsign,
            ssid=self._node_record.ssid,
        )
        self._node.connect_node()
        self._set_status(ConnectionStatus.CONNECTED)

    def _do_disconnect(self) -> None:
        self._connection.disconnect()
        self._set_status(ConnectionStatus.DISCONNECTED)

    def _do_check_mail(self) -> None:
        self._set_status(ConnectionStatus.CONNECTING)
        try:
            self._connection.connect(
                callsign=self._node_record.callsign,
                ssid=self._node_record.ssid,
            )
            self._node.connect_node()
            self._set_status(ConnectionStatus.SYNCING)

            retrieved = 0
            headers = self._node.list_messages()
            for header in headers:
                msg = self._node.read_message(header.bbs_id)
                now = datetime.now(timezone.utc)
                saved = self._store.save_message(Message(
                    operator_id=self._operator.id,
                    node_id=self._node_record.id,
                    bbs_id=header.bbs_id,
                    from_call=header.from_call,
                    to_call=header.to_call,
                    subject=header.subject,
                    body=msg.body,
                    timestamp=now,
                ))
                if saved:
                    retrieved += 1
                    self._emit(MessageReceivedEvent(
                        message_id=saved.id,
                        from_call=header.from_call,
                        subject=header.subject,
                    ))

            # Send any queued outbound messages
            sent = 0
            outbound = self._store.list_messages(
                operator_id=self._operator.id
            )
            for m in outbound:
                if not m.sent and not m.deleted:
                    self._node.send_message(m.to_call, m.subject, m.body)
                    self._store.mark_message_sent(m.id)
                    sent += 1

            self._last_sync = datetime.now(timezone.utc)
            self._messages_last_sync = retrieved
            self._emit(SyncCompleteEvent(
                messages_retrieved=retrieved,
                messages_sent=sent,
            ))
        finally:
            self._connection.disconnect()
            self._set_status(ConnectionStatus.DISCONNECTED)

    def _do_send_message(self, cmd: SendMessageCommand) -> None:
        now = datetime.now(timezone.utc)
        self._store.save_message(Message(
            operator_id=self._operator.id,
            node_id=self._node_record.id,
            bbs_id="",  # not yet assigned by BBS
            from_call=f"{self._operator.callsign}-{self._operator.ssid}",
            to_call=cmd.to_call,
            subject=cmd.subject,
            body=cmd.body,
            timestamp=now,
            sent=False,
        ))

    def _do_delete_message(self, cmd: DeleteMessageCommand) -> None:
        self._store.delete_message(cmd.message_id)
```

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/test_engine/ -v
```

Expected: engine tests pass.

- [ ] **Step 7: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass with no errors.

- [ ] **Step 8: Commit**

```bash
git add open_packet/engine/ tests/test_engine/
git commit -m "feat: engine with command/event queues and check-mail orchestration"
```

---

## Task 11: UIBase and TUI Widgets

**Files:**
- Create: `open_packet/ui/base.py`
- Create: `open_packet/ui/tui/widgets/status_bar.py`
- Create: `open_packet/ui/tui/widgets/folder_tree.py`
- Create: `open_packet/ui/tui/widgets/message_list.py`
- Create: `open_packet/ui/tui/widgets/message_body.py`
- Create: `open_packet/ui/tui/widgets/console_panel.py`
- Create: `tests/test_ui/test_tui.py`

- [ ] **Step 1: Implement UIBase**

```python
# open_packet/ui/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from open_packet.engine.commands import Command
from open_packet.engine.events import Event


class UIBase(ABC):
    @abstractmethod
    def send_command(self, cmd: Command) -> None: ...

    @abstractmethod
    def on_event(self, event: Event) -> None: ...
```

- [ ] **Step 2: Implement StatusBar widget**

```python
# open_packet/ui/tui/widgets/status_bar.py
from __future__ import annotations
from textual.widget import Widget
from textual.reactive import reactive
from open_packet.engine.events import ConnectionStatus


class StatusBar(Widget):
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }
    """

    callsign: reactive[str] = reactive("---")
    status: reactive[ConnectionStatus] = reactive(ConnectionStatus.DISCONNECTED)
    last_sync: reactive[str] = reactive("Never")

    def render(self) -> str:
        status_icon = {
            ConnectionStatus.DISCONNECTED: "○",
            ConnectionStatus.CONNECTING: "◎",
            ConnectionStatus.CONNECTED: "●",
            ConnectionStatus.SYNCING: "⟳",
            ConnectionStatus.ERROR: "✗",
        }.get(self.status, "?")
        return (
            f"open-packet  {self.callsign}  "
            f"{status_icon}  {self.status.value.title()}  "
            f"| Last sync: {self.last_sync}"
        )
```

- [ ] **Step 3: Implement FolderTree widget**

```python
# open_packet/ui/tui/widgets/folder_tree.py
from __future__ import annotations
from textual.widgets import Tree
from textual.widgets.tree import TreeNode
from textual.message import Message as TMessage


class FolderTree(Tree):
    DEFAULT_CSS = """
    FolderTree {
        width: 18;
        border-right: solid $primary;
    }
    """

    class FolderSelected(TMessage):
        def __init__(self, folder: str, category: str = "") -> None:
            self.folder = folder
            self.category = category
            super().__init__()

    def on_mount(self) -> None:
        self.root.expand()
        self.root.add_leaf("Inbox")
        self.root.add_leaf("Sent")
        bulletins = self.root.add("Bulletins")
        bulletins.add_leaf("WX")
        bulletins.add_leaf("NTS")
        bulletins.add_leaf("ALL")

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        label = str(event.node.label)
        parent = event.node.parent
        if parent and str(parent.label) == "Bulletins":
            self.post_message(self.FolderSelected("Bulletins", category=label))
        else:
            self.post_message(self.FolderSelected(label))
```

- [ ] **Step 4: Implement MessageList widget**

```python
# open_packet/ui/tui/widgets/message_list.py
from __future__ import annotations
from textual.widgets import DataTable
from textual.message import Message as TMessage
from open_packet.store.models import Message


class MessageList(DataTable):
    DEFAULT_CSS = """
    MessageList {
        height: 1fr;
    }
    """

    class MessageSelected(TMessage):
        def __init__(self, message: Message) -> None:
            self.message = message
            super().__init__()

    def on_mount(self) -> None:
        self.add_columns("  ", "Subject", "From", "Date")
        self.cursor_type = "row"

    def load_messages(self, messages: list[Message]) -> None:
        self.clear()
        self._messages = messages
        for msg in messages:
            read_marker = " " if msg.read else "●"
            date_str = msg.timestamp.strftime("%m/%d %H:%M") if msg.timestamp else ""
            self.add_row(read_marker, msg.subject[:40], msg.from_call, date_str)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if hasattr(self, "_messages") and event.cursor_row < len(self._messages):
            self.post_message(self.MessageSelected(self._messages[event.cursor_row]))
```

- [ ] **Step 5: Implement MessageBody widget**

```python
# open_packet/ui/tui/widgets/message_body.py
from __future__ import annotations
from textual.widgets import RichLog
from open_packet.store.models import Message


class MessageBody(RichLog):
    DEFAULT_CSS = """
    MessageBody {
        height: 1fr;
        border-top: solid $primary;
        padding: 0 1;
    }
    """

    def show_message(self, message: Message) -> None:
        self.clear()
        self.write(f"From:    {message.from_call}")
        self.write(f"To:      {message.to_call}")
        self.write(f"Subject: {message.subject}")
        self.write("─" * 40)
        self.write(message.body)

    def clear_message(self) -> None:
        self.clear()
```

- [ ] **Step 6: Implement ConsolePanel widget**

```python
# open_packet/ui/tui/widgets/console_panel.py
from __future__ import annotations
from collections import deque
from datetime import datetime
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import RichLog, Label, Input
from textual.containers import Vertical


class ConsolePanel(Widget):
    DEFAULT_CSS = """
    ConsolePanel {
        height: 8;
        border-top: solid $primary;
    }
    ConsolePanel Label {
        background: $primary;
        width: 100%;
        padding: 0 1;
        height: 1;
    }
    ConsolePanel RichLog {
        height: 1fr;
    }
    """

    def __init__(self, buffer_size: int = 500, **kwargs):
        super().__init__(**kwargs)
        self._buffer_size = buffer_size
        self._log_file = None
        self._buffer: deque = deque(maxlen=buffer_size)

    def compose(self) -> ComposeResult:
        yield Label("CONSOLE")
        yield RichLog(id="console_log", highlight=False, markup=False)

    def set_log_file(self, path: str) -> None:
        import logging
        from logging.handlers import RotatingFileHandler
        handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=3)
        self._log_file = logging.getLogger("open_packet.console")
        self._log_file.addHandler(handler)
        self._log_file.setLevel(logging.DEBUG)

    def log_frame(self, direction: str, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"{ts} {direction} {text}"
        self._buffer.append(line)
        log_widget = self.query_one("#console_log", RichLog)
        log_widget.write(line)
        if self._log_file:
            self._log_file.debug(line)
```

- [ ] **Step 7: Write TUI widget tests**

```python
# tests/test_ui/test_tui.py
import pytest
from textual.testing import AppTest
from open_packet.ui.tui.app import OpenPacketApp
from open_packet.config.config import AppConfig, TCPConnectionConfig, StoreConfig, UIConfig


@pytest.fixture
def app_config(tmp_path):
    return AppConfig(
        connection=TCPConnectionConfig(type="kiss_tcp", host="localhost", port=8001),
        store=StoreConfig(
            db_path=str(tmp_path / "test.db"),
            export_path=str(tmp_path / "export"),
        ),
        ui=UIConfig(),
    )


@pytest.mark.asyncio
async def test_app_mounts(app_config):
    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        assert app.query_one("StatusBar") is not None
        assert app.query_one("FolderTree") is not None
        assert app.query_one("MessageList") is not None
        assert app.query_one("MessageBody") is not None


@pytest.mark.asyncio
async def test_console_toggle(app_config):
    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        # Console starts hidden by default
        console = app.query_one("ConsolePanel")
        assert not console.display
        # Backtick toggles console
        await pilot.press("`")
        assert console.display
        await pilot.press("`")
        assert not console.display
```

- [ ] **Step 8: Run to verify failure (app not yet implemented)**

```bash
uv run pytest tests/test_ui/ -v
```

Expected: ImportError on `OpenPacketApp`.

- [ ] **Step 9: Commit widgets**

```bash
git add open_packet/ui/ tests/test_ui/
git commit -m "feat: UIBase ABC and TUI widget stubs (status bar, folder tree, message list, body, console)"
```

---

## Task 12: TUI App and Screens

**Files:**
- Create: `open_packet/ui/tui/app.py`
- Create: `open_packet/ui/tui/screens/main.py`
- Create: `open_packet/ui/tui/screens/compose.py`

- [ ] **Step 1: Implement ComposeScreen**

```python
# open_packet/ui/tui/screens/compose.py
from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, TextArea
from textual.containers import Vertical, Horizontal
from open_packet.engine.commands import SendMessageCommand


class ComposeScreen(ModalScreen):
    DEFAULT_CSS = """
    ComposeScreen {
        align: center middle;
    }
    ComposeScreen Vertical {
        width: 70;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    ComposeScreen TextArea {
        height: 10;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("New Message", id="compose_title")
            yield Label("To:")
            yield Input(placeholder="Callsign", id="to_field")
            yield Label("Subject:")
            yield Input(placeholder="Subject", id="subject_field")
            yield Label("Body:")
            yield TextArea(id="body_field")
            with Horizontal():
                yield Button("Send", variant="primary", id="send_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.dismiss(None)
        elif event.button.id == "send_btn":
            to_call = self.query_one("#to_field", Input).value.strip()
            subject = self.query_one("#subject_field", Input).value.strip()
            body = self.query_one("#body_field", TextArea).text.strip()
            if to_call and subject:
                self.dismiss(SendMessageCommand(
                    to_call=to_call, subject=subject, body=body
                ))
```

- [ ] **Step 2: Implement MainScreen**

```python
# open_packet/ui/tui/screens/main.py
from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Horizontal, Vertical
from open_packet.ui.tui.widgets.status_bar import StatusBar
from open_packet.ui.tui.widgets.folder_tree import FolderTree
from open_packet.ui.tui.widgets.message_list import MessageList
from open_packet.ui.tui.widgets.message_body import MessageBody
from open_packet.ui.tui.widgets.console_panel import ConsolePanel


class MainScreen(Screen):
    DEFAULT_CSS = """
    MainScreen {
        layout: vertical;
    }
    #main_area {
        height: 1fr;
    }
    #right_pane {
        layout: vertical;
        width: 1fr;
    }
    """

    BINDINGS = [
        ("c", "check_mail", "Check Mail"),
        ("n", "new_message", "New"),
        ("d", "delete_message", "Delete"),
        ("r", "reply_message", "Reply"),
        ("`", "toggle_console", "Console"),
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield StatusBar(id="status_bar")
        with Horizontal(id="main_area"):
            yield FolderTree("Folders", id="folder_tree")
            with Vertical(id="right_pane"):
                yield MessageList(id="message_list")
                yield MessageBody(id="message_body")
        yield ConsolePanel(id="console_panel")

    def on_mount(self) -> None:
        self.query_one("ConsolePanel").display = self.app.config.ui.console_visible

    def action_toggle_console(self) -> None:
        panel = self.query_one("ConsolePanel")
        panel.display = not panel.display

    def action_check_mail(self) -> None:
        self.app.check_mail()

    def action_new_message(self) -> None:
        self.app.push_screen("compose")

    def action_delete_message(self) -> None:
        self.app.delete_selected_message()

    def action_reply_message(self) -> None:
        self.app.reply_to_selected()

    def action_quit(self) -> None:
        self.app.exit()
```

- [ ] **Step 3: Implement OpenPacketApp**

```python
# open_packet/ui/tui/app.py
from __future__ import annotations
import logging
import os
import queue
import threading
from typing import Optional

from textual.app import App, ComposeResult

from open_packet.config.config import AppConfig, load_config
from open_packet.engine.commands import (
    CheckMailCommand, DeleteMessageCommand, SendMessageCommand
)
from open_packet.engine.engine import Engine
from open_packet.engine.events import (
    ConnectionStatusEvent, MessageReceivedEvent, SyncCompleteEvent,
    ErrorEvent, ConnectionStatus,
)
from open_packet.link.kiss import KISSLink
from open_packet.node.bpq import BPQNode
from open_packet.store.database import Database
from open_packet.store.store import Store
from open_packet.transport.tcp import TCPTransport
from open_packet.transport.serial import SerialTransport
from open_packet.ui.tui.screens.compose import ComposeScreen
from open_packet.ui.tui.screens.main import MainScreen

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "~/.config/open-packet/config.yaml"


def _setup_logging(log_path: str) -> None:
    from logging.handlers import RotatingFileHandler
    os.makedirs(os.path.dirname(os.path.expanduser(log_path)), exist_ok=True)
    handler = RotatingFileHandler(
        os.path.expanduser(log_path), maxBytes=5_000_000, backupCount=5
    )
    logging.basicConfig(
        level=logging.INFO,
        handlers=[handler],
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )


class OpenPacketApp(App):
    SCREENS = {"main": MainScreen, "compose": ComposeScreen}
    TITLE = "open-packet"

    def __init__(self, config: AppConfig, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self._cmd_queue: queue.Queue = queue.Queue()
        self._evt_queue: queue.Queue = queue.Queue()
        self._engine: Optional[Engine] = None
        self._selected_message = None

    def on_mount(self) -> None:
        self._init_engine()
        self.push_screen("main")
        self.set_interval(0.1, self._poll_events)

    def _init_engine(self) -> None:
        db_path = os.path.expanduser(self.config.store.db_path)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        db = Database(db_path)
        db.initialize()
        store = Store(db)

        operator = db.get_default_operator()
        node_record = db.get_default_node()
        if not operator or not node_record:
            self.notify("No operator or node configured. Add them to the database.", severity="error")
            return

        # Build transport + link
        conn_cfg = self.config.connection
        if conn_cfg.type == "kiss_tcp":
            transport = TCPTransport(host=conn_cfg.host, port=conn_cfg.port)
        else:
            transport = SerialTransport(device=conn_cfg.device, baud=conn_cfg.baud)

        connection = KISSLink(transport=transport)
        node = BPQNode(
            connection=connection,
            node_callsign=node_record.callsign,
            node_ssid=node_record.ssid,
            my_callsign=operator.callsign,
            my_ssid=operator.ssid,
        )

        self._engine = Engine(
            command_queue=self._cmd_queue,
            event_queue=self._evt_queue,
            store=store,
            operator=operator,
            node_record=node_record,
            connection=connection,
            node=node,
        )
        self._engine.start()

    def _poll_events(self) -> None:
        while not self._evt_queue.empty():
            try:
                event = self._evt_queue.get_nowait()
                self._handle_event(event)
            except queue.Empty:
                break

    def _handle_event(self, event) -> None:
        try:
            status_bar = self.query_one("StatusBar")
        except Exception:
            return

        if isinstance(event, ConnectionStatusEvent):
            status_bar.status = event.status
            if event.status == ConnectionStatus.ERROR:
                self.notify(f"Error: {event.detail}", severity="error")
        elif isinstance(event, SyncCompleteEvent):
            from datetime import datetime
            status_bar.last_sync = datetime.now().strftime("%H:%M")
            self.notify(
                f"Sync complete: {event.messages_retrieved} new, {event.messages_sent} sent"
            )
            self._refresh_message_list()
        elif isinstance(event, ErrorEvent):
            self.notify(f"Error: {event.message}", severity="error")

    def _refresh_message_list(self) -> None:
        # Implemented in Task 13 — wires store queries into the TUI
        pass

    def check_mail(self) -> None:
        if self._engine:
            self._cmd_queue.put(CheckMailCommand())

    def delete_selected_message(self) -> None:
        if self._selected_message and self._engine:
            self._cmd_queue.put(DeleteMessageCommand(
                message_id=self._selected_message.id,
                bbs_id=self._selected_message.bbs_id,
            ))

    def reply_to_selected(self) -> None:
        if self._selected_message:
            self.push_screen(ComposeScreen())

    def on_compose_screen_dismiss(self, result) -> None:
        if result and isinstance(result, SendMessageCommand):
            self._cmd_queue.put(result)

    def on_message_list_message_selected(self, event) -> None:
        self._selected_message = event.message
        try:
            self.query_one("MessageBody").show_message(event.message)
        except Exception:
            pass

    def on_folder_tree_folder_selected(self, event) -> None:
        pass  # Future: reload message list for selected folder


def main() -> None:
    import sys
    config_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CONFIG_PATH
    _setup_logging("~/.local/share/open-packet/open-packet.log")
    try:
        config = load_config(os.path.expanduser(config_path))
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        sys.exit(1)
    app = OpenPacketApp(config=config)
    app.run()
```

- [ ] **Step 4: Run TUI tests**

```bash
uv run pytest tests/test_ui/ -v
```

Expected: TUI mount and console toggle tests pass.

- [ ] **Step 5: Run the full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add open_packet/ui/tui/ tests/test_ui/
git commit -m "feat: TUI app with main screen, compose screen, and engine integration"
```

---

## Task 13: Wire TUI Folder Selection and Message List Refresh

**Files:**
- Modify: `open_packet/ui/tui/app.py`
- Modify: `open_packet/store/store.py` (add `list_sent_messages`, `list_bulletins_by_category`)
- Modify: `tests/test_ui/test_tui.py`

The TUI currently has two broken interactions: (1) selecting a folder doesn't load messages, and (2) after `SyncCompleteEvent` the inbox doesn't update. This task wires both.

The app needs a reference to the `Store` and the active `Operator` so it can query the right messages for the selected folder. Store these on `OpenPacketApp` during `_init_engine`.

- [ ] **Step 1: Expose store and operator on the app**

In `open_packet/ui/tui/app.py`, in `_init_engine`, after creating `store`, `op`, `node_record`, add:

```python
self._store = store
self._active_operator = operator
self._active_folder = "Inbox"
self._active_category = ""
```

- [ ] **Step 2: Implement `_refresh_message_list`**

Replace the stub in `OpenPacketApp`:

```python
def _refresh_message_list(self) -> None:
    if not hasattr(self, "_store") or not self._store:
        return
    try:
        msg_list = self.query_one("MessageList")
        folder = getattr(self, "_active_folder", "Inbox")
        category = getattr(self, "_active_category", "")
        operator_id = self._active_operator.id

        if folder == "Inbox":
            messages = [
                m for m in self._store.list_messages(operator_id=operator_id)
                if not m.sent
            ]
        elif folder == "Sent":
            messages = [
                m for m in self._store.list_messages(operator_id=operator_id)
                if m.sent
            ]
        elif folder == "Bulletins":
            messages = self._store.list_bulletins(
                operator_id=operator_id,
                category=category or None,
            )
        else:
            messages = []

        msg_list.load_messages(messages)
    except Exception:
        logger.exception("Failed to refresh message list")
```

- [ ] **Step 3: Implement `on_folder_tree_folder_selected`**

Replace the stub in `OpenPacketApp`:

```python
def on_folder_tree_folder_selected(self, event) -> None:
    self._active_folder = event.folder
    self._active_category = getattr(event, "category", "")
    self._refresh_message_list()
```

- [ ] **Step 4: Call `_refresh_message_list` after sync**

In `_handle_event`, in the `SyncCompleteEvent` branch, add the refresh call:

```python
elif isinstance(event, SyncCompleteEvent):
    from datetime import datetime
    status_bar.last_sync = datetime.now().strftime("%H:%M")
    self.notify(
        f"Sync complete: {event.messages_retrieved} new, {event.messages_sent} sent"
    )
    self._refresh_message_list()   # ← add this
```

- [ ] **Step 5: Also refresh on mount**

In `OpenPacketApp.on_mount`, after `self.push_screen("main")`:

```python
self.call_after_refresh(self._refresh_message_list)
```

- [ ] **Step 6: Add TUI wiring tests**

Append to `tests/test_ui/test_tui.py`:

```python
@pytest.mark.asyncio
async def test_folder_selection_loads_inbox(app_config, tmp_path):
    """Selecting Inbox in the folder tree populates the message list."""
    from open_packet.store.database import Database
    from open_packet.store.store import Store
    from open_packet.store.models import Operator, Node, Message
    from datetime import datetime, timezone

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    store = Store(db)
    store.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="001",
        from_call="W0TEST", to_call="KD9ABC", subject="Test",
        body="Body", timestamp=datetime.now(timezone.utc),
    ))

    # Patch app_config to use the pre-populated db
    app_config.store.db_path = str(tmp_path / "test.db")
    app = OpenPacketApp(config=app_config)
    # Inject store/operator directly to bypass engine init
    app._store = store
    app._active_operator = op
    app._active_folder = "Inbox"
    app._active_category = ""

    async with app.run_test() as pilot:
        app._refresh_message_list()
        await pilot.pause()
        msg_list = app.query_one("MessageList")
        assert msg_list.row_count == 1
```

- [ ] **Step 7: Run TUI tests**

```bash
uv run pytest tests/test_ui/ -v
```

Expected: all TUI tests pass including the new wiring test.

- [ ] **Step 8: Commit**

```bash
git add open_packet/ui/tui/app.py tests/test_ui/test_tui.py
git commit -m "feat: wire folder selection and post-sync message list refresh in TUI"
```

---

## Task 14: Flat-File Export

**Files:**
- Create: `open_packet/store/exporter.py`
- Modify: `tests/test_store/test_store.py` (add export tests)

The spec requires optional export of messages and bulletins to a directory tree of `.txt` files. This is enabled when `store.export_path` is set in config. The exporter writes one file per message/bulletin on demand (called after each sync).

- [ ] **Step 1: Add export tests**

Append to `tests/test_store/test_store.py`:

```python
from open_packet.store.exporter import export_messages, export_bulletins
import os


def test_export_messages_writes_files(store, tmp_path):
    s, op, node = store
    msg = Message(
        operator_id=op.id, node_id=node.id, bbs_id="005",
        from_call="W0TEST", to_call="KD9ABC",
        subject="Export test", body="Export body",
        timestamp=datetime(2026, 3, 22, 12, 0, 0, tzinfo=timezone.utc),
    )
    saved = s.save_message(msg)
    export_messages([saved], base_path=str(tmp_path))
    inbox_dir = tmp_path / "inbox" / "KD9ABC"
    files = list(inbox_dir.iterdir())
    assert len(files) == 1
    content = files[0].read_text()
    assert "Export test" in content
    assert "Export body" in content


def test_export_bulletins_writes_files(store, tmp_path):
    s, op, node = store
    bul = Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="B005",
        category="WX", from_call="W0WX",
        subject="Weather", body="Sunny",
        timestamp=datetime(2026, 3, 22, 12, 0, 0, tzinfo=timezone.utc),
    )
    saved = s.save_bulletin(bul)
    export_bulletins([saved], base_path=str(tmp_path))
    wx_dir = tmp_path / "bulletins" / "WX"
    files = list(wx_dir.iterdir())
    assert len(files) == 1
    content = files[0].read_text()
    assert "Weather" in content


def test_export_sent_messages(store, tmp_path):
    s, op, node = store
    msg = Message(
        operator_id=op.id, node_id=node.id, bbs_id="006",
        from_call="KD9ABC", to_call="W0TEST",
        subject="Outbound", body="Sent body",
        timestamp=datetime(2026, 3, 22, 12, 0, 0, tzinfo=timezone.utc),
        sent=True,
    )
    saved = s.save_message(msg)
    export_messages([saved], base_path=str(tmp_path))
    sent_dir = tmp_path / "sent"
    files = list(sent_dir.iterdir())
    assert len(files) == 1
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_store/ -k "export" -v
```

Expected: ImportError on `open_packet.store.exporter`.

- [ ] **Step 3: Implement the exporter**

```python
# open_packet/store/exporter.py
from __future__ import annotations
import os
from open_packet.store.models import Message, Bulletin


def export_messages(messages: list[Message], base_path: str) -> None:
    for msg in messages:
        if msg.sent:
            folder = os.path.join(base_path, "sent")
        else:
            folder = os.path.join(base_path, "inbox", msg.to_call.upper())
        os.makedirs(folder, exist_ok=True)
        date_str = msg.timestamp.strftime("%Y-%m-%d") if msg.timestamp else "0000-00-00"
        safe_subject = "".join(c if c.isalnum() or c in "-_ " else "_" for c in msg.subject)[:40]
        filename = f"{date_str}-{msg.bbs_id}-{safe_subject}.txt".replace(" ", "-")
        path = os.path.join(folder, filename)
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write(f"From:    {msg.from_call}\n")
                f.write(f"To:      {msg.to_call}\n")
                f.write(f"Subject: {msg.subject}\n")
                f.write(f"Date:    {msg.timestamp.isoformat() if msg.timestamp else ''}\n")
                f.write("-" * 40 + "\n")
                f.write(msg.body)


def export_bulletins(bulletins: list[Bulletin], base_path: str) -> None:
    for bul in bulletins:
        folder = os.path.join(base_path, "bulletins", bul.category.upper())
        os.makedirs(folder, exist_ok=True)
        date_str = bul.timestamp.strftime("%Y-%m-%d") if bul.timestamp else "0000-00-00"
        safe_subject = "".join(c if c.isalnum() or c in "-_ " else "_" for c in bul.subject)[:40]
        filename = f"{date_str}-{bul.bbs_id}-{safe_subject}.txt".replace(" ", "-")
        path = os.path.join(folder, filename)
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write(f"Category: {bul.category}\n")
                f.write(f"From:     {bul.from_call}\n")
                f.write(f"Subject:  {bul.subject}\n")
                f.write(f"Date:     {bul.timestamp.isoformat() if bul.timestamp else ''}\n")
                f.write("-" * 40 + "\n")
                f.write(bul.body)
```

- [ ] **Step 4: Call the exporter from the engine after sync**

In `open_packet/engine/engine.py`, add an import and call in `_do_check_mail` after `SyncCompleteEvent` is emitted:

```python
from open_packet.store.exporter import export_messages, export_bulletins

# At the end of _do_check_mail, before the finally block:
if self._export_path:
    all_messages = self._store.list_messages(operator_id=self._operator.id)
    all_bulletins = self._store.list_bulletins(operator_id=self._operator.id)
    export_messages(all_messages, base_path=self._export_path)
    export_bulletins(all_bulletins, base_path=self._export_path)
```

Add `_export_path: str | None` as an `__init__` parameter to `Engine` (default `None`). Pass it from `OpenPacketApp._init_engine` using `os.path.expanduser(self.config.store.export_path) if self.config.store.export_path else None`.

- [ ] **Step 5: Run all store tests**

```bash
uv run pytest tests/test_store/ -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add open_packet/store/exporter.py tests/test_store/test_store.py open_packet/engine/engine.py
git commit -m "feat: flat-file export of messages and bulletins after sync"
```

---

## Task 15: Integration Test

**Files:**
- Create: `tests/test_engine/test_integration.py`

A full mock session: engine + store + mock connection replaying a captured BPQ session transcript. Verifies end-to-end that `CheckMailCommand` results in messages saved to the database.

- [ ] **Step 1: Write the integration test**

```python
# tests/test_engine/test_integration.py
import queue
import time
import tempfile
import os
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from open_packet.engine.engine import Engine
from open_packet.engine.commands import CheckMailCommand
from open_packet.engine.events import SyncCompleteEvent
from open_packet.store.database import Database
from open_packet.store.store import Store
from open_packet.store.models import Operator, Node
from open_packet.node.bpq import BPQNode
from open_packet.link.base import ConnectionBase
from open_packet.ax25.frame import AX25Frame, encode_frame
from open_packet.node.base import MessageHeader, Message as NodeMessage


class ReplayConnection(ConnectionBase):
    """Replays a sequence of AX.25 frames as if received from a BBS."""
    def __init__(self, source: str, source_ssid: int,
                 dest: str, dest_ssid: int, responses: list[str]):
        self._source = source
        self._source_ssid = source_ssid
        self._dest = dest
        self._dest_ssid = dest_ssid
        self._responses = list(responses)
        self.sent_text: list[str] = []

    def connect(self, callsign: str, ssid: int) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def send_frame(self, data: bytes) -> None:
        from open_packet.ax25.frame import decode_frame
        frame = decode_frame(data)
        self.sent_text.append(frame.info.decode(errors="replace").strip())

    def receive_frame(self, timeout: float = 5.0) -> bytes:
        if self._responses:
            text = self._responses.pop(0)
            return encode_frame(AX25Frame(
                destination=self._dest,
                destination_ssid=self._dest_ssid,
                source=self._source,
                source_ssid=self._source_ssid,
                info=text.encode(),
            ))
        return b""


def test_full_check_mail_cycle():
    """
    Simulate a BPQ session: connect, list messages, read one message,
    disconnect. Verify the message ends up in the database.
    """
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    try:
        db = Database(f.name)
        db.initialize()
        op = db.insert_operator(
            Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True)
        )
        node_record = db.insert_node(
            Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True)
        )
        store = Store(db)

        # BPQ session transcript
        responses = [
            "BPQ> ",                                              # initial prompt
            "Msg  To        From      Date   Subject\n"           # list response
            "1    KD9ABC    W0TEST    03/22  Hello World\n"
            "BPQ> ",
            "From: W0TEST\nTo: KD9ABC\nSubject: Hello World\n\n"  # read response
            "This is the message body.\n"
            "BPQ> ",
        ]

        connection = ReplayConnection(
            source="W0BPQ", source_ssid=1,
            dest="KD9ABC", dest_ssid=1,
            responses=responses,
        )
        node = BPQNode(
            connection=connection,
            node_callsign="W0BPQ", node_ssid=1,
            my_callsign="KD9ABC", my_ssid=1,
        )

        cmd_queue = queue.Queue()
        evt_queue = queue.Queue()
        engine = Engine(
            command_queue=cmd_queue, event_queue=evt_queue,
            store=store, operator=op, node_record=node_record,
            connection=connection, node=node,
        )
        engine.start()
        cmd_queue.put(CheckMailCommand())

        # Collect events
        events = []
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                events.append(evt_queue.get(timeout=0.5))
            except queue.Empty:
                if any(isinstance(e, SyncCompleteEvent) for e in events):
                    break

        engine.stop()

        sync_events = [e for e in events if isinstance(e, SyncCompleteEvent)]
        assert sync_events, "No SyncCompleteEvent received"
        assert sync_events[0].messages_retrieved >= 1

        # Verify message in database
        messages = store.list_messages(operator_id=op.id)
        assert any(m.subject == "Hello World" for m in messages)

    finally:
        db.close()
        os.unlink(f.name)
```

- [ ] **Step 2: Run the integration test**

```bash
uv run pytest tests/test_engine/test_integration.py -v
```

Expected: PASS.

- [ ] **Step 3: Run full test suite one final time**

```bash
uv run pytest -v
```

Expected: all tests pass, zero failures.

- [ ] **Step 4: Commit**

```bash
git add tests/test_engine/test_integration.py
git commit -m "test: end-to-end integration test for full check-mail cycle"
```

---

## Final Checklist

- [ ] `uv run pytest` passes with zero failures
- [ ] `uv run open-packet --help` does not crash (or at least imports cleanly)
- [ ] All modules have `__init__.py` files
- [ ] Git log shows one commit per task
- [ ] No `TODO` or placeholder comments remain in implementation files
