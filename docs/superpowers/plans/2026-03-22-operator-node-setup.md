# Operator and Node Setup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add in-TUI setup screens for configuring operators and nodes, with automatic first-run detection and an always-accessible Settings modal reachable via `s`.

**Architecture:** Three new `ModalScreen` subclasses (`SettingsScreen`, `OperatorSetupScreen`, `NodeSetupScreen`) are wired into `MainScreen` (for the `s` binding) and `OpenPacketApp` (for dismiss handlers and first-run detection). `OpenPacketApp` gains `self._db` tracking, `_restart_engine()`, `_save_operator()`, `_save_node()`, branching first-run detection, and dismiss handlers for all three screens. Two helper methods are added to `Database`.

**Tech Stack:** Python 3.11+, Textual (`ModalScreen`, `Button`, `Input`, `Switch`, `Label`), pytest + pytest-asyncio.

---

## File Map

```
open_packet/store/database.py               MODIFY — add clear_default_operator(), clear_default_node()
open_packet/ui/tui/screens/settings.py      CREATE — SettingsScreen modal menu
open_packet/ui/tui/screens/setup_operator.py CREATE — OperatorSetupScreen form modal
open_packet/ui/tui/screens/setup_node.py    CREATE — NodeSetupScreen form modal
open_packet/ui/tui/screens/main.py          MODIFY — add 's' binding + action_settings()
open_packet/ui/tui/app.py                   MODIFY — self._db, first-run detection, dismiss
                                                      handlers, _restart_engine, _save_operator,
                                                      _save_node
tests/test_store/test_database_helpers.py   CREATE — tests for clear_default_* methods
tests/test_ui/test_setup_screens.py         CREATE — screen unit tests + integration tests
```

---

## Task 1: Database clear_default helpers

**Files:**
- Modify: `open_packet/store/database.py`
- Create: `tests/test_store/test_database_helpers.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_store/test_database_helpers.py
import pytest
import tempfile
import os
from open_packet.store.database import Database
from open_packet.store.models import Operator, Node


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "test.db"))
    d.initialize()
    yield d
    d.close()


def test_clear_default_operator_clears_existing(db):
    db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="a", is_default=True))
    db.insert_operator(Operator(callsign="W0TEST", ssid=0, label="b", is_default=True))
    db.clear_default_operator()
    assert db.get_default_operator() is None


def test_clear_default_operator_noop_when_none_set(db):
    # Should not raise when no default exists
    db.clear_default_operator()
    assert db.get_default_operator() is None


def test_clear_default_node_clears_existing(db):
    db.insert_node(Node(label="BBS1", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    db.insert_node(Node(label="BBS2", callsign="W0FOO", ssid=0, node_type="bpq", is_default=True))
    db.clear_default_node()
    assert db.get_default_node() is None


def test_clear_default_node_noop_when_none_set(db):
    db.clear_default_node()
    assert db.get_default_node() is None
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_store/test_database_helpers.py -v
```

Expected: `AttributeError: 'Database' object has no attribute 'clear_default_operator'`

- [ ] **Step 3: Implement the helpers**

In `open_packet/store/database.py`, add these two methods after `get_default_node`:

