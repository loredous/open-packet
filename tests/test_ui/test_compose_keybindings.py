"""Keyboard submit (Ctrl+S) and cancel (Escape) on the compose and form-fill screens."""
from textual.app import App
from textual.widgets import Input, Label, TextArea

from open_packet.engine.commands import PostBulletinCommand, SendMessageCommand
from open_packet.forms.loader import FormDefinition, FormField
from open_packet.ui.tui.screens.compose import ComposeScreen
from open_packet.ui.tui.screens.compose_bulletin import ComposeBulletinScreen
from open_packet.ui.tui.screens.form_fill import FormFillScreen

_NO_RESULT = object()


class _Host(App):
    """Pushes a single modal screen and records what it dismisses with."""

    def __init__(self, screen):
        super().__init__()
        self._modal = screen
        self.result = _NO_RESULT

    def on_mount(self) -> None:
        self.push_screen(self._modal, callback=self._record)

    def _record(self, result) -> None:
        self.result = result


# --- ComposeScreen ---------------------------------------------------------

async def test_compose_ctrl_s_from_body_sends_message():
    app = _Host(ComposeScreen(to_call="W0AA", subject="Hello", body="Hi there"))
    async with app.run_test() as pilot:
        app.screen.query_one("#body_field", TextArea).focus()
        await pilot.press("ctrl+s")
        await pilot.pause()
    assert app.result == SendMessageCommand(to_call="W0AA", subject="Hello", body="Hi there")


async def test_compose_ctrl_s_without_recipient_stays_open():
    app = _Host(ComposeScreen(subject="Hello"))
    async with app.run_test() as pilot:
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, ComposeScreen)
    assert app.result is _NO_RESULT


async def test_compose_escape_from_body_cancels():
    app = _Host(ComposeScreen(to_call="W0AA", subject="Hello"))
    async with app.run_test() as pilot:
        app.screen.query_one("#body_field", TextArea).focus()
        await pilot.press("escape")
        await pilot.pause()
    assert app.result is None


# --- ComposeBulletinScreen -------------------------------------------------

async def test_bulletin_ctrl_s_posts_bulletin():
    app = _Host(ComposeBulletinScreen())
    async with app.run_test() as pilot:
        screen = app.screen
        screen.query_one("#category_field", Input).value = "WX"
        screen.query_one("#subject_field", Input).value = "Storm"
        screen.query_one("#body_field", TextArea).load_text("Heavy rain")
        screen.query_one("#body_field", TextArea).focus()
        await pilot.press("ctrl+s")
        await pilot.pause()
    assert app.result == PostBulletinCommand(category="WX", subject="Storm", body="Heavy rain")


async def test_bulletin_ctrl_s_without_category_shows_error():
    app = _Host(ComposeBulletinScreen())
    async with app.run_test() as pilot:
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, ComposeBulletinScreen)
        assert "required" in str(app.screen.query_one("#category_error", Label).render())
    assert app.result is _NO_RESULT


async def test_bulletin_escape_cancels():
    app = _Host(ComposeBulletinScreen())
    async with app.run_test() as pilot:
        app.screen.query_one("#body_field", TextArea).focus()
        await pilot.press("escape")
        await pilot.pause()
    assert app.result is None


# --- FormFillScreen --------------------------------------------------------

def _form() -> FormDefinition:
    return FormDefinition(
        name="Test Form",
        category="Test",
        fields=[
            FormField(name="who", label="Who", required=True),
            FormField(name="notes", label="Notes", type="textarea"),
        ],
        subject_template="Report from {{ who }}",
        body_template="{{ notes }}",
    )


async def test_form_fill_ctrl_s_submits_valid_form():
    app = _Host(FormFillScreen(_form(), initial_values={"who": "W0AA", "notes": "All quiet"}))
    async with app.run_test() as pilot:
        app.screen.query_one("#field_notes", TextArea).focus()
        await pilot.press("ctrl+s")
        await pilot.pause()
    assert app.result == ("Report from W0AA", "All quiet")


async def test_form_fill_ctrl_s_with_invalid_form_stays_open():
    app = _Host(FormFillScreen(_form()))
    async with app.run_test() as pilot:
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, FormFillScreen)
    assert app.result is _NO_RESULT
