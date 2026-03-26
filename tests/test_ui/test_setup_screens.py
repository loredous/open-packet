import pytest
from textual.app import App
from open_packet.ui.tui.screens.settings import SettingsScreen
from open_packet.ui.tui.screens.setup_operator import OperatorSetupScreen
from open_packet.ui.tui.screens.setup_node import NodeSetupScreen, _hops_to_text, _text_to_hops
from open_packet.ui.tui.screens.setup_interface import InterfaceSetupScreen
from open_packet.ui.tui.app import OpenPacketApp
from open_packet.config.config import AppConfig, StoreConfig, UIConfig
from open_packet.store.database import Database
from open_packet.store.models import Operator, Node, Interface, NodeHop


def test_hops_to_text_empty():
    assert _hops_to_text([]) == ""

def test_hops_to_text_with_port():
    assert _hops_to_text([NodeHop("W0RELAY", port=3)]) == "W0RELAY:3"

def test_hops_to_text_no_port():
    assert _hops_to_text([NodeHop("W0RELAY")]) == "W0RELAY"

def test_hops_to_text_multiple():
    result = _hops_to_text([NodeHop("W0R1", port=1), NodeHop("W0R2")])
    assert result == "W0R1:1\nW0R2"

def test_text_to_hops_empty():
    assert _text_to_hops("") == []

def test_text_to_hops_with_port():
    hops = _text_to_hops("W0RELAY:3")
    assert hops[0].callsign == "W0RELAY"
    assert hops[0].port == 3

def test_text_to_hops_no_port():
    hops = _text_to_hops("W0RELAY")
    assert hops[0].callsign == "W0RELAY"
    assert hops[0].port is None

def test_text_to_hops_invalid_port_falls_back():
    hops = _text_to_hops("W0RELAY:notanint")
    assert hops[0].callsign == "W0RELAY:notanint"
    assert hops[0].port is None


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


@pytest.mark.asyncio
async def test_operator_setup_valid_input():
    app = _ScreenTestApp(OperatorSetupScreen)
    async with app.run_test() as pilot:
        await pilot.click("#callsign_field")
        await pilot.press(*"kd9abc")
        await pilot.click("#ssid_field")
        await pilot.press("1")
        await pilot.click("#label_field")
        await pilot.press(*"home")
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
async def test_operator_setup_empty_ssid_defaults_to_zero():
    app = _ScreenTestApp(OperatorSetupScreen)
    async with app.run_test() as pilot:
        await pilot.click("#callsign_field")
        await pilot.press(*"kd9abc")
        # leave ssid_field blank
        await pilot.click("#label_field")
        await pilot.press(*"home")
        await pilot.click("#save_btn")
        await pilot.pause()
    result = app.dismiss_result
    assert result is not _SENTINEL
    assert result is not None
    assert result.ssid == 0


@pytest.mark.asyncio
async def test_operator_setup_blank_callsign_does_not_dismiss():
    app = _ScreenTestApp(OperatorSetupScreen)
    async with app.run_test() as pilot:
        await pilot.click("#ssid_field")
        await pilot.press("1")
        await pilot.click("#label_field")
        await pilot.press(*"home")
        await pilot.click("#save_btn")
        await pilot.pause()
    assert app.dismiss_result is _SENTINEL  # never dismissed


@pytest.mark.asyncio
async def test_operator_setup_invalid_ssid_does_not_dismiss():
    app = _ScreenTestApp(OperatorSetupScreen)
    async with app.run_test() as pilot:
        await pilot.click("#callsign_field")
        await pilot.press(*"KD9ABC")
        await pilot.click("#ssid_field")
        await pilot.press(*"99")
        await pilot.click("#label_field")
        await pilot.press(*"home")
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


@pytest.fixture
def node_db(tmp_path):
    db = Database(str(tmp_path / "node_test.db"))
    db.initialize()
    yield db
    db.close()