```python
def clear_default_operator(self) -> None:
    assert self._conn
    self._conn.execute("UPDATE operators SET is_default=0 WHERE is_default=1")
    self._conn.commit()

def clear_default_node(self) -> None:
    assert self._conn
    self._conn.execute("UPDATE nodes SET is_default=0 WHERE is_default=1")
    self._conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_store/test_database_helpers.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Run full suite to confirm no regressions**

```bash
uv run pytest -v
```

Expected: all 50 existing tests plus 4 new = 54 total pass.

- [ ] **Step 6: Commit**

```bash
git add open_packet/store/database.py tests/test_store/test_database_helpers.py
git commit -m "feat: add clear_default_operator and clear_default_node to Database"
```

---

## Task 2: SettingsScreen

**Files:**
- Create: `open_packet/ui/tui/screens/settings.py`
- Create: `tests/test_ui/test_setup_screens.py` (first section only)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ui/test_setup_screens.py
import pytest
from textual.app import App
from textual.widgets import Label
from open_packet.ui.tui.screens.settings import SettingsScreen
from open_packet.ui.tui.screens.setup_operator import OperatorSetupScreen
from open_packet.ui.tui.screens.setup_node import NodeSetupScreen


_SENTINEL = object()


class _ScreenTestApp(App):
    """Minimal wrapper app for testing modal screens in isolation."""
    def __init__(self, screen_factory, **kwargs):
        super().__init__(**kwargs)
        self._screen_factory = screen_factory
        self.dismiss_result = _SENTINEL

    def on_mount(self) -> None:
        def capture(result):
            self.dismiss_result = result
        self.push_screen(self._screen_factory(), callback=capture)


@pytest.mark.asyncio
async def test_settings_operator_button():
    app = _ScreenTestApp(SettingsScreen)
    async with app.run_test() as pilot:
        await pilot.click("#operator_btn")
        await pilot.pause()
    assert app.dismiss_result == "operator"


@pytest.mark.asyncio
async def test_settings_node_button():
    app = _ScreenTestApp(SettingsScreen)
    async with app.run_test() as pilot:
        await pilot.click("#node_btn")
        await pilot.pause()
    assert app.dismiss_result == "node"


@pytest.mark.asyncio
async def test_settings_close_button():
    app = _ScreenTestApp(SettingsScreen)
    async with app.run_test() as pilot:
        await pilot.click("#close_btn")
        await pilot.pause()
    assert app.dismiss_result is None
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_ui/test_setup_screens.py::test_settings_operator_button -v
```

Expected: `ImportError: cannot import name 'SettingsScreen'`

- [ ] **Step 3: Implement SettingsScreen**

```python
# open_packet/ui/tui/screens/settings.py
from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from textual.containers import Vertical


class SettingsScreen(ModalScreen):
    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
    }
    SettingsScreen Vertical {
        width: 40;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    SettingsScreen Button {
        width: 100%;
        margin: 0 0 1 0;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Settings")
            yield Button("Operator", id="operator_btn")
            yield Button("Node", id="node_btn")
            yield Button("Close", id="close_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "operator_btn":
            self.dismiss("operator")
        elif event.button.id == "node_btn":
            self.dismiss("node")
        else:
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_ui/test_setup_screens.py -k "settings" -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add open_packet/ui/tui/screens/settings.py tests/test_ui/test_setup_screens.py
git commit -m "feat: SettingsScreen modal with operator/node menu"
```

---

## Task 3: OperatorSetupScreen

**Files:**
- Create: `open_packet/ui/tui/screens/setup_operator.py`
- Modify: `tests/test_ui/test_setup_screens.py` (append tests)

- [ ] **Step 1: Append the failing tests**

Add to `tests/test_ui/test_setup_screens.py`:

