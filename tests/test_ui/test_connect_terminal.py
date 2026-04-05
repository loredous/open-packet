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
