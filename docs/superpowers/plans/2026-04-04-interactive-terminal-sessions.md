# Interactive Terminal Sessions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an interactive packet terminal feature: users connect to a station via a raw AX.25 or telnet session, send/receive free-form text in the TUI, and manage sessions from the folder sidebar; also make SSID optional in node setup.

**Architecture:** `TerminalSession` runs a background daemon thread per connection (mirroring `Engine`'s pattern); `OpenPacketApp` owns the session list and polls each session's queue every 100 ms alongside the existing engine queue; sessions appear under a "Sessions" section in `FolderTree` and the right pane switches to a `TerminalView` widget when one is selected.

**Tech Stack:** Python 3.12+, Textual 0.x (RichLog, Input, Select, Tree), SQLite via existing `Database`, AX.25 via existing `AX25Connection`/`KISSLink`, telnet via existing `TelnetLink`.

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `open_packet/terminal/__init__.py` | Package marker |
| Create | `open_packet/terminal/session.py` | `TerminalSession` + `TerminalConnectResult` |
| Create | `open_packet/ui/tui/widgets/terminal_view.py` | Scrollable log + input widget |
| Create | `open_packet/ui/tui/screens/connect_terminal.py` | Connect dialog modal |
| Create | `tests/test_terminal/__init__.py` | Package marker |
| Create | `tests/test_terminal/test_session.py` | Unit tests for `TerminalSession` |
| Create | `tests/test_ui/test_terminal_view.py` | Widget tests for `TerminalView` |
| Create | `tests/test_ui/test_connect_terminal.py` | Modal tests for `ConnectTerminalScreen` |
| Modify | `open_packet/ui/tui/widgets/folder_tree.py` | Add Sessions section + `SessionSelected` message |
| Modify | `open_packet/ui/tui/screens/main.py` | Add `TerminalView`, `show_terminal()`, `show_messages()`, bindings |
| Modify | `open_packet/ui/tui/app.py` | Session list, polling, event handlers |
| Modify | `open_packet/ui/tui/screens/setup_node.py` | SSID optional |
| Modify | `tests/test_ui/test_setup_screens.py` | Test blank SSID on node setup |

---

## Task 1: SSID optional in `setup_node.py`

**Files:**
- Modify: `open_packet/ui/tui/screens/setup_node.py`
- Test: `tests/test_ui/test_setup_screens.py`

- [ ] **Step 1: Write the failing test**

Add this test to `tests/test_ui/test_setup_screens.py` after the `test_node_setup_cancel` test (which already has a `node_db` fixture):

```python
@pytest.mark.asyncio
async def test_node_setup_blank_ssid_defaults_to_zero(node_db):
    """Blank SSID field on node setup should default to 0, not error."""
    app = _ScreenTestApp(lambda: NodeSetupScreen(interfaces=[], db=node_db))
    async with app.run_test(size=(80, 120)) as pilot:
        await pilot.click("#label_field")
        await pilot.press(*"Home BBS")
        await pilot.click("#callsign_field")
        await pilot.press(*"w0bpq")
        # leave ssid_field blank
        await pilot.click("#telnet_host")
        await pilot.press(*"192.168.1.209")
        await pilot.click("#telnet_port")
        await pilot.press(*"8023")
        await pilot.click("#telnet_user")
        await pilot.press(*"K0JLB")
        await pilot.click("#telnet_pass")
        await pilot.press(*"password")
        await pilot.click("#save_btn")
        await pilot.pause()
    result = app.dismiss_result
    assert result is not _SENTINEL
    assert result is not None
    assert result.ssid == 0
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
uv run pytest tests/test_ui/test_setup_screens.py::test_node_setup_blank_ssid_defaults_to_zero -v
```

Expected: FAIL — blank SSID raises `ValueError` in `int("")`.

- [ ] **Step 3: Fix `setup_node.py`**

In `open_packet/ui/tui/screens/setup_node.py`:

Change the label at line 95 from `"SSID (0-15):"` to `"SSID (optional, 0–15):"`.

Change the `_validate` method's SSID block (around line 221–230):
```python
        try:
            ssid = int(ssid_str) if ssid_str else 0
            if not 0 <= ssid <= 15:
                raise ValueError
            self.query_one("#ssid_error", Label).update("")
        except ValueError:
            self.query_one("#ssid_error", Label).update("SSID must be an integer 0-15")
            valid = False
```

Change the `on_button_pressed` save path at line 329:
```python
                ssid = int(self.query_one("#ssid_field", Input).value.strip() or "0")
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
uv run pytest tests/test_ui/test_setup_screens.py::test_node_setup_blank_ssid_defaults_to_zero -v
```

Expected: PASS.

- [ ] **Step 5: Run the full setup screen test suite to check for regressions**

```bash
uv run pytest tests/test_ui/test_setup_screens.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add open_packet/ui/tui/screens/setup_node.py tests/test_ui/test_setup_screens.py
git commit -m "feat: make SSID optional in node setup screen (defaults to 0)"
```

---

## Task 2: `TerminalSession` and `TerminalConnectResult`

**Files:**
- Create: `open_packet/terminal/__init__.py`
- Create: `open_packet/terminal/session.py`
- Create: `tests/test_terminal/__init__.py`
- Create: `tests/test_terminal/test_session.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_terminal/__init__.py` (empty).

Create `tests/test_terminal/test_session.py`:

```python
from __future__ import annotations
import queue
import threading
import time
from unittest.mock import MagicMock

from open_packet.terminal.session import TerminalSession, TerminalConnectResult
from open_packet.store.models import Interface


# --- Unit tests (no threads) ---

def test_poll_drains_queue():
    conn = MagicMock()
    session = TerminalSession(label="W0TEST", connection=conn)
    session._rx_queue.put("hello")
    session._rx_queue.put("world")
    lines = session.poll()
    assert lines == ["hello", "world"]
    assert session.poll() == []


def test_poll_empty_returns_empty_list():
    conn = MagicMock()
    session = TerminalSession(label="W0TEST", connection=conn)
    assert session.poll() == []


def test_send_encodes_text_with_carriage_return():
    conn = MagicMock()
    session = TerminalSession(label="W0TEST", connection=conn)
    session.send("hello")
    conn.send_frame.assert_called_once_with(b"hello\r")


def test_initial_status_is_connecting():
    conn = MagicMock()
    session = TerminalSession(label="W0TEST", connection=conn)
    assert session.status == "connecting"
    assert session.has_unread is False


# --- Integration tests (with threads) ---

def _make_blocking_session(frames: list[bytes]):
    """Session whose fake connection yields `frames` then blocks indefinitely."""
    conn = MagicMock()
    frame_q: queue.Queue[bytes] = queue.Queue()
    for f in frames:
        frame_q.put(f)
    stop = threading.Event()

    def fake_recv(timeout=1.0):
        try:
            return frame_q.get(timeout=min(timeout, 0.05))
        except queue.Empty:
            stop.wait(timeout=min(timeout, 0.05))
            return b''

    conn.receive_frame.side_effect = fake_recv
    session = TerminalSession(
        label="W0TEST", connection=conn,
        target_callsign="W0XYZ", target_ssid=0,
    )
    return session, stop


def _wait_for(condition, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_run_thread_sets_connected_status():
    session, stop = _make_blocking_session([])
    session.start()
    assert _wait_for(lambda: session.status == "connected")
    stop.set()
    session.disconnect()


def test_run_thread_receives_frame_into_poll():
    session, stop = _make_blocking_session([b"hello\r\n"])
    session.start()
    lines = []
    assert _wait_for(lambda: bool(lines := session.poll()))
    assert any("hello" in l for l in lines)
    stop.set()
    session.disconnect()


def test_connect_error_sets_error_status():
    conn = MagicMock()
    conn.connect.side_effect = Exception("refused")
    session = TerminalSession(label="W0TEST", connection=conn)
    session.start()
    assert _wait_for(lambda: session.status == "error")
    lines = session.poll()
    assert any("connection error" in l for l in lines)


def test_disconnect_sets_disconnected_status():
    session, stop = _make_blocking_session([])
    session.start()
    _wait_for(lambda: session.status == "connected")
    stop.set()
    session.disconnect()
    assert session.status == "disconnected"


# --- TerminalConnectResult ---

def test_terminal_connect_result_fields():
    iface = Interface(id=1, label="Home", iface_type="kiss_tcp", host="localhost", port=8910)
    result = TerminalConnectResult(
        label="W0XYZ",
        interface=iface,
        target_callsign="W0XYZ",
        target_ssid=3,
    )
    assert result.label == "W0XYZ"
    assert result.interface is iface
    assert result.target_callsign == "W0XYZ"
    assert result.target_ssid == 3
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_terminal/ -v
```

Expected: FAIL — `open_packet.terminal.session` does not exist.

- [ ] **Step 3: Create `open_packet/terminal/__init__.py`**

```python
```
(empty file)

- [ ] **Step 4: Create `open_packet/terminal/session.py`**

```python
# open_packet/terminal/session.py
from __future__ import annotations
import queue
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

from open_packet.link.base import ConnectionBase

if TYPE_CHECKING:
    from open_packet.store.models import Interface


@dataclass
class TerminalConnectResult:
    label: str
    interface: "Interface"
    target_callsign: str
    target_ssid: int


class TerminalSession:
    def __init__(
        self,
        label: str,
        connection: ConnectionBase,
        target_callsign: str = "",
        target_ssid: int = 0,
    ) -> None:
        self.label = label
        self.status = "connecting"
        self.has_unread = False
        self._connection = connection
        self._target_callsign = target_callsign
        self._target_ssid = target_ssid
        self._rx_queue: queue.Queue[str] = queue.Queue()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def send(self, text: str) -> None:
        self._connection.send_frame((text + "\r").encode())

    def disconnect(self) -> None:
        self._stop_event.set()
        try:
            self._connection.disconnect()
        except Exception:
            pass
        self._thread.join(timeout=5.0)
        self.status = "disconnected"

    def poll(self) -> list[str]:
        lines: list[str] = []
        while not self._rx_queue.empty():
            try:
                lines.append(self._rx_queue.get_nowait())
            except queue.Empty:
                break
        return lines

    def _run(self) -> None:
        try:
            self._connection.connect(self._target_callsign, self._target_ssid)
            self.status = "connected"
        except Exception as e:
            self.status = "error"
            self._rx_queue.put(f"[connection error: {e}]")
            return
        while not self._stop_event.is_set():
            try:
                data = self._connection.receive_frame(timeout=1.0)
                if data:
                    self._rx_queue.put(data.decode(errors="replace"))
            except Exception as e:
                self.status = "error"
                self._rx_queue.put(f"[error: {e}]")
                break
        if self.status not in ("error", "disconnected"):
            self.status = "disconnected"
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
uv run pytest tests/test_terminal/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add open_packet/terminal/ tests/test_terminal/
git commit -m "feat: add TerminalSession and TerminalConnectResult"
```

---

## Task 3: `TerminalView` widget

**Files:**
- Create: `open_packet/ui/tui/widgets/terminal_view.py`
- Create: `tests/test_ui/test_terminal_view.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ui/test_terminal_view.py`:

```python
from __future__ import annotations
import pytest
from textual.app import App, ComposeResult
from open_packet.ui.tui.widgets.terminal_view import TerminalView


class _TerminalTestApp(App):
    def compose(self) -> ComposeResult:
        tv = TerminalView(id="tv")
        yield tv
        
    def on_mount(self) -> None:
        self.submitted: list[str] = []
    
    def on_terminal_view_line_submitted(self, event: TerminalView.LineSubmitted) -> None:
        self.submitted.append(event.text)


@pytest.mark.asyncio
async def test_terminal_view_mounts():
    app = _TerminalTestApp()
    async with app.run_test() as pilot:
        assert app.query_one("#tv") is not None


@pytest.mark.asyncio
async def test_set_header_updates_label():
    app = _TerminalTestApp()
    async with app.run_test() as pilot:
        tv = app.query_one(TerminalView)
        tv.set_header("W0XYZ — connected")
        await pilot.pause()
        from textual.widgets import Label
        header = tv.query_one("#terminal_header", Label)
        assert "W0XYZ" in str(header.renderable)


@pytest.mark.asyncio
async def test_append_line_adds_to_log():
    app = _TerminalTestApp()
    async with app.run_test() as pilot:
        tv = app.query_one(TerminalView)
        tv.append_line("hello world")
        await pilot.pause()
        # RichLog contains content — just verify no exception raised
        from textual.widgets import RichLog
        log = tv.query_one(RichLog)
        assert log is not None


@pytest.mark.asyncio
async def test_input_submit_fires_line_submitted():
    app = _TerminalTestApp()
    async with app.run_test() as pilot:
        from textual.widgets import Input
        inp = app.query_one("#terminal_input", Input)
        await pilot.click("#terminal_input")
        await pilot.press(*"hello")
        await pilot.press("enter")
        await pilot.pause()
    assert app.submitted == ["hello"]


@pytest.mark.asyncio
async def test_input_clears_after_submit():
    app = _TerminalTestApp()
    async with app.run_test() as pilot:
        from textual.widgets import Input
        await pilot.click("#terminal_input")
        await pilot.press(*"test")
        await pilot.press("enter")
        await pilot.pause()
        inp = app.query_one("#terminal_input", Input)
        assert inp.value == ""


@pytest.mark.asyncio
async def test_blank_input_does_not_fire_event():
    app = _TerminalTestApp()
    async with app.run_test() as pilot:
        await pilot.click("#terminal_input")
        await pilot.press("enter")
        await pilot.pause()
    assert app.submitted == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_ui/test_terminal_view.py -v
```

Expected: FAIL — `open_packet.ui.tui.widgets.terminal_view` does not exist.

- [ ] **Step 3: Create `open_packet/ui/tui/widgets/terminal_view.py`**

```python
# open_packet/ui/tui/widgets/terminal_view.py
from __future__ import annotations
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message as TMessage
from textual.widgets import Input, Label, RichLog


class TerminalView(Vertical):
    DEFAULT_CSS = """
    TerminalView {
        height: 1fr;
    }
    TerminalView #terminal_header {
        height: 1;
        background: $primary-darken-2;
        color: $text;
        padding: 0 1;
    }
    TerminalView RichLog {
        height: 1fr;
    }
    TerminalView #terminal_input {
        height: 3;
        border-top: solid $primary;
    }
    """

    class LineSubmitted(TMessage):
        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()

    def compose(self) -> ComposeResult:
        yield Label("", id="terminal_header")
        yield RichLog(id="terminal_log", auto_scroll=True, markup=False)
        yield Input(placeholder="Type and press Enter to send...", id="terminal_input")

    def set_header(self, text: str) -> None:
        self.query_one("#terminal_header", Label).update(text)

    def append_line(self, text: str) -> None:
        self.query_one("#terminal_log", RichLog).write(text)

    def clear(self) -> None:
        self.query_one("#terminal_log", RichLog).clear()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if text:
            self.post_message(self.LineSubmitted(text))
            event.input.clear()
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_ui/test_terminal_view.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add open_packet/ui/tui/widgets/terminal_view.py tests/test_ui/test_terminal_view.py
git commit -m "feat: add TerminalView widget"
```

---

## Task 4: `FolderTree` sessions section

**Files:**
- Modify: `open_packet/ui/tui/widgets/folder_tree.py`
- Test inline by running the existing folder tree tests + checking new behavior

- [ ] **Step 1: Write the failing test**

Add this to `tests/test_ui/test_tui.py`:

```python
@pytest.mark.asyncio
async def test_folder_tree_update_sessions_adds_entries(app_config, tmp_path):
    """update_sessions() adds session entries to the tree without crashing."""
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node, Interface
    from open_packet.ui.tui.widgets.folder_tree import FolderTree
    from unittest.mock import MagicMock

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=True))
    iface = db.insert_interface(Interface(label="TNC", iface_type="kiss_tcp", host="localhost", port=8910))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=0, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        await pilot.pause()
        ft = app.query_one(FolderTree)

        # Build fake sessions
        session_a = MagicMock()
        session_a.label = "W0XYZ"
        session_a.status = "connected"
        session_a.has_unread = False

        session_b = MagicMock()
        session_b.label = "K0TEST"
        session_b.status = "error"
        session_b.has_unread = False

        ft.update_sessions([session_a, session_b])
        await pilot.pause()
        # Two session nodes exist — no exception raised
        assert len(ft._session_nodes) == 2
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
uv run pytest tests/test_ui/test_tui.py::test_folder_tree_update_sessions_adds_entries -v
```

Expected: FAIL — `FolderTree` has no `_session_nodes` attribute.

- [ ] **Step 3: Modify `folder_tree.py`**

Replace the entire file with:

```python
# open_packet/ui/tui/widgets/folder_tree.py
from __future__ import annotations
from rich.style import Style
from rich.text import Text
from textual.widgets import Tree
from textual.widgets.tree import TreeNode
from textual.message import Message as TMessage


def _session_label(session) -> Text:
    if session.status == "connecting":
        prefix, color = "⟳ ", "yellow"
    elif session.status == "connected" and session.has_unread:
        prefix, color = "◉ ", "cyan"
    elif session.status == "connected":
        prefix, color = "● ", "green"
    elif session.status == "error":
        prefix, color = "✕ ", "red"
    else:  # disconnected or unknown
        prefix, color = "○ ", "dim"
    return Text.assemble((prefix, color), session.label)


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

    class SessionSelected(TMessage):
        def __init__(self, session_idx: int) -> None:
            self.session_idx = session_idx
            super().__init__()

    def on_mount(self) -> None:
        self.root.expand()
        self._inbox_node     = self.root.add_leaf("Inbox",  data="Inbox")
        self._outbox_node    = self.root.add_leaf("Outbox", data="Outbox")
        self._sent_node      = self.root.add_leaf("Sent",   data="Sent")
        self._bulletins_node = self.root.add("Bulletins", data="Bulletins")
        self._bulletin_nodes: dict[str, TreeNode] = {}
        self._sessions_node  = self.root.add("Sessions", data="__sessions__")
        self._session_nodes: list[TreeNode] = []

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data or str(event.node.label)
        if isinstance(data, str) and data.startswith("__session_"):
            idx = int(data.split("_")[-1])
            self.post_message(self.SessionSelected(idx))
            return
        parent = event.node.parent
        if parent and parent.data == "Bulletins":
            self.post_message(self.FolderSelected("Bulletins", category=data))
        else:
            self.post_message(self.FolderSelected(data))

    def update_counts(self, stats: dict) -> None:
        if not hasattr(self, "_inbox_node"):
            return
        inbox_total, inbox_unread = stats.get("Inbox", (0, 0))
        (sent_total,)  = stats.get("Sent",   (0,))
        (outbox_count,) = stats.get("Outbox", (0,))

        if inbox_total == 0:
            self._inbox_node.set_label("Inbox")
        elif inbox_unread == 0:
            self._inbox_node.set_label(f"Inbox ({inbox_total})")
        else:
            self._inbox_node.set_label(
                Text.assemble("Inbox (", str(inbox_total), "/", (str(inbox_unread), "bold"), ")")
            )

        if outbox_count > 0:
            self._outbox_node.set_label(
                Text(f"Outbox ({outbox_count})", style=Style(bgcolor="dark_goldenrod"))
            )
        else:
            self._outbox_node.set_label(Text("Outbox", style=Style()))

        self._sent_node.set_label(f"Sent ({sent_total})" if sent_total > 0 else "Sent")

        bulletin_stats: dict[str, tuple[int, int]] = stats.get("Bulletins", {})
        for category, (total, unread) in bulletin_stats.items():
            if category not in self._bulletin_nodes:
                node = self._bulletins_node.add_leaf(category, data=category)
                self._bulletin_nodes[category] = node
            node = self._bulletin_nodes[category]
            if total == 0 and unread == 0:
                node.set_label(category)
            elif unread == 0:
                node.set_label(f"{category} ({total})")
            else:
                node.set_label(f"{category} ({total}/{unread} new)")

        for category in list(self._bulletin_nodes):
            if category not in bulletin_stats:
                self._bulletin_nodes[category].remove()
                del self._bulletin_nodes[category]

    def update_sessions(self, sessions: list) -> None:
        if not hasattr(self, "_sessions_node"):
            return
        for node in list(self._session_nodes):
            node.remove()
        self._session_nodes.clear()

        for i, session in enumerate(sessions):
            label = _session_label(session)
            node = self._sessions_node.add_leaf(label, data=f"__session_{i}__")
            self._session_nodes.append(node)

        if sessions:
            self._sessions_node.expand()
```

- [ ] **Step 4: Run the new test to confirm it passes**

```bash
uv run pytest tests/test_ui/test_tui.py::test_folder_tree_update_sessions_adds_entries -v
```

Expected: PASS.

- [ ] **Step 5: Run the full TUI test suite to check for regressions**

```bash
uv run pytest tests/test_ui/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add open_packet/ui/tui/widgets/folder_tree.py tests/test_ui/test_tui.py
git commit -m "feat: add Sessions section to FolderTree with status indicators"
```

---

## Task 5: `ConnectTerminalScreen`

**Files:**
- Create: `open_packet/ui/tui/screens/connect_terminal.py`
- Create: `tests/test_ui/test_connect_terminal.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ui/test_connect_terminal.py`:

```python
from __future__ import annotations
import pytest
from textual.app import App
from textual.widgets import Select
from open_packet.store.database import Database
from open_packet.store.models import Interface, Node
from open_packet.ui.tui.screens.connect_terminal import ConnectTerminalScreen, _CUSTOM

_SENTINEL = object()


class _ConnectTestApp(App):
    def __init__(self, db, **kwargs):
        super().__init__(**kwargs)
        self._db = db
        self.dismiss_result = _SENTINEL

    def on_mount(self) -> None:
        def capture(result):
            self.dismiss_result = result
        self.push_screen(ConnectTerminalScreen(db=self._db), callback=capture)


@pytest.fixture
def conn_db(tmp_path):
    db = Database(str(tmp_path / "conn.db"))
    db.initialize()
    yield db
    db.close()


@pytest.fixture
def populated_db(conn_db):
    iface_kiss = conn_db.insert_interface(Interface(
        label="Home TNC", iface_type="kiss_tcp", host="localhost", port=8910
    ))
    iface_telnet = conn_db.insert_interface(Interface(
        label="Home BBS", iface_type="telnet",
        host="192.168.1.209", port=8023, username="K0JLB", password="pw"
    ))
    node = conn_db.insert_node(Node(
        label="W0BPQ Node", callsign="W0BPQ", ssid=0, node_type="bpq",
        is_default=True, interface_id=iface_telnet.id
    ))
    return conn_db, iface_kiss, iface_telnet, node


@pytest.mark.asyncio
async def test_cancel_returns_none(conn_db):
    app = _ConnectTestApp(conn_db)
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.click("#cancel_btn")
        await pilot.pause()
    assert app.dismiss_result is None


@pytest.mark.asyncio
async def test_connect_without_interface_does_not_dismiss(conn_db):
    """No interface selected — should not dismiss."""
    app = _ConnectTestApp(conn_db)
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.click("#callsign_field")
        await pilot.press(*"W0XYZ")
        await pilot.click("#connect_btn")
        await pilot.pause()
    assert app.dismiss_result is _SENTINEL


@pytest.mark.asyncio
async def test_connect_kiss_returns_result(populated_db):
    db, iface_kiss, iface_telnet, node = populated_db
    app = _ConnectTestApp(db)
    async with app.run_test(size=(80, 40)) as pilot:
        # Select the KISS interface
        iface_sel = pilot.app.screen.query_one("#iface_select", Select)
        iface_sel.value = str(iface_kiss.id)
        await pilot.pause()
        await pilot.click("#callsign_field")
        await pilot.press(*"W0XYZ")
        await pilot.click("#connect_btn")
        await pilot.pause()
    from open_packet.terminal.session import TerminalConnectResult
    result = app.dismiss_result
    assert result is not _SENTINEL
    assert result is not None
    assert isinstance(result, TerminalConnectResult)
    assert result.target_callsign == "W0XYZ"
    assert result.target_ssid == 0
    assert result.interface.id == iface_kiss.id


@pytest.mark.asyncio
async def test_connect_telnet_disables_callsign(populated_db):
    """Selecting telnet interface disables callsign field."""
    db, iface_kiss, iface_telnet, node = populated_db
    app = _ConnectTestApp(db)
    async with app.run_test(size=(80, 40)) as pilot:
        from textual.widgets import Input
        iface_sel = pilot.app.screen.query_one("#iface_select", Select)
        iface_sel.value = str(iface_telnet.id)
        await pilot.pause()
        callsign_input = pilot.app.screen.query_one("#callsign_field", Input)
        assert callsign_input.disabled is True


@pytest.mark.asyncio
async def test_select_node_autofills_interface_and_callsign(populated_db):
    db, iface_kiss, iface_telnet, node = populated_db
    app = _ConnectTestApp(db)
    async with app.run_test(size=(80, 40)) as pilot:
        from textual.widgets import Input
        node_sel = pilot.app.screen.query_one("#node_select", Select)
        node_sel.value = str(node.id)
        await pilot.pause()
        iface_sel = pilot.app.screen.query_one("#iface_select", Select)
        callsign_input = pilot.app.screen.query_one("#callsign_field", Input)
        assert str(iface_sel.value) == str(iface_telnet.id)
        assert callsign_input.value == "W0BPQ"


@pytest.mark.asyncio
async def test_connect_kiss_with_ssid(populated_db):
    db, iface_kiss, _, _ = populated_db
    app = _ConnectTestApp(db)
    async with app.run_test(size=(80, 40)) as pilot:
        iface_sel = pilot.app.screen.query_one("#iface_select", Select)
        iface_sel.value = str(iface_kiss.id)
        await pilot.pause()
        await pilot.click("#callsign_field")
        await pilot.press(*"W0XYZ")
        await pilot.click("#ssid_field")
        await pilot.press("3")
        await pilot.click("#connect_btn")
        await pilot.pause()
    result = app.dismiss_result
    assert result is not _SENTINEL
    assert result.target_ssid == 3


@pytest.mark.asyncio
async def test_connect_kiss_blank_callsign_does_not_dismiss(populated_db):
    db, iface_kiss, _, _ = populated_db
    app = _ConnectTestApp(db)
    async with app.run_test(size=(80, 40)) as pilot:
        iface_sel = pilot.app.screen.query_one("#iface_select", Select)
        iface_sel.value = str(iface_kiss.id)
        await pilot.pause()
        # leave callsign blank
        await pilot.click("#connect_btn")
        await pilot.pause()
    assert app.dismiss_result is _SENTINEL
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_ui/test_connect_terminal.py -v
```

Expected: FAIL — module does not exist.

- [ ] **Step 3: Create `open_packet/ui/tui/screens/connect_terminal.py`**

```python
# open_packet/ui/tui/screens/connect_terminal.py
from __future__ import annotations
from typing import Optional
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select
from textual.containers import Vertical, Horizontal
from open_packet.store.database import Database
from open_packet.store.models import Interface, Node
from open_packet.terminal.session import TerminalConnectResult
from open_packet.ui.tui.screens import CALLSIGN_RE

_CUSTOM = "__custom__"
_NO_IFACE = "__none__"


class ConnectTerminalScreen(ModalScreen):
    DEFAULT_CSS = """
    ConnectTerminalScreen {
        align: center middle;
    }
    ConnectTerminalScreen > Vertical {
        width: 55;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    ConnectTerminalScreen .error {
        color: $error;
        height: 1;
    }
    """

    def __init__(self, db: Database, **kwargs) -> None:
        super().__init__(**kwargs)
        self._db = db
        self._nodes: list[Node] = []
        self._interfaces: list[Interface] = []

    def compose(self) -> ComposeResult:
        self._nodes = self._db.list_nodes()
        self._interfaces = self._db.list_interfaces()

        node_options = [("— custom connection —", _CUSTOM)]
        for n in self._nodes:
            node_options.append((n.label, str(n.id)))

        iface_options = [("— select interface —", _NO_IFACE)]
        for iface in self._interfaces:
            display = iface.label or f"{iface.iface_type}:{iface.host}"
            iface_options.append((display, str(iface.id)))

        with Vertical():
            yield Label("Connect to Station")
            yield Label("Node:")
            yield Select(node_options, value=_CUSTOM, id="node_select")
            yield Label("Interface:")
            yield Select(iface_options, value=_NO_IFACE, id="iface_select")
            yield Label("", id="iface_error", classes="error")
            yield Label("Callsign:")
            yield Input(placeholder="e.g. W0XYZ", id="callsign_field")
            yield Label("SSID (optional, 0–15):")
            yield Input(placeholder="0", id="ssid_field")
            yield Label("", id="callsign_error", classes="error")
            with Horizontal():
                yield Button("Connect", variant="primary", id="connect_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "node_select":
            self._on_node_changed(event.value)
        elif event.select.id == "iface_select":
            self._refresh_callsign_state()

    def _on_node_changed(self, value) -> None:
        if value == _CUSTOM or value == Select.BLANK:
            return
        node = next((n for n in self._nodes if str(n.id) == str(value)), None)
        if node is None:
            return
        if node.interface_id is not None:
            self.query_one("#iface_select", Select).value = str(node.interface_id)
        self.query_one("#callsign_field", Input).value = node.callsign
        ssid_val = str(node.ssid) if node.ssid else ""
        self.query_one("#ssid_field", Input).value = ssid_val
        self._refresh_callsign_state()

    def _active_iface(self) -> Optional[Interface]:
        val = self.query_one("#iface_select", Select).value
        if not val or val in (Select.BLANK, _NO_IFACE):
            return None
        return next((i for i in self._interfaces if str(i.id) == str(val)), None)

    def _refresh_callsign_state(self) -> None:
        iface = self._active_iface()
        is_telnet = iface is not None and iface.iface_type == "telnet"
        self.query_one("#callsign_field", Input).disabled = is_telnet
        self.query_one("#ssid_field", Input).disabled = is_telnet

    def _validate(self) -> bool:
        iface = self._active_iface()
        iface_err = self.query_one("#iface_error", Label)
        call_err = self.query_one("#callsign_error", Label)

        if iface is None:
            iface_err.update("Interface is required")
            return False
        iface_err.update("")

        if iface.iface_type == "telnet":
            call_err.update("")
            return True

        callsign = self.query_one("#callsign_field", Input).value.strip()
        ssid_str = self.query_one("#ssid_field", Input).value.strip()

        if not CALLSIGN_RE.match(callsign):
            call_err.update("Callsign must be 1-6 alphanumeric characters")
            return False

        try:
            ssid = int(ssid_str) if ssid_str else 0
            if not 0 <= ssid <= 15:
                raise ValueError
        except ValueError:
            call_err.update("SSID must be 0–15")
            return False

        call_err.update("")
        return True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.dismiss(None)
            return
        if event.button.id != "connect_btn":
            return
        if not self._validate():
            return

        iface = self._active_iface()
        assert iface is not None

        callsign = self.query_one("#callsign_field", Input).value.strip().upper()
        ssid_str = self.query_one("#ssid_field", Input).value.strip()
        ssid = int(ssid_str) if ssid_str else 0

        node_val = self.query_one("#node_select", Select).value
        if node_val not in (_CUSTOM, Select.BLANK):
            node = next((n for n in self._nodes if str(n.id) == str(node_val)), None)
            label = node.label if node else (callsign or iface.label or "session")
        elif iface.iface_type == "telnet":
            label = iface.label or iface.host or "telnet"
        else:
            label = callsign or "session"

        self.dismiss(TerminalConnectResult(
            label=label,
            interface=iface,
            target_callsign=callsign,
            target_ssid=ssid,
        ))

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_ui/test_connect_terminal.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add open_packet/ui/tui/screens/connect_terminal.py tests/test_ui/test_connect_terminal.py
git commit -m "feat: add ConnectTerminalScreen modal"
```

---

## Task 6: `MainScreen` terminal integration

**Files:**
- Modify: `open_packet/ui/tui/screens/main.py`

- [ ] **Step 1: Write the failing test**

Add this to `tests/test_ui/test_tui.py`:

```python
@pytest.mark.asyncio
async def test_main_screen_show_terminal_hides_messages(app_config, tmp_path):
    """show_terminal() hides MessageList/MessageBody and shows TerminalView."""
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node, Interface
    from open_packet.ui.tui.screens.main import MainScreen
    from open_packet.ui.tui.widgets.terminal_view import TerminalView
    from open_packet.ui.tui.widgets.message_list import MessageList
    from open_packet.ui.tui.widgets.message_body import MessageBody

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=True))
    iface = db.insert_interface(Interface(label="TNC", iface_type="kiss_tcp", host="localhost", port=8910))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=0, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        await pilot.pause()
        main = app.query_one(MainScreen)
        tv = main.query_one(TerminalView)
        ml = main.query_one(MessageList)
        mb = main.query_one(MessageBody)

        # Initially messages visible, terminal hidden
        assert tv.display is False
        assert ml.display is True
        assert mb.display is True

        main.show_terminal()
        await pilot.pause()
        assert tv.display is True
        assert ml.display is False
        assert mb.display is False

        main.show_messages()
        await pilot.pause()
        assert tv.display is False
        assert ml.display is True
        assert mb.display is True
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
uv run pytest tests/test_ui/test_tui.py::test_main_screen_show_terminal_hides_messages -v
```

Expected: FAIL — `MainScreen` has no `show_terminal` method and no `TerminalView`.

- [ ] **Step 3: Update `main.py`**

Replace the entire file:

```python
# open_packet/ui/tui/screens/main.py
from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer
from open_packet.ui.tui.widgets.status_bar import StatusBar
from open_packet.ui.tui.widgets.folder_tree import FolderTree
from open_packet.ui.tui.widgets.message_list import MessageList
from open_packet.ui.tui.widgets.message_body import MessageBody
from open_packet.ui.tui.widgets.console_panel import ConsolePanel
from open_packet.ui.tui.widgets.terminal_view import TerminalView


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
        ("c", "check_mail", "Send/Receive"),
        ("n", "new_message", "New"),
        ("b", "new_bulletin", "Bulletin"),
        ("t", "terminal_connect", "Terminal"),
        ("d", "delete_message", "Delete"),
        ("r", "reply_message", "Reply"),
        ("s", "settings", "Settings"),
        ("`", "toggle_console", "Console"),
        ("ctrl+d", "disconnect_session", "Disconnect"),
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield StatusBar(id="status_bar")
        with Horizontal(id="main_area"):
            yield FolderTree("Folders", id="folder_tree")
            with Vertical(id="right_pane"):
                yield MessageList(id="message_list")
                yield MessageBody(id="message_body")
                yield TerminalView(id="terminal_view")
        yield ConsolePanel(id="console_panel")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("ConsolePanel").display = self.app.config.ui.console_visible
        self.query_one(TerminalView).display = False

    def show_terminal(self) -> None:
        self.query_one(TerminalView).display = True
        self.query_one(MessageList).display = False
        self.query_one(MessageBody).display = False

    def show_messages(self) -> None:
        self.query_one(TerminalView).display = False
        self.query_one(MessageList).display = True
        self.query_one(MessageBody).display = True

    def action_toggle_console(self) -> None:
        panel = self.query_one("ConsolePanel")
        panel.display = not panel.display

    def action_check_mail(self) -> None:
        self.app.check_mail()

    def action_new_message(self) -> None:
        self.app.open_compose()

    def action_new_bulletin(self) -> None:
        self.app.open_compose_bulletin()

    def action_terminal_connect(self) -> None:
        self.app.open_terminal_connect()

    def action_delete_message(self) -> None:
        self.app.delete_selected_message()

    def action_reply_message(self) -> None:
        self.app.reply_to_selected()

    def action_settings(self) -> None:
        self.app.open_settings()

    def action_disconnect_session(self) -> None:
        self.app.disconnect_session()

    def action_quit(self) -> None:
        self.app.exit()
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
uv run pytest tests/test_ui/test_tui.py::test_main_screen_show_terminal_hides_messages -v
```

Expected: PASS.

- [ ] **Step 5: Run the full UI test suite**

```bash
uv run pytest tests/test_ui/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add open_packet/ui/tui/screens/main.py
git commit -m "feat: add TerminalView to MainScreen with show_terminal/show_messages"
```

---

## Task 7: `OpenPacketApp` integration

**Files:**
- Modify: `open_packet/ui/tui/app.py`
- Test: `tests/test_ui/test_tui.py`

- [ ] **Step 1: Write the failing test**

Add this to `tests/test_ui/test_tui.py`:

```python
@pytest.mark.asyncio
async def test_open_terminal_connect_pushes_screen(app_config, tmp_path):
    """Pressing 't' pushes ConnectTerminalScreen when a db is available."""
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node, Interface
    from open_packet.ui.tui.screens.connect_terminal import ConnectTerminalScreen

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=True))
    iface = db.insert_interface(Interface(label="TNC", iface_type="kiss_tcp", host="localhost", port=8910))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=0, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        assert isinstance(app.screen, ConnectTerminalScreen)
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
uv run pytest tests/test_ui/test_tui.py::test_open_terminal_connect_pushes_screen -v
```

Expected: FAIL — `open_terminal_connect` method does not exist on `OpenPacketApp`.

- [ ] **Step 3: Add session state and `open_terminal_connect` to `app.py`**

In `open_packet/ui/tui/app.py`, make these changes:

Add imports near the top (with the other imports):
```python
from open_packet.terminal.session import TerminalSession, TerminalConnectResult
from open_packet.ui.tui.screens.connect_terminal import ConnectTerminalScreen
```

In `OpenPacketApp.__init__`, after `self._pending_neighbor_prompts: list = []`:
```python
        self._terminal_sessions: list[TerminalSession] = []
        self._active_session_idx: Optional[int] = None