```python
@pytest.mark.asyncio
async def test_operator_setup_valid_input():
    app = _ScreenTestApp(OperatorSetupScreen)
    async with app.run_test() as pilot:
        await pilot.click("#callsign_field")
        await pilot.type("kd9abc")
        await pilot.click("#ssid_field")
        await pilot.type("1")
        await pilot.click("#label_field")
        await pilot.type("home")
        await pilot.click("#save_btn")
        await pilot.pause()
    result = app.dismiss_result
    assert result is not _SENTINEL
    assert result is not None
    assert result.callsign == "KD9ABC"  # uppercased
    assert result.ssid == 1
    assert result.label == "home"
    assert result.is_default is True


@pytest.mark.asyncio
async def test_operator_setup_blank_callsign_does_not_dismiss():
    app = _ScreenTestApp(OperatorSetupScreen)
    async with app.run_test() as pilot:
        await pilot.click("#ssid_field")
        await pilot.type("1")
        await pilot.click("#label_field")
        await pilot.type("home")
        await pilot.click("#save_btn")
        await pilot.pause()
    assert app.dismiss_result is _SENTINEL  # never dismissed


@pytest.mark.asyncio
async def test_operator_setup_invalid_ssid_does_not_dismiss():
    app = _ScreenTestApp(OperatorSetupScreen)
    async with app.run_test() as pilot:
        await pilot.click("#callsign_field")
        await pilot.type("KD9ABC")
        await pilot.click("#ssid_field")
        await pilot.type("99")
        await pilot.click("#label_field")
        await pilot.type("home")
        await pilot.click("#save_btn")
        await pilot.pause()
    assert app.dismiss_result is _SENTINEL


@pytest.mark.asyncio
async def test_operator_setup_cancel():
    app = _ScreenTestApp(OperatorSetupScreen)
    async with app.run_test() as pilot:
        await pilot.click("#cancel_btn")
        await pilot.pause()
    assert app.dismiss_result is None
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_ui/test_setup_screens.py -k "operator_setup" -v
```

Expected: `ImportError: cannot import name 'OperatorSetupScreen'`

- [ ] **Step 3: Implement OperatorSetupScreen**

```python
# open_packet/ui/tui/screens/setup_operator.py
from __future__ import annotations
import re
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Switch
from textual.containers import Vertical, Horizontal
from open_packet.store.models import Operator


CALLSIGN_RE = re.compile(r'^[A-Za-z0-9]{1,6}$')


class OperatorSetupScreen(ModalScreen):
    DEFAULT_CSS = """
    OperatorSetupScreen {
        align: center middle;
    }
    OperatorSetupScreen Vertical {
        width: 50;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    OperatorSetupScreen .error {
        color: $error;
        height: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Operator Setup")
            yield Label("Callsign:")
            yield Input(placeholder="e.g. KD9ABC", id="callsign_field")
            yield Label("", id="callsign_error", classes="error")
            yield Label("SSID (0-15):")
            yield Input(placeholder="0", id="ssid_field")
            yield Label("", id="ssid_error", classes="error")
            yield Label("Label:")
            yield Input(placeholder="e.g. home", id="label_field")
            yield Label("", id="label_error", classes="error")
            yield Label("Set as default:")
            yield Switch(value=True, id="default_switch")
            with Horizontal():
                yield Button("Save", variant="primary", id="save_btn")
                yield Button("Cancel", id="cancel_btn")

    def _validate(self) -> bool:
        valid = True
        callsign = self.query_one("#callsign_field", Input).value.strip()
        ssid_str = self.query_one("#ssid_field", Input).value.strip()
        label = self.query_one("#label_field", Input).value.strip()

        callsign_error = self.query_one("#callsign_error", Label)
        ssid_error = self.query_one("#ssid_error", Label)
        label_error = self.query_one("#label_error", Label)

        if not CALLSIGN_RE.match(callsign):
            callsign_error.update("Callsign must be 1-6 alphanumeric characters")
            valid = False
        else:
            callsign_error.update("")

        try:
            ssid = int(ssid_str)
            if not 0 <= ssid <= 15:
                raise ValueError
            ssid_error.update("")
        except ValueError:
            ssid_error.update("SSID must be an integer 0-15")
            valid = False

        if not label:
            label_error.update("Label is required")
            valid = False
        else:
            label_error.update("")

        return valid

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.dismiss(None)
        elif event.button.id == "save_btn":
            if self._validate():
                callsign = self.query_one("#callsign_field", Input).value.strip().upper()
                ssid = int(self.query_one("#ssid_field", Input).value.strip())
                label = self.query_one("#label_field", Input).value.strip()
                is_default = self.query_one("#default_switch", Switch).value
                self.dismiss(Operator(
                    callsign=callsign,
                    ssid=ssid,
                    label=label,
                    is_default=is_default,
                ))

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_ui/test_setup_screens.py -k "operator_setup" -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add open_packet/ui/tui/screens/setup_operator.py tests/test_ui/test_setup_screens.py
git commit -m "feat: OperatorSetupScreen modal with form validation"
```

