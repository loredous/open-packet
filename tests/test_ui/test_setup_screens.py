import pytest
from textual.app import App
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


@pytest.mark.asyncio
async def test_node_setup_valid_input():
    app = _ScreenTestApp(NodeSetupScreen)
    async with app.run_test() as pilot:
        await pilot.click("#label_field")
        await pilot.press(*"Home BBS")
        await pilot.click("#callsign_field")
        await pilot.press(*"w0bpq")
        await pilot.click("#ssid_field")
        await pilot.press("1")
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
        await pilot.press(*"Home BBS")
        await pilot.click("#ssid_field")
        await pilot.press("0")
        await pilot.click("#save_btn")
        await pilot.pause()
    assert app.dismiss_result is _SENTINEL


@pytest.mark.asyncio
async def test_node_setup_invalid_ssid_does_not_dismiss():
    app = _ScreenTestApp(NodeSetupScreen)
    async with app.run_test() as pilot:
        await pilot.click("#label_field")
        await pilot.press(*"Home BBS")
        await pilot.click("#callsign_field")
        await pilot.press(*"W0BPQ")
        await pilot.click("#ssid_field")
        await pilot.press(*"abc")
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
