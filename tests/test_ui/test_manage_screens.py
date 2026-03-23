import pytest
import tempfile
import os
from textual.app import App
from open_packet.store.database import Database
from open_packet.store.models import Operator, Node
from open_packet.ui.tui.screens.manage_operators import OperatorManageScreen
from open_packet.ui.tui.screens.manage_nodes import NodeManageScreen
from open_packet.ui.tui.screens.setup_operator import OperatorSetupScreen
from open_packet.ui.tui.screens.setup_node import NodeSetupScreen


_SENTINEL = object()


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "test.db"))
    d.initialize()
    yield d
    d.close()


@pytest.fixture
def db_with_operators(db):
    db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=True))
    db.insert_operator(Operator(callsign="W0TEST", ssid=1, label="car", is_default=False))
    return db


@pytest.fixture
def db_with_nodes(db):
    db.insert_node(Node(label="Home BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    db.insert_node(Node(label="Work BBS", callsign="W0FOO", ssid=0, node_type="bpq", is_default=False))
    return db


class _ManageTestApp(App):
    def __init__(self, screen_factory, **kwargs):
        super().__init__(**kwargs)
        self._screen_factory = screen_factory
        self.dismiss_result = _SENTINEL

    def on_mount(self) -> None:
        def capture(result):
            self.dismiss_result = result
        self.push_screen(self._screen_factory(), callback=capture)


# --- OperatorManageScreen ---

@pytest.mark.asyncio
async def test_operator_manage_close_no_changes(db_with_operators):
    db = db_with_operators
    app = _ManageTestApp(lambda: OperatorManageScreen(db))
    async with app.run_test() as pilot:
        await pilot.click("#close_btn")
        await pilot.pause()
    assert app.dismiss_result is False


@pytest.mark.asyncio
async def test_operator_manage_set_active_changes_default(db_with_operators):
    db = db_with_operators
    ops = db.list_operators()
    non_default = next(o for o in ops if not o.is_default)

    app = _ManageTestApp(lambda: OperatorManageScreen(db))
    async with app.run_test() as pilot:
        await pilot.click(f"#set_active_{non_default.id}")
        await pilot.pause()
        await pilot.click("#close_btn")
        await pilot.pause()

    assert app.dismiss_result is True
    assert db.get_default_operator().id == non_default.id


@pytest.mark.asyncio
async def test_operator_manage_escape_returns_needs_restart_false(db_with_operators):
    db = db_with_operators
    app = _ManageTestApp(lambda: OperatorManageScreen(db))
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
    assert app.dismiss_result is False


@pytest.mark.asyncio
async def test_operator_manage_shows_active_badge(db_with_operators):
    db = db_with_operators
    default_op = db.get_default_operator()
    app = _ManageTestApp(lambda: OperatorManageScreen(db))
    async with app.run_test() as pilot:
        await pilot.pause()
        # Active operator row should not have a set_active button
        assert not app.query(f"#set_active_{default_op.id}")


@pytest.mark.asyncio
async def test_operator_manage_empty_db(db):
    app = _ManageTestApp(lambda: OperatorManageScreen(db))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.click("#close_btn")
        await pilot.pause()
    assert app.dismiss_result is False


# --- NodeManageScreen ---

@pytest.mark.asyncio
async def test_node_manage_close_no_changes(db_with_nodes):
    db = db_with_nodes
    app = _ManageTestApp(lambda: NodeManageScreen(db))
    async with app.run_test() as pilot:
        await pilot.click("#close_btn")
        await pilot.pause()
    assert app.dismiss_result is False


@pytest.mark.asyncio
async def test_node_manage_set_active_changes_default(db_with_nodes):
    db = db_with_nodes
    nodes = db.list_nodes()
    non_default = next(n for n in nodes if not n.is_default)

    app = _ManageTestApp(lambda: NodeManageScreen(db))
    async with app.run_test() as pilot:
        await pilot.click(f"#set_active_{non_default.id}")
        await pilot.pause()
        await pilot.click("#close_btn")
        await pilot.pause()

    assert app.dismiss_result is True
    assert db.get_default_node().id == non_default.id


# --- OperatorSetupScreen pre-population ---

@pytest.mark.asyncio
async def test_operator_setup_prepopulates_fields(db_with_operators):
    db = db_with_operators
    op = db.list_operators()[0]

    _SENTINEL2 = object()
    result_holder = [_SENTINEL2]

    class _EditApp(App):
        def on_mount(self):
            def capture(r):
                result_holder[0] = r
            self.push_screen(OperatorSetupScreen(op), callback=capture)

    app = _EditApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        callsign_val = app.screen.query_one("#callsign_field").value
        assert callsign_val == op.callsign
        await pilot.click("#cancel_btn")
        await pilot.pause()

    assert result_holder[0] is None


@pytest.mark.asyncio
async def test_operator_setup_edit_preserves_id(db_with_operators):
    db = db_with_operators
    op = db.list_operators()[0]

    result_holder = [None]

    class _EditApp(App):
        def on_mount(self):
            def capture(r):
                result_holder[0] = r
            self.push_screen(OperatorSetupScreen(op), callback=capture)

    app = _EditApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # Save without changing — id should be preserved in the returned object
        await pilot.click("#save_btn")
        await pilot.pause()

    assert result_holder[0] is not None
    assert result_holder[0].id == op.id
    assert result_holder[0].callsign == op.callsign


# --- NodeSetupScreen pre-population ---

@pytest.mark.asyncio
async def test_node_setup_prepopulates_fields(db_with_nodes):
    db = db_with_nodes
    node = db.list_nodes()[0]

    result_holder = [_SENTINEL]

    class _EditApp(App):
        def on_mount(self):
            def capture(r):
                result_holder[0] = r
            self.push_screen(NodeSetupScreen(node), callback=capture)

    app = _EditApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        callsign_val = app.screen.query_one("#callsign_field").value
        assert callsign_val == node.callsign
        await pilot.click("#cancel_btn")
        await pilot.pause()

    assert result_holder[0] is None