---

## Task 4: NodeSetupScreen

**Files:**
- Create: `open_packet/ui/tui/screens/setup_node.py`
- Modify: `tests/test_ui/test_setup_screens.py` (append tests)

- [ ] **Step 1: Append the failing tests**

Add to `tests/test_ui/test_setup_screens.py`:

```python
@pytest.mark.asyncio
async def test_node_setup_valid_input():
    app = _ScreenTestApp(NodeSetupScreen)
    async with app.run_test() as pilot:
        await pilot.click("#label_field")
        await pilot.type("Home BBS")
        await pilot.click("#callsign_field")
        await pilot.type("w0bpq")
        await pilot.click("#ssid_field")
        await pilot.type("1")
        await pilot.click("#save_btn")
        await pilot.pause()
    result = app.dismiss_result
    assert result is not _SENTINEL
    assert result is not None
    assert result.label == "Home BBS"
    assert result.callsign == "W0BPQ"  # uppercased
    assert result.ssid == 1
    assert result.node_type == "bpq"
    assert result.is_default is True


@pytest.mark.asyncio
async def test_node_setup_blank_callsign_does_not_dismiss():
    app = _ScreenTestApp(NodeSetupScreen)
    async with app.run_test() as pilot:
        await pilot.click("#label_field")
        await pilot.type("Home BBS")
        await pilot.click("#ssid_field")
        await pilot.type("0")
        await pilot.click("#save_btn")
        await pilot.pause()
    assert app.dismiss_result is _SENTINEL


@pytest.mark.asyncio
async def test_node_setup_invalid_ssid_does_not_dismiss():
    app = _ScreenTestApp(NodeSetupScreen)
    async with app.run_test() as pilot:
        await pilot.click("#label_field")
        await pilot.type("Home BBS")
        await pilot.click("#callsign_field")
        await pilot.type("W0BPQ")
        await pilot.click("#ssid_field")
        await pilot.type("abc")
        await pilot.click("#save_btn")
        await pilot.pause()
    assert app.dismiss_result is _SENTINEL


@pytest.mark.asyncio
async def test_node_setup_cancel():
    app = _ScreenTestApp(NodeSetupScreen)
    async with app.run_test() as pilot:
        await pilot.click("#cancel_btn")
        await pilot.pause()
    assert app.dismiss_result is None
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_ui/test_setup_screens.py -k "node_setup" -v
```

Expected: `ImportError: cannot import name 'NodeSetupScreen'`

- [ ] **Step 3: Implement NodeSetupScreen**