```

Add these methods to `OpenPacketApp` (after `open_compose_bulletin`):

```python
    def open_terminal_connect(self) -> None:
        if self._db is None:
            return
        self.push_screen(
            ConnectTerminalScreen(db=self._db),
            callback=self._on_connect_terminal_result,
        )

    def _on_connect_terminal_result(self, result: Optional[TerminalConnectResult]) -> None:
        if result is None:
            return
        iface = result.interface
        op = self._active_operator
        if op is None:
            return

        match iface.iface_type:
            case "telnet":
                connection = TelnetLink(
                    host=iface.host, port=iface.port,
                    username=iface.username, password=iface.password,
                )
            case "kiss_tcp":
                transport = TCPTransport(host=iface.host, port=iface.port)
                connection = AX25Connection(
                    kiss=KISSLink(transport=transport),
                    my_callsign=op.callsign,
                    my_ssid=op.ssid,
                )
            case "kiss_serial":
                transport = SerialTransport(device=iface.device, baud=iface.baud)
                connection = AX25Connection(
                    kiss=KISSLink(transport=transport),
                    my_callsign=op.callsign,
                    my_ssid=op.ssid,
                )
            case _:
                return

        session = TerminalSession(
            label=result.label,
            connection=connection,
            target_callsign=result.target_callsign,
            target_ssid=result.target_ssid,
        )
        session.start()
        self._terminal_sessions.append(session)
        self._refresh_sessions()

    def disconnect_session(self) -> None:
        idx = self._active_session_idx
        if idx is None or idx >= len(self._terminal_sessions):
            return
        self._terminal_sessions[idx].disconnect()
        self._terminal_sessions.pop(idx)
        self._active_session_idx = None
        self._refresh_sessions()
        try:
            self.query_one("MainScreen").show_messages()
        except Exception:
            pass

    def _refresh_sessions(self) -> None:
        try:
            self.query_one("FolderTree").update_sessions(self._terminal_sessions)
        except Exception:
            pass
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
uv run pytest tests/test_ui/test_tui.py::test_open_terminal_connect_pushes_screen -v
```

Expected: PASS.

- [ ] **Step 5: Write the session polling and event handler tests**

Add to `tests/test_ui/test_tui.py`:

```python
@pytest.mark.asyncio
async def test_poll_events_routes_session_lines_to_terminal_view(app_config, tmp_path):
    """Lines from an active session appear in TerminalView."""
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node, Interface
    from open_packet.terminal.session import TerminalSession
    from open_packet.ui.tui.widgets.terminal_view import TerminalView
    from open_packet.ui.tui.screens.main import MainScreen
    from unittest.mock import MagicMock

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=True))
    iface = db.insert_interface(Interface(label="TNC", iface_type="kiss_tcp", host="localhost", port=8910))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=0, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        await pilot.pause()

        # Inject a fake session with a pending line
        fake_session = MagicMock(spec=TerminalSession)
        fake_session.label = "W0XYZ"
        fake_session.status = "connected"
        fake_session.has_unread = False
        fake_session.poll.return_value = ["hello from W0XYZ"]

        app._terminal_sessions = [fake_session]
        app._active_session_idx = 0

        main = app.query_one(MainScreen)
        main.show_terminal()
        await pilot.pause()

        # Trigger a poll cycle
        app._poll_events()
        await pilot.pause()

        # TerminalView should have received the line (no exception = success)
        tv = main.query_one(TerminalView)
        assert tv.display is True


