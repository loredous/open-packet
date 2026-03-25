# Status Bar Identity Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Display the active operator callsign, node label, and interface label in a right-aligned section of the TUI status bar, alongside the existing connection state on the left.

**Architecture:** Two sequential tasks. Task 1 refactors `StatusBar` from a single `render()` widget into a container with two `Label` children (`#status_left`, `#status_right`), driven by reactive watchers. Task 2 wires `OpenPacketApp` to populate those reactives from the active operator/node/interface at every engine lifecycle call site.

**Tech Stack:** Python 3.12, Textual (TUI framework), pytest with `asyncio_mode = "auto"` (no `@pytest.mark.asyncio` decorator needed on async tests — it is set in `pyproject.toml`)

---

### Task 1: Refactor StatusBar widget

**Files:**
- Create: `tests/test_ui/test_status_bar.py`
- Modify: `open_packet/ui/tui/widgets/status_bar.py`

**Background:** The current `StatusBar` is a leaf `Widget` with a single `render()` method that returns a plain string. It has three reactives: `callsign` (never set, shows `---`), `status`, and `last_sync`. We are replacing it with a container widget that composes two `Label` children and uses reactive watchers to update them independently. The `callsign` reactive and its `---` placeholder are removed.

---

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ui/test_status_bar.py` with this content:

```python
# tests/test_ui/test_status_bar.py
from textual.app import App, ComposeResult
from open_packet.ui.tui.widgets.status_bar import StatusBar
from open_packet.engine.events import ConnectionStatus


class StatusBarApp(App):
    def compose(self) -> ComposeResult:
        yield StatusBar(id="status_bar")


async def test_left_label_shows_emoji_and_app_name():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        left = app.query_one("#status_left")
        assert "📻 open-packet" in str(left.renderable)


async def test_left_label_shows_disconnected_icon_by_default():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        left = app.query_one("#status_left")
        assert "○" in str(left.renderable)  # DISCONNECTED icon


async def test_left_label_updates_on_status_change():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.status = ConnectionStatus.CONNECTED
        await pilot.pause()
        left = app.query_one("#status_left")
        text = str(left.renderable)
        assert "●" in text
        assert "Connected" in text


async def test_left_label_updates_on_last_sync_change():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.last_sync = "13:45"
        await pilot.pause()
        left = app.query_one("#status_left")
        assert "13:45" in str(left.renderable)


async def test_right_label_empty_by_default():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        right = app.query_one("#status_right")
        assert str(right.renderable) == ""


async def test_right_label_shows_operator_with_separator():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.operator = "W1AW"
        await pilot.pause()
        text = str(app.query_one("#status_right").renderable)
        assert "W1AW" in text
        assert "│" in text


async def test_right_label_shows_all_three_fields():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.operator = "W1AW"
        sb.node = "Home BBS"
        sb.interface_label = "Home TNC"
        await pilot.pause()
        text = str(app.query_one("#status_right").renderable)
        assert "W1AW" in text
        assert "Home BBS" in text
        assert "Home TNC" in text
        assert "│" in text
        assert ":" in text


async def test_right_label_clears_when_all_fields_empty():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.operator = "W1AW"
        await pilot.pause()
        sb.operator = ""
        await pilot.pause()
        assert str(app.query_one("#status_right").renderable) == ""


async def test_left_label_does_not_contain_triple_dash():
    """The old callsign placeholder '---' must not appear in the new implementation."""
    app = StatusBarApp()
    async with app.run_test() as pilot:
        left = app.query_one("#status_left")
        assert "---" not in str(left.renderable)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_ui/test_status_bar.py -v
```

Expected: most tests fail (widget still has old `render()` implementation, no `#status_left` / `#status_right` children).

- [ ] **Step 3: Implement the new StatusBar**

Replace the entire contents of `open_packet/ui/tui/widgets/status_bar.py` with:

```python
# open_packet/ui/tui/widgets/status_bar.py
from __future__ import annotations
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label
from textual.reactive import reactive
from open_packet.engine.events import ConnectionStatus


class StatusBar(Widget):
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
        layout: horizontal;
    }
    #status_left {
        width: 1fr;
    }
    #status_right {
        width: auto;
    }
    """

    status: reactive[ConnectionStatus] = reactive(ConnectionStatus.DISCONNECTED)
    last_sync: reactive[str] = reactive("Never")
    operator: reactive[str] = reactive("")
    node: reactive[str] = reactive("")
    interface_label: reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        yield Label("", id="status_left")
        yield Label("", id="status_right")

    def on_mount(self) -> None:
        self._render_left()
        self._render_right()

    # --- Watchers ---

    def watch_status(self, _) -> None:
        self._render_left()

    def watch_last_sync(self, _) -> None:
        self._render_left()

    def watch_operator(self, _) -> None:
        self._render_right()

    def watch_node(self, _) -> None:
        self._render_right()

    def watch_interface_label(self, _) -> None:
        self._render_right()

    # --- Render helpers ---

    def _render_left(self) -> None:
        icon = {
            ConnectionStatus.DISCONNECTED: "○",
            ConnectionStatus.CONNECTING: "◎",
            ConnectionStatus.CONNECTED: "●",
            ConnectionStatus.SYNCING: "⟳",
            ConnectionStatus.ERROR: "✗",
        }.get(self.status, "?")
        text = f"📻 open-packet  {icon}  {self.status.value.title()}  | Last sync: {self.last_sync}"
        try:
            self.query_one("#status_left", Label).update(text)
        except Exception:
            return

    def _render_right(self) -> None:
        fields = [f for f in [self.operator, self.node, self.interface_label] if f]
        right = ("│  " + "  :  ".join(fields)) if fields else ""
        try:
            self.query_one("#status_right", Label).update(right)
        except Exception:
            return
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_ui/test_status_bar.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Run the full test suite to confirm no regressions**

```bash
uv run pytest -v
```

Expected: all existing tests pass. If `test_tui.py` tests fail because `StatusBar` no longer has a `callsign` reactive, that is expected — Task 2 will fix them. If any other tests fail, investigate before proceeding.

- [ ] **Step 6: Commit**

```bash
git add open_packet/ui/tui/widgets/status_bar.py tests/test_ui/test_status_bar.py
git commit -m "feat: refactor StatusBar to show operator/node/interface in right section"
```

---

### Task 2: Wire app.py identity propagation

**Files:**
- Modify: `open_packet/ui/tui/app.py`
- Modify: `tests/test_ui/test_tui.py`

**Background:** `OpenPacketApp` needs to set the three new `StatusBar` reactives (`operator`, `node`, `interface_label`) whenever the engine lifecycle changes. This requires two new instance attributes (`_active_node`, `_active_interface`), a new helper `_update_status_bar_identity()`, and calls to that helper at every point where identity state becomes stable.

The call sites are:
1. `_start_engine()` — before the `interface_id is None` early return
2. `_start_engine()` — before the `iface is None` early return
3. `_start_engine()` — at the end of the success path (after engine start)
4. `_init_engine()` — before the "no operator" early return
5. `_init_engine()` — before the "no node record" early return
6. `_restart_engine()` — after clearing all identity attrs to `None`, before `_init_engine()`

---

- [ ] **Step 1: Write the failing integration tests**

Add these tests to the end of `tests/test_ui/test_tui.py`:

```python
@pytest.mark.asyncio
async def test_status_bar_shows_operator_node_interface(app_config, tmp_path):
    """After mounting with full config, status bar right section shows callsign, node, interface."""
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node, Interface

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="W1AW", ssid=0, label="home", is_default=True))
    iface = db.insert_interface(Interface(
        label="Home TNC", iface_type="kiss_tcp", host="localhost", port=8910
    ))
    db.insert_node(Node(label="Home BBS", callsign="W0BPQ", ssid=0, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        right = app.query_one("#status_right")
        text = str(right.renderable)
        assert "W1AW" in text       # ssid=0, no suffix
        assert "Home BBS" in text
        assert "Home TNC" in text


@pytest.mark.asyncio
async def test_status_bar_shows_ssid_when_nonzero(app_config, tmp_path):
    """Operator with ssid>0 is shown as callsign-ssid."""
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node, Interface

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="W1AW", ssid=3, label="mobile", is_default=True))
    iface = db.insert_interface(Interface(
        label="Mobile TNC", iface_type="kiss_tcp", host="localhost", port=8910
    ))
    db.insert_node(Node(label="Local BBS", callsign="W0BPQ", ssid=0, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        right = app.query_one("#status_right")
        assert "W1AW-3" in str(right.renderable)


@pytest.mark.asyncio
async def test_status_bar_right_empty_when_no_operator(app_config, tmp_path):
    """When no operator is configured, the right section of the status bar is empty."""
    # Don't insert any operator — DB is empty
    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        # The OperatorSetupScreen will be pushed, but we can still check the bar
        right = app.query_one("#status_right")
        assert str(right.renderable) == ""
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_ui/test_tui.py::test_status_bar_shows_operator_node_interface tests/test_ui/test_tui.py::test_status_bar_shows_ssid_when_nonzero tests/test_ui/test_tui.py::test_status_bar_right_empty_when_no_operator -v
```

Expected: all three FAIL (no `#status_right` child exists yet in the app, or it has no content).

- [ ] **Step 3: Implement app.py changes**

Edit `open_packet/ui/tui/app.py` with the following changes:

**3a. Add two new instance attributes** in `OpenPacketApp.__init__`, after the existing `self._active_operator` line (around line 64):

```python
self._active_node: Optional[Node] = None
self._active_interface: Optional[Interface] = None
```

**3b. Add the `_update_status_bar_identity()` helper method** anywhere in the class (e.g., after `_restart_engine`):

```python
def _update_status_bar_identity(self) -> None:
    op = self._active_operator
    node = self._active_node
    iface = self._active_interface
    try:
        sb = self.query_one("StatusBar")
    except Exception:
        return
    if op:
        sb.operator = f"{op.callsign}-{op.ssid}" if op.ssid != 0 else op.callsign
    else:
        sb.operator = ""
    sb.node = node.label if node else ""
    sb.interface_label = iface.label if iface else ""
```

**3c. Modify `_init_engine()`** to call `_update_status_bar_identity()` before each early return:

```python
def _init_engine(self) -> None:
    db_path = os.path.expanduser(self.config.store.db_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    db = Database(db_path)
    db.initialize()
    self._db = db

    operator = db.get_default_operator()
    node_record = db.get_default_node()

    if not operator:
        self._update_status_bar_identity()          # <-- ADD THIS
        self.call_after_refresh(
            lambda: self.push_screen(OperatorSetupScreen(), callback=self._on_operator_setup_result)
        )
        return
    elif not node_record:
        self._update_status_bar_identity()          # <-- ADD THIS
        self.call_after_refresh(
            lambda: self.push_screen(NodeSetupScreen(interfaces=self._db.list_interfaces(), db=self._db), callback=self._on_node_setup_result)
        )
        return

    self._start_engine(db, operator, node_record)
```

**3d. Modify `_start_engine()`** to assign `_active_node`/`_active_interface` and call `_update_status_bar_identity()` at each exit point:

```python
def _start_engine(self, db: Database, operator: Operator, node_record: Node) -> None:
    store = Store(db)
    self._store = store
    self._active_operator = operator

    if node_record.interface_id is None:
        self._update_status_bar_identity()          # <-- ADD THIS
        return  # no interface configured; engine stays dormant

    iface = db.get_interface(node_record.interface_id)
    if iface is None:
        self._update_status_bar_identity()          # <-- ADD THIS
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
                my_callsign=operator.callsign,
                my_ssid=operator.ssid,
            )
        case "kiss_serial":
            transport = SerialTransport(device=iface.device, baud=iface.baud)
            connection = AX25Connection(
                kiss=KISSLink(transport=transport),
                my_callsign=operator.callsign,
                my_ssid=operator.ssid,
            )
        case _:
            raise ValueError(f"Unknown interface type: {iface.iface_type!r}")

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

    self._active_node = node_record        # <-- ADD THESE THREE LINES
    self._active_interface = iface
    self._update_status_bar_identity()
```

**3e. Modify `_restart_engine()`** to clear the new attributes and call `_update_status_bar_identity()` before re-init:

```python
def _restart_engine(self) -> None:
    if self._engine is not None:
        self._engine.stop()
    if self._db is not None:
        self._db.close()
    self._engine = None
    self._store = None
    self._active_operator = None
    self._active_node = None                # <-- ADD THIS
    self._active_interface = None           # <-- ADD THIS
    self._db = None
    self._update_status_bar_identity()      # <-- ADD THIS
    self._init_engine()
```

- [ ] **Step 4: Run the new integration tests**

```bash
uv run pytest tests/test_ui/test_tui.py::test_status_bar_shows_operator_node_interface tests/test_ui/test_tui.py::test_status_bar_shows_ssid_when_nonzero tests/test_ui/test_tui.py::test_status_bar_right_empty_when_no_operator -v
```

Expected: all three PASS.

- [ ] **Step 5: Run the full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass. Investigate any failures before proceeding.

- [ ] **Step 6: Commit**

```bash
git add open_packet/ui/tui/app.py tests/test_ui/test_tui.py
git commit -m "feat: wire app identity to status bar (operator/node/interface)"
```
