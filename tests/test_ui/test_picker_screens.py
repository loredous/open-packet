import pytest
from textual.app import App
from open_packet.store.database import Database
from open_packet.store.models import Operator, Node, Interface
from open_packet.ui.tui.screens.operator_picker import OperatorPickerScreen
from open_packet.ui.tui.screens.node_picker import NodePickerScreen
from open_packet.ui.tui.screens.interface_picker import InterfacePickerScreen

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


class _PickerTestApp(App):
    def __init__(self, screen_factory, **kwargs):
        super().__init__(**kwargs)
        self._factory = screen_factory
        self.dismiss_result = _SENTINEL

    def on_mount(self) -> None:
        self.push_screen(self._factory(), callback=lambda r: setattr(self, "dismiss_result", r))


@pytest.mark.asyncio
async def test_operator_picker_close_returns_false(db_with_operators):
    db = db_with_operators
    app = _PickerTestApp(lambda: OperatorPickerScreen(db))
    async with app.run_test() as pilot:
        await pilot.click("#close_btn")
        await pilot.pause()
    assert app.dismiss_result is False


@pytest.mark.asyncio
async def test_operator_picker_select_changes_default(db_with_operators):
    db = db_with_operators
    ops = db.list_operators()
    non_default = next(o for o in ops if not o.is_default)
    app = _PickerTestApp(lambda: OperatorPickerScreen(db))
    async with app.run_test() as pilot:
        await pilot.click(f"#select_{non_default.id}")
        await pilot.pause()
    assert app.dismiss_result is True
    assert db.get_default_operator().id == non_default.id


@pytest.mark.asyncio
async def test_node_picker_close_returns_false(db_with_nodes):
    db = db_with_nodes
    app = _PickerTestApp(lambda: NodePickerScreen(db))
    async with app.run_test() as pilot:
        await pilot.click("#close_btn")
        await pilot.pause()
    assert app.dismiss_result is False


@pytest.mark.asyncio
async def test_node_picker_select_changes_default(db_with_nodes):
    db = db_with_nodes
    nodes = db.list_nodes()
    non_default = next(n for n in nodes if not n.is_default)
    app = _PickerTestApp(lambda: NodePickerScreen(db))
    async with app.run_test() as pilot:
        await pilot.click(f"#select_{non_default.id}")
        await pilot.pause()
    assert app.dismiss_result is True
    assert db.get_default_node().id == non_default.id


@pytest.mark.asyncio
async def test_interface_picker_select_updates_node(db):
    iface1 = db.insert_interface(Interface(label="TNC1", iface_type="kiss_tcp", host="localhost", port=8910))
    iface2 = db.insert_interface(Interface(label="TNC2", iface_type="kiss_tcp", host="localhost", port=9000))
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
                               is_default=True, interface_id=iface1.id))
    app = _PickerTestApp(lambda: InterfacePickerScreen(db, node))
    async with app.run_test() as pilot:
        await pilot.click(f"#select_{iface2.id}")
        await pilot.pause()
    assert app.dismiss_result is True
    refreshed = db.get_node(node.id)
    assert refreshed.interface_id == iface2.id


@pytest.mark.asyncio
async def test_interface_picker_close_returns_false(db):
    iface = db.insert_interface(Interface(label="TNC", iface_type="kiss_tcp", host="localhost", port=8910))
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
                               is_default=True, interface_id=iface.id))
    app = _PickerTestApp(lambda: InterfacePickerScreen(db, node))
    async with app.run_test() as pilot:
        await pilot.click("#close_btn")
        await pilot.pause()
    assert app.dismiss_result is False