```python
# open_packet/ui/tui/screens/setup_node.py
from __future__ import annotations
import re
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Switch
from textual.containers import Vertical, Horizontal
from open_packet.store.models import Node


CALLSIGN_RE = re.compile(r'^[A-Za-z0-9]{1,6}$')


class NodeSetupScreen(ModalScreen):
    DEFAULT_CSS = """
    NodeSetupScreen {
        align: center middle;
    }
    NodeSetupScreen Vertical {
        width: 50;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    NodeSetupScreen .error {
        color: $error;
        height: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Node Setup")
            yield Label("Label:")
            yield Input(placeholder="e.g. Home BBS", id="label_field")
            yield Label("", id="label_error", classes="error")
            yield Label("Callsign:")
            yield Input(placeholder="e.g. W0BPQ", id="callsign_field")
            yield Label("", id="callsign_error", classes="error")
            yield Label("SSID (0-15):")
            yield Input(placeholder="0", id="ssid_field")
            yield Label("", id="ssid_error", classes="error")
            yield Label("Node Type: bpq")
            yield Label("Set as default:")
            yield Switch(value=True, id="default_switch")
            with Horizontal():
                yield Button("Save", variant="primary", id="save_btn")
                yield Button("Cancel", id="cancel_btn")

    def _validate(self) -> bool:
        valid = True
        label = self.query_one("#label_field", Input).value.strip()
        callsign = self.query_one("#callsign_field", Input).value.strip()
        ssid_str = self.query_one("#ssid_field", Input).value.strip()

        label_error = self.query_one("#label_error", Label)
        callsign_error = self.query_one("#callsign_error", Label)
        ssid_error = self.query_one("#ssid_error", Label)

        if not label:
            label_error.update("Label is required")
            valid = False
        else:
            label_error.update("")

        if not CALLSIGN_RE.match(callsign):
            callsign_error.update("Callsign must be 1-6 alphanumeric characters")
            valid = False
        else:
            callsign_error.update("")

        try:
            ssid = int(ssid_str)
            if not 0 <= ssid <= 15:
                raise ValueError
            ssid_error.update("")
        except ValueError:
            ssid_error.update("SSID must be an integer 0-15")
            valid = False

        return valid

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.dismiss(None)
        elif event.button.id == "save_btn":
            if self._validate():
                label = self.query_one("#label_field", Input).value.strip()
                callsign = self.query_one("#callsign_field", Input).value.strip().upper()
                ssid = int(self.query_one("#ssid_field", Input).value.strip())
                is_default = self.query_one("#default_switch", Switch).value
                self.dismiss(Node(
                    label=label,
                    callsign=callsign,
                    ssid=ssid,
                    node_type="bpq",
                    is_default=is_default,
                ))

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_ui/test_setup_screens.py -k "node_setup" -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Run all setup screen tests so far**

```bash
uv run pytest tests/test_ui/test_setup_screens.py -v
```

Expected: 11 tests pass (3 settings + 4 operator + 4 node).

- [ ] **Step 6: Commit**

```bash
git add open_packet/ui/tui/screens/setup_node.py tests/test_ui/test_setup_screens.py
git commit -m "feat: NodeSetupScreen modal with form validation"
```

---

## Task 5: Wire MainScreen and OpenPacketApp

**Files:**
- Modify: `open_packet/ui/tui/screens/main.py`
- Modify: `open_packet/ui/tui/app.py`
- Modify: `tests/test_ui/test_setup_screens.py` (append integration tests)

This task wires everything together: `s` key → `SettingsScreen`, first-run detection, dismiss handlers, `_restart_engine`.

- [ ] **Step 1: Append the failing integration tests**

Add to `tests/test_ui/test_setup_screens.py`:

```python
import tempfile
import os
from open_packet.ui.tui.app import OpenPacketApp
from open_packet.config.config import AppConfig, TCPConnectionConfig, StoreConfig, UIConfig
from open_packet.store.database import Database
from open_packet.store.models import Operator, Node


@pytest.fixture
def base_config(tmp_path):
    return AppConfig(
        connection=TCPConnectionConfig(type="kiss_tcp", host="localhost", port=8001),
        store=StoreConfig(
            db_path=str(tmp_path / "test.db"),
            export_path=str(tmp_path / "export"),
        ),
        ui=UIConfig(),
    )


@pytest.mark.asyncio
async def test_first_run_pushes_operator_setup(base_config):
    """Empty DB: OperatorSetupScreen is pushed on mount."""
    app = OpenPacketApp(config=base_config)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, OperatorSetupScreen)


@pytest.mark.asyncio
async def test_first_run_node_missing_pushes_node_setup(base_config, tmp_path):
    """Operator exists but no node: NodeSetupScreen is pushed."""
    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    db.close()

    app = OpenPacketApp(config=base_config)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, NodeSetupScreen)