@pytest.mark.asyncio
async def test_poll_events_sets_has_unread_for_inactive_session(app_config, tmp_path):
    """Lines arriving for a non-active session set has_unread = True."""
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node, Interface
    from open_packet.terminal.session import TerminalSession
    from unittest.mock import MagicMock

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=True))
    iface = db.insert_interface(Interface(label="TNC", iface_type="kiss_tcp", host="localhost", port=8910))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=0, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        await pilot.pause()

        fake_session = MagicMock(spec=TerminalSession)
        fake_session.label = "W0XYZ"
        fake_session.status = "connected"
        fake_session.has_unread = False
        fake_session.poll.return_value = ["incoming data"]

        app._terminal_sessions = [fake_session]
        app._active_session_idx = None  # not viewing this session

        app._poll_events()
        await pilot.pause()

        assert fake_session.has_unread is True
```

- [ ] **Step 6: Run the new tests to confirm they fail**

```bash
uv run pytest tests/test_ui/test_tui.py::test_poll_events_routes_session_lines_to_terminal_view tests/test_ui/test_tui.py::test_poll_events_sets_has_unread_for_inactive_session -v
```

Expected: FAIL — polling doesn't handle sessions yet.

- [ ] **Step 7: Update `_poll_events` and add session event handlers in `app.py`**

Replace the existing `_poll_events` method:

```python
    def _poll_events(self) -> None:
        while not self._evt_queue.empty():
            try:
                event = self._evt_queue.get_nowait()
                self._handle_event(event)
            except queue.Empty:
                break

        if not self._terminal_sessions:
            return

        needs_sidebar_refresh = False
        for i, session in enumerate(self._terminal_sessions):
            lines = session.poll()
            if lines:
                if i == self._active_session_idx:
                    try:
                        tv = self.query_one("TerminalView")
                        for line in lines:
                            tv.append_line(line)
                    except Exception:
                        pass
                else:
                    session.has_unread = True
                    needs_sidebar_refresh = True

        if needs_sidebar_refresh:
            self._refresh_sessions()
