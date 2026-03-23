import pytest
from textual.app import App
from open_packet.ui.tui.screens.settings import SettingsScreen


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