@pytest.mark.asyncio
async def test_node_setup_telnet_creates_interface(node_db):
    """Saving a Telnet node creates an Interface record and links the Node to it."""
    app = _ScreenTestApp(lambda: NodeSetupScreen(interfaces=[], db=node_db))
    async with app.run_test(size=(80, 120)) as pilot:
        await pilot.click("#label_field")
        await pilot.press(*"Home BBS")
        await pilot.click("#callsign_field")
        await pilot.press(*"w0bpq")
        await pilot.click("#ssid_field")
        await pilot.press("1")
        # conn_type defaults to "telnet", iface_selector defaults to "New"
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
    assert result.label == "Home BBS"
    assert result.callsign == "W0BPQ"
    assert result.ssid == 1
    assert result.interface_id is not None

    iface = node_db.get_interface(result.interface_id)
    assert iface.iface_type == "telnet"
    assert iface.host == "192.168.1.209"
    assert iface.port == 8023
    assert iface.username == "K0JLB"
    assert iface.password == "password"


@pytest.mark.asyncio
async def test_node_setup_reuses_existing_interface(node_db):
    """When an existing interface is selected, no new Interface record is created."""
    existing = node_db.insert_interface(Interface(
        label="Home TNC", iface_type="telnet",
        host="10.0.0.1", port=8023, username="K0JLB", password="pw"
    ))
    before_count = len(node_db.list_interfaces())

    app = _ScreenTestApp(lambda: NodeSetupScreen(
        interfaces=node_db.list_interfaces(), db=node_db
    ))
    async with app.run_test(size=(80, 120)) as pilot:
        await pilot.click("#label_field")
        await pilot.press(*"Remote BBS")
        await pilot.click("#callsign_field")
        await pilot.press(*"W0BPQ")
        await pilot.click("#ssid_field")
        await pilot.press("0")
        # interface selector should have the existing interface; select it
        iface_sel = pilot.app.screen.query_one("#iface_selector")
        iface_sel.value = existing.id
        await pilot.pause()
        await pilot.click("#save_btn")
        await pilot.pause()

    result = app.dismiss_result
    assert result is not _SENTINEL
    assert result is not None
    assert result.interface_id == existing.id
    assert len(node_db.list_interfaces()) == before_count  # no new interface created


@pytest.mark.asyncio
async def test_node_setup_blank_host_does_not_dismiss(node_db):
    """Telnet with blank host should not dismiss."""
    app = _ScreenTestApp(lambda: NodeSetupScreen(interfaces=[], db=node_db))
    async with app.run_test(size=(80, 120)) as pilot:
        await pilot.click("#label_field")
        await pilot.press(*"BBS")
        await pilot.click("#callsign_field")
        await pilot.press(*"W0BPQ")
        await pilot.click("#ssid_field")
        await pilot.press("0")
        # Leave host blank, fill rest
        await pilot.click("#telnet_port")
        await pilot.press(*"8023")
        await pilot.click("#telnet_user")
        await pilot.press(*"K0JLB")
        await pilot.click("#telnet_pass")
        await pilot.press(*"pw")
        await pilot.click("#save_btn")
        await pilot.pause()
    assert app.dismiss_result is _SENTINEL


@pytest.mark.asyncio
async def test_node_setup_cancel(node_db):
    app = _ScreenTestApp(lambda: NodeSetupScreen(interfaces=[], db=node_db))
    async with app.run_test(size=(80, 120)) as pilot:
        await pilot.click("#cancel_btn")
        await pilot.pause()
    assert app.dismiss_result is None


@pytest.mark.asyncio
async def test_interface_setup_telnet_valid():
    app = _ScreenTestApp(InterfaceSetupScreen)
    async with app.run_test(size=(80, 80)) as pilot:
        # Default type is telnet
        await pilot.click("#iface_label_field")
        await pilot.press(*"Home BBS")
        await pilot.click("#host_field")
        await pilot.press(*"192.168.1.209")
        await pilot.click("#port_field")
        await pilot.press(*"8023")
        await pilot.click("#username_field")
        await pilot.press(*"K0JLB")
        await pilot.click("#password_field")
        await pilot.press(*"secret")
        await pilot.click("#save_btn")
        await pilot.pause()
    result = app.dismiss_result
    assert result is not _SENTINEL
    assert result is not None
    assert result.label == "Home BBS"
    assert result.iface_type == "telnet"
    assert result.host == "192.168.1.209"
    assert result.port == 8023
    assert result.username == "K0JLB"
    assert result.password == "secret"