@pytest.mark.asyncio
async def test_partial_first_run_cancel_engine_stays_none(base_config):
    """Operator saved, NodeSetupScreen cancelled: engine stays uninitialized."""
    app = OpenPacketApp(config=base_config)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, OperatorSetupScreen)
        # Fill and save operator
        await pilot.click("#callsign_field")
        await pilot.type("KD9ABC")
        await pilot.click("#ssid_field")
        await pilot.type("1")
        await pilot.click("#label_field")
        await pilot.type("home")
        await pilot.click("#save_btn")
        await pilot.pause()
        # Now NodeSetupScreen should be shown
        assert isinstance(app.screen, NodeSetupScreen)
        # Cancel node setup
        await pilot.click("#cancel_btn")
        await pilot.pause()
    assert app._engine is None
    assert app._db is not None  # db was opened


@pytest.mark.asyncio
async def test_engine_reinit_after_full_setup(base_config):
    """Completing operator + node setup initializes the engine."""
    app = OpenPacketApp(config=base_config)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        # Fill operator
        await pilot.click("#callsign_field")
        await pilot.type("KD9ABC")
        await pilot.click("#ssid_field")
        await pilot.type("1")
        await pilot.click("#label_field")
        await pilot.type("home")
        await pilot.click("#save_btn")
        await pilot.pause()
        # Fill node
        await pilot.click("#label_field")
        await pilot.type("Home BBS")
        await pilot.click("#callsign_field")
        await pilot.type("W0BPQ")
        await pilot.click("#ssid_field")
        await pilot.type("1")
        await pilot.click("#save_btn")
        await pilot.pause()
        await pilot.pause()
    assert app._engine is not None
    app._engine.stop()
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_ui/test_setup_screens.py -k "first_run or engine_reinit or partial" -v
```

Expected: failures — the logic doesn't exist yet in the app.

- [ ] **Step 3: Update MainScreen**

In `open_packet/ui/tui/screens/main.py`, make these changes:

Add import at the top:
```python
from open_packet.ui.tui.screens.settings import SettingsScreen
```

Add `("s", "settings", "Settings")` to BINDINGS:
```python
BINDINGS = [
    ("c", "check_mail", "Check Mail"),
    ("n", "new_message", "New"),
    ("d", "delete_message", "Delete"),
    ("r", "reply_message", "Reply"),
    ("s", "settings", "Settings"),
    ("`", "toggle_console", "Console"),
    ("q", "quit", "Quit"),
]
```

Add the action method (after `action_reply_message`):
```python
def action_settings(self) -> None:
    self.app.push_screen(SettingsScreen())
```

- [ ] **Step 4: Update OpenPacketApp**

Replace `open_packet/ui/tui/app.py` with this complete updated version:

```python
# open_packet/ui/tui/app.py
from __future__ import annotations
import logging
import os
import queue
from typing import Optional

