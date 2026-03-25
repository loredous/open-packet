# tests/test_ui/test_status_bar.py
from textual.app import App, ComposeResult
from open_packet.ui.tui.widgets.status_bar import StatusBar
from open_packet.engine.events import ConnectionStatus
from tests.test_ui.conftest import _label_text


class StatusBarApp(App):
    def compose(self) -> ComposeResult:
        yield StatusBar(id="status_bar")


async def test_left_label_shows_emoji_and_app_name():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        left = app.query_one("#status_left")
        assert "📻 open-packet" in _label_text(left)


async def test_left_label_shows_disconnected_icon_by_default():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        left = app.query_one("#status_left")
        assert "○" in _label_text(left)  # DISCONNECTED icon


async def test_left_label_updates_on_status_change():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.status = ConnectionStatus.CONNECTED
        await pilot.pause()
        left = app.query_one("#status_left")
        text = _label_text(left)
        assert "●" in text
        assert "Connected" in text


async def test_left_label_updates_on_last_sync_change():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.last_sync = "13:45"
        await pilot.pause()
        left = app.query_one("#status_left")
        assert "13:45" in _label_text(left)


async def test_right_label_empty_by_default():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        right = app.query_one("#status_right")
        assert _label_text(right) == ""


async def test_right_label_shows_operator_with_separator():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.operator = "W1AW"
        await pilot.pause()
        text = _label_text(app.query_one("#status_right"))
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
        text = _label_text(app.query_one("#status_right"))
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
        assert _label_text(app.query_one("#status_right")) == ""


async def test_left_label_does_not_contain_triple_dash():
    """The old callsign placeholder '---' must not appear in the new implementation."""
    app = StatusBarApp()
    async with app.run_test() as pilot:
        left = app.query_one("#status_left")
        assert "---" not in _label_text(left)