@pytest.mark.asyncio
async def test_interface_setup_blank_host_does_not_dismiss():
    app = _ScreenTestApp(InterfaceSetupScreen)
    async with app.run_test(size=(80, 80)) as pilot:
        await pilot.click("#iface_label_field")
        await pilot.press(*"Bad")
        # leave host blank
        await pilot.click("#port_field")
        await pilot.press(*"8023")
        await pilot.click("#username_field")
        await pilot.press(*"user")
        await pilot.click("#password_field")
        await pilot.press(*"pw")
        await pilot.click("#save_btn")
        await pilot.pause()
    assert app.dismiss_result is _SENTINEL


@pytest.mark.asyncio
async def test_interface_setup_cancel():
    app = _ScreenTestApp(InterfaceSetupScreen)
    async with app.run_test() as pilot:
        await pilot.click("#cancel_btn")
        await pilot.pause()
    assert app.dismiss_result is None


@pytest.mark.asyncio
async def test_settings_interfaces_button():
    app = _ScreenTestApp(SettingsScreen)
    async with app.run_test() as pilot:
        await pilot.click("#interfaces_btn")
        await pilot.pause()
    assert app.dismiss_result == "interfaces"


from open_packet.ui.tui.screens.manage_interfaces import InterfaceManageScreen


class _ManageTestApp(App):
    """Wrapper app that opens InterfaceManageScreen with a real DB."""
    def __init__(self, db, **kwargs):
        super().__init__(**kwargs)
        self._db = db
        self.dismiss_result = _SENTINEL

    def on_mount(self):
        def capture(result):
            self.dismiss_result = result
        self.push_screen(InterfaceManageScreen(self._db), callback=capture)


@pytest.mark.asyncio
async def test_interface_manage_shows_existing(node_db):
    node_db.insert_interface(Interface(label="My TNC", iface_type="kiss_tcp",
                                       host="localhost", port=8910))
    app = _ManageTestApp(node_db)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.query("Label")  # screen mounted
        await pilot.click("#close_btn")
        await pilot.pause()
    assert app.dismiss_result is False


@pytest.mark.asyncio
async def test_interface_manage_close_returns_false(node_db):
    app = _ManageTestApp(node_db)
    async with app.run_test() as pilot:
        await pilot.click("#close_btn")
        await pilot.pause()
    assert app.dismiss_result is False


@pytest.fixture
def base_config(tmp_path):
    return AppConfig(
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
    async with app.run_test(size=(80, 120)) as pilot:
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, OperatorSetupScreen)
        # Fill and save operator
        await pilot.click("#callsign_field")
        await pilot.press(*"KD9ABC")
        await pilot.click("#ssid_field")
        await pilot.press(*"1")
        await pilot.click("#label_field")
        await pilot.press(*"home")
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
    async with app.run_test(size=(80, 120)) as pilot:
        await pilot.pause()
        await pilot.pause()
        # Fill operator
        await pilot.click("#callsign_field")
        await pilot.press(*"KD9ABC")
        await pilot.click("#ssid_field")
        await pilot.press(*"1")
        await pilot.click("#label_field")
        await pilot.press(*"home")
        await pilot.click("#save_btn")
        await pilot.pause()
        # Fill node
        await pilot.click("#label_field")
        await pilot.press(*"HomeBBS")
        await pilot.click("#callsign_field")
        await pilot.press(*"W0BPQ")
        await pilot.click("#ssid_field")
        await pilot.press(*"1")
        # Telnet fields (default connection type)
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
        await pilot.pause()
    assert app._engine is not None
    app._engine.stop()