from textual.app import App

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
from open_packet.store.models import Operator, Node
from open_packet.store.store import Store
from open_packet.transport.tcp import TCPTransport
from open_packet.transport.serial import SerialTransport
from open_packet.ui.tui.screens.compose import ComposeScreen
from open_packet.ui.tui.screens.main import MainScreen
from open_packet.ui.tui.screens.settings import SettingsScreen
from open_packet.ui.tui.screens.setup_operator import OperatorSetupScreen
from open_packet.ui.tui.screens.setup_node import NodeSetupScreen

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
    SCREENS = {"compose": ComposeScreen}
    TITLE = "open-packet"

    def __init__(self, config: AppConfig, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self._cmd_queue: queue.Queue = queue.Queue()
        self._evt_queue: queue.Queue = queue.Queue()
        self._engine: Optional[Engine] = None
        self._selected_message = None
        self._store: Optional[Store] = None
        self._active_operator: Optional[Operator] = None
        self._active_folder = "Inbox"
        self._active_category = ""
        self._db: Optional[Database] = None

    def get_default_screen(self) -> MainScreen:
        return MainScreen()

    def on_mount(self) -> None:
        self._init_engine()
        self.set_interval(0.1, self._poll_events)
        self.call_after_refresh(self._refresh_message_list)

    def _init_engine(self) -> None:
        db_path = os.path.expanduser(self.config.store.db_path)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        db = Database(db_path)
        db.initialize()
        # Assign self._db BEFORE any early return so _restart_engine can close it.
        self._db = db

        operator = db.get_default_operator()
        node_record = db.get_default_node()

        if not operator and not node_record:
            self.call_after_refresh(lambda: self.push_screen(OperatorSetupScreen()))
            return
        elif not operator:
            self.call_after_refresh(lambda: self.push_screen(OperatorSetupScreen()))
            return
        elif not node_record:
            self.call_after_refresh(lambda: self.push_screen(NodeSetupScreen()))
            return

        store = Store(db)
        self._store = store
        self._active_operator = operator

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

        export_path = (
            os.path.expanduser(self.config.store.export_path)
            if self.config.store.export_path else None
        )

        self._engine = Engine(
            command_queue=self._cmd_queue,
            event_queue=self._evt_queue,
            store=store,
            operator=operator,
            node_record=node_record,
            connection=connection,
            node=node,
            export_path=export_path,
        )
        self._engine.start()

    def _restart_engine(self) -> None:
        if self._engine is not None:
            self._engine.stop()
        if self._db is not None:
            self._db.close()
        self._engine = None
        self._store = None
        self._active_operator = None
        self._db = None
        self._init_engine()

    def _save_operator(self, op: Operator) -> None:
        if op.is_default:
            self._db.clear_default_operator()
        self._db.insert_operator(op)

    def _save_node(self, node: Node) -> None:
        if node.is_default:
            self._db.clear_default_node()
        self._db.insert_node(node)

    # --- Dismiss handlers ---

    def on_settings_screen_dismiss(self, result) -> None:
        if result == "operator":
            self.push_screen(OperatorSetupScreen())
        elif result == "node":
            self.push_screen(NodeSetupScreen())

    def on_operator_setup_screen_dismiss(self, result) -> None:
        if result is None:
            return
        self._save_operator(result)
        # Check DB state to determine next step (works for both first-run and settings flow)
        if self._db.get_default_node() is None:
            self.push_screen(NodeSetupScreen())
        else:
            self._restart_engine()

    def on_node_setup_screen_dismiss(self, result) -> None:
        if result is None:
            return
        self._save_node(result)
        self._restart_engine()

    # --- Event polling ---

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
        if not self._store or not self._active_operator:
            return
        try:
            msg_list = self.query_one("MessageList")
            folder = self._active_folder
            category = self._active_category
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
        self._active_folder = event.folder
        self._active_category = getattr(event, "category", "")
        self._refresh_message_list()


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

- [ ] **Step 5: Run the integration tests**

```bash
uv run pytest tests/test_ui/test_setup_screens.py -v
```

Expected: all 15 tests pass (11 screen unit tests + 4 integration tests).

- [ ] **Step 6: Run the full suite**

```bash
uv run pytest -v
```

Expected: all tests pass (54 existing + new setup screen tests).

- [ ] **Step 7: Commit**

```bash
git add open_packet/ui/tui/screens/main.py open_packet/ui/tui/app.py tests/test_ui/test_setup_screens.py
git commit -m "feat: wire operator/node setup screens into MainScreen and OpenPacketApp"
```

---

## Final Checklist

- [ ] `uv run pytest` passes with zero failures
- [ ] Pressing `s` in the TUI opens the Settings modal
- [ ] With an empty database, `OperatorSetupScreen` appears on first launch
- [ ] With operator configured but no node, `NodeSetupScreen` appears on first launch
- [ ] Completing both setup screens initializes the engine
- [ ] Cancelling node setup after saving operator leaves operator in DB; next launch shows only `NodeSetupScreen`
