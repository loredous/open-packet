# tests/test_ui/test_upload_file.py
"""Tests for the UploadFileScreen modal and the FileList upload action."""
from __future__ import annotations
import pytest
from open_packet.ui.tui.screens.upload_file import UploadFileScreen
from open_packet.engine.commands import UploadFileCommand


@pytest.mark.asyncio
async def test_upload_screen_cancel_returns_none(tmp_path):
    """Pressing Cancel dismisses the screen with None."""
    dismissed = []

    from textual.app import App

    class TestApp(App):
        async def on_mount(self):
            await self.push_screen(
                UploadFileScreen(),
                callback=dismissed.append,
            )

    async with TestApp().run_test() as pilot:
        await pilot.click("#cancel_btn")
        await pilot.pause()

    assert dismissed == [None]


@pytest.mark.asyncio
async def test_upload_screen_validates_missing_path(tmp_path):
    """Clicking Upload with no path set shows an error label."""
    from textual.app import App
    from textual.widgets import Label

    class TestApp(App):
        async def on_mount(self):
            await self.push_screen(UploadFileScreen())

    async with TestApp().run_test() as pilot:
        # Click Upload without filling in any field
        await pilot.click("#upload_btn")
        await pilot.pause()

        screen = pilot.app.screen
        error_label = screen.query_one("#error_label", Label)
        assert error_label.has_class("visible")


@pytest.mark.asyncio
async def test_upload_screen_autofills_bbs_filename(tmp_path):
    """Setting local_path_field auto-fills the BBS filename with the basename."""
    from textual.app import App
    from textual.widgets import Input

    local_file = tmp_path / "myreport.txt"
    local_file.write_text("content")

    class TestApp(App):
        async def on_mount(self):
            await self.push_screen(UploadFileScreen())

    async with TestApp().run_test() as pilot:
        screen = pilot.app.screen
        local_input = screen.query_one("#local_path_field", Input)
        bbs_input = screen.query_one("#bbs_filename_field", Input)

        # Set the local path via the Input widget directly
        local_input.value = str(local_file)
        await pilot.pause()

        # BBS filename should be auto-filled with the basename
        assert bbs_input.value == "myreport.txt"


@pytest.mark.asyncio
async def test_upload_screen_submit_returns_command(tmp_path):
    """Filling in all fields and clicking Upload returns an UploadFileCommand."""
    from textual.app import App
    from textual.widgets import Input

    local_file = tmp_path / "notes.txt"
    local_file.write_text("Some notes")

    dismissed = []

    class TestApp(App):
        async def on_mount(self):
            await self.push_screen(
                UploadFileScreen(),
                callback=dismissed.append,
            )

    async with TestApp().run_test() as pilot:
        screen = pilot.app.screen

        local_input = screen.query_one("#local_path_field", Input)
        desc_input = screen.query_one("#description_field", Input)

        local_input.value = str(local_file)
        await pilot.pause()
        desc_input.value = "My notes file"
        await pilot.pause()

        await pilot.click("#upload_btn")
        await pilot.pause()

    assert len(dismissed) == 1
    result = dismissed[0]
    assert isinstance(result, UploadFileCommand)
    assert result.local_path == str(local_file)
    assert result.bbs_filename == "notes.txt"
    assert result.description == "My notes file"


@pytest.mark.asyncio
async def test_upload_screen_rejects_nonexistent_file(tmp_path):
    """Clicking Upload with a path that doesn't exist shows an error."""
    from textual.app import App
    from textual.widgets import Input, Label

    class TestApp(App):
        async def on_mount(self):
            await self.push_screen(UploadFileScreen())

    async with TestApp().run_test() as pilot:
        screen = pilot.app.screen

        local_input = screen.query_one("#local_path_field", Input)
        bbs_input = screen.query_one("#bbs_filename_field", Input)
        desc_input = screen.query_one("#description_field", Input)

        local_input.value = "/nonexistent/path/file.txt"
        bbs_input.value = "file.txt"
        desc_input.value = "Test desc"
        await pilot.pause()

        await pilot.click("#upload_btn")
        await pilot.pause()

        error_label = screen.query_one("#error_label", Label)
        assert error_label.has_class("visible")


@pytest.mark.asyncio
async def test_upload_screen_rejects_oversized_file(tmp_path):
    """Clicking Upload with a file exceeding MAX_FILE_SIZE shows an error."""
    from textual.app import App
    from textual.widgets import Input, Label
    from open_packet.node.bpq import MAX_FILE_SIZE

    big_file = tmp_path / "big.txt"
    big_file.write_text("x" * (MAX_FILE_SIZE + 1))

    class TestApp(App):
        async def on_mount(self):
            await self.push_screen(UploadFileScreen())

    async with TestApp().run_test() as pilot:
        screen = pilot.app.screen

        local_input = screen.query_one("#local_path_field", Input)
        desc_input = screen.query_one("#description_field", Input)

        local_input.value = str(big_file)
        await pilot.pause()
        desc_input.value = "Big file"
        await pilot.pause()

        await pilot.click("#upload_btn")
        await pilot.pause()

        error_label = screen.query_one("#error_label", Label)
        assert error_label.has_class("visible")
