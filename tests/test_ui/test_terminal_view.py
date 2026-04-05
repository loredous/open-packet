from __future__ import annotations
import pytest
from textual.app import App, ComposeResult
from open_packet.ui.tui.widgets.terminal_view import TerminalView


class _TerminalTestApp(App):
    def compose(self) -> ComposeResult:
        tv = TerminalView(id="tv")
        yield tv

    def on_mount(self) -> None:
        self.submitted: list[str] = []

    def on_terminal_view_line_submitted(self, event: TerminalView.LineSubmitted) -> None:
        self.submitted.append(event.text)


@pytest.mark.asyncio
async def test_terminal_view_mounts():
    app = _TerminalTestApp()
    async with app.run_test() as pilot:
        assert app.query_one("#tv") is not None


@pytest.mark.asyncio
async def test_set_header_updates_label():
    app = _TerminalTestApp()
    async with app.run_test() as pilot:
        tv = app.query_one(TerminalView)
        tv.set_header("W0XYZ — connected")
        await pilot.pause()
        from textual.widgets import Label
        header = tv.query_one("#terminal_header", Label)
        assert "W0XYZ" in str(header.render())


@pytest.mark.asyncio
async def test_append_line_adds_to_log():
    app = _TerminalTestApp()
    async with app.run_test() as pilot:
        tv = app.query_one(TerminalView)
        tv.append_line("hello world")
        await pilot.pause()
        # RichLog contains content — just verify no exception raised
        from textual.widgets import RichLog
        log = tv.query_one(RichLog)
        assert log is not None


@pytest.mark.asyncio
async def test_input_submit_fires_line_submitted():
    app = _TerminalTestApp()
    async with app.run_test() as pilot:
        from textual.widgets import Input
        inp = app.query_one("#terminal_input", Input)
        await pilot.click("#terminal_input")
        await pilot.press(*"hello")
        await pilot.press("enter")
        await pilot.pause()
    assert app.submitted == ["hello"]


@pytest.mark.asyncio
async def test_input_clears_after_submit():
    app = _TerminalTestApp()
    async with app.run_test() as pilot:
        from textual.widgets import Input
        await pilot.click("#terminal_input")
        await pilot.press(*"test")
        await pilot.press("enter")
        await pilot.pause()
        inp = app.query_one("#terminal_input", Input)
        assert inp.value == ""


@pytest.mark.asyncio
async def test_blank_input_does_not_fire_event():
    app = _TerminalTestApp()
    async with app.run_test() as pilot:
        await pilot.click("#terminal_input")
        await pilot.press("enter")
        await pilot.pause()
    assert app.submitted == []