```

Add these two event handlers to `OpenPacketApp` (after `on_folder_tree_folder_selected`):

```python
    def on_folder_tree_session_selected(self, event) -> None:
        idx = event.session_idx
        if idx >= len(self._terminal_sessions):
            return
        self._active_session_idx = idx
        session = self._terminal_sessions[idx]
        session.has_unread = False
        self._refresh_sessions()
        try:
            from open_packet.ui.tui.screens.main import MainScreen
            main = self.query_one(MainScreen)
            main.show_terminal()
            tv = main.query_one("TerminalView")
            tv.set_header(f"{session.label} — {session.status}")
        except Exception:
            pass

    def on_terminal_view_line_submitted(self, event) -> None:
        idx = self._active_session_idx
        if idx is None or idx >= len(self._terminal_sessions):
            return
        session = self._terminal_sessions[idx]
        session.send(event.text)
        try:
            self.query_one("TerminalView").append_line(f"> {event.text}")
        except Exception:
            pass
```

- [ ] **Step 8: Run the new tests to confirm they pass**

```bash
uv run pytest tests/test_ui/test_tui.py::test_poll_events_routes_session_lines_to_terminal_view tests/test_ui/test_tui.py::test_poll_events_sets_has_unread_for_inactive_session -v
```

Expected: both PASS.

- [ ] **Step 9: Run the full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 10: Commit**

```bash
git add open_packet/ui/tui/app.py tests/test_ui/test_tui.py
git commit -m "feat: wire terminal sessions into OpenPacketApp — polling, sidebar, input routing"
```
