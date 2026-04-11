from textual.app import App, ComposeResult
from textual.widgets import Label
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
        assert "○" in _label_text(left)


async def test_left_label_updates_on_status_change():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.status = ConnectionStatus.CONNECTED
        await pilot.pause()
        text = _label_text(app.query_one("#status_left"))
        assert "●" in text
        assert "Connected" in text


async def test_left_label_updates_on_last_sync_change():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.last_sync = "13:45"
        await pilot.pause()
        assert "13:45" in _label_text(app.query_one("#status_left"))


async def test_identity_hidden_when_all_fields_empty():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        assert not app.query_one("#identity_container").display


async def test_identity_shows_operator_button():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.operator = "W1AW"
        await pilot.pause()
        assert app.query_one("#identity_container").display
        assert _label_text(app.query_one("#identity_operator", Label)) == "W1AW"


async def test_identity_hides_node_sep_when_node_empty():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.operator = "W1AW"
        await pilot.pause()
        assert not app.query_one("#identity_sep_node").display


async def test_identity_shows_all_three_labels():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.operator = "W1AW"
        sb.node = "Home BBS"
        sb.interface_label = "Home TNC"
        await pilot.pause()
        assert app.query_one("#identity_container").display
        assert app.query_one("#identity_sep_node").display
        assert app.query_one("#identity_sep_iface").display


async def test_identity_cleared_when_all_empty():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.operator = "W1AW"
        await pilot.pause()
        sb.operator = ""
        await pilot.pause()
        assert not app.query_one("#identity_container").display


async def test_identity_clicked_message_posted_on_operator_click():
    messages = []

    class _App(App):
        def compose(self) -> ComposeResult:
            yield StatusBar()

        def on_status_bar_identity_clicked(self, event: StatusBar.IdentityClicked) -> None:
            messages.append(event.kind)

    app = _App()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.operator = "W1AW"
        await pilot.pause()
        await pilot.click("#identity_operator")
        await pilot.pause()
    assert messages == ["operator"]


async def test_left_label_does_not_contain_triple_dash():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        left = app.query_one("#status_left")
        assert "---" not in _label_text(left)


async def test_left_label_shows_last_frame_never_by_default():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        left = app.query_one("#status_left")
        assert "Last frame: Never" in _label_text(left)


async def test_left_label_updates_on_last_frame_change():
    app = StatusBarApp()
    async with app.run_test() as pilot:
        sb = app.query_one(StatusBar)
        sb.last_frame = "12:34:56"
        await pilot.pause()
        assert "Last frame: 12:34:56" in _label_text(app.query_one("#status_left"))


async def test_frame_received_event_handling_updates_last_frame():
    """Polling a FrameReceivedEvent and updating last_frame should change the status bar text."""
    import queue
    from datetime import timezone
    from open_packet.engine.events import FrameReceivedEvent

    class _App(App):
        def compose(self) -> ComposeResult:
            yield StatusBar()

        def on_mount(self) -> None:
            self._evt_queue: queue.Queue = queue.Queue()
            self._evt_queue.put(FrameReceivedEvent())
            self.set_interval(0.05, self._poll)

        def _poll(self) -> None:
            while not self._evt_queue.empty():
                event = self._evt_queue.get_nowait()
                if isinstance(event, FrameReceivedEvent):
                    self.query_one(StatusBar).last_frame = event.timestamp.astimezone().strftime("%H:%M:%S")

    app = _App()
    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        text = _label_text(app.query_one("#status_left"))
        assert "Last frame: Never" not in text
        assert "Last frame:" in text
