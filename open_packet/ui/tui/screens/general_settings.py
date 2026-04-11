from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Input, Select, Switch
from textual.containers import Vertical, Horizontal
from open_packet.store.settings import Settings


class GeneralSettingsScreen(ModalScreen):
    DEFAULT_CSS = """
    GeneralSettingsScreen {
        align: center middle;
    }
    GeneralSettingsScreen > Vertical {
        width: 90%;
        height: auto;
        max-height: 90%;
        overflow-y: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    GeneralSettingsScreen .field-row {
        height: 3;
        margin-bottom: 1;
    }
    GeneralSettingsScreen .field-label {
        width: 20;
        content-align: left middle;
    }
    GeneralSettingsScreen .field-input {
        width: 1fr;
    }
    GeneralSettingsScreen .footer-row {
        height: 3;
        margin-top: 1;
        align: right middle;
    }
    GeneralSettingsScreen .footer-row Button {
        width: auto;
        min-width: 12;
        margin: 0 0 0 1;
    }
    """

    def __init__(self, settings: Settings, **kwargs):
        super().__init__(**kwargs)
        self._settings = settings

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("General Settings")
            with Horizontal(classes="field-row"):
                yield Label("Export Path", classes="field-label")
                yield Input(
                    value=self._settings.export_path,
                    id="export_path_field",
                    classes="field-input",
                )
            with Horizontal(classes="field-row"):
                yield Label("Console Buffer", classes="field-label")
                yield Input(
                    value=str(self._settings.console_buffer),
                    id="console_buffer_field",
                    classes="field-input",
                )
            with Horizontal(classes="field-row"):
                yield Label("Log Level", classes="field-label")
                yield Select(
                    options=[("Basic", "basic"), ("Debug", "debug")],
                    value=self._settings.console_log_level,
                    id="console_log_level_field",
                    classes="field-input",
                )
            with Horizontal(classes="field-row"):
                yield Label("Auto-Discover", classes="field-label")
                yield Switch(
                    value=self._settings.auto_discover,
                    id="auto_discover_field",
                )
            with Horizontal(classes="field-row"):
                yield Label("Scheduled S/R", classes="field-label")
                yield Switch(
                    value=self._settings.scheduled_sr_enabled,
                    id="scheduled_sr_enabled_field",
                )
            with Horizontal(classes="field-row"):
                yield Label("S/R Interval (min)", classes="field-label")
                yield Input(
                    value=str(self._settings.scheduled_sr_interval),
                    id="scheduled_sr_interval_field",
                    classes="field-input",
                )
            with Horizontal(classes="field-row"):
                yield Label("Notifications", classes="field-label")
                yield Switch(
                    value=self._settings.notifications_enabled,
                    id="notifications_enabled_field",
                )
            with Horizontal(classes="footer-row"):
                yield Button("Save", id="save_btn", variant="primary")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save_btn":
            self._save()
        else:
            self.dismiss(False)

    def _save(self) -> None:
        export_path = self.query_one("#export_path_field", Input).value.strip()
        console_buffer_raw = self.query_one("#console_buffer_field", Input).value.strip()
        auto_discover = self.query_one("#auto_discover_field", Switch).value
        scheduled_sr_enabled = self.query_one("#scheduled_sr_enabled_field", Switch).value
        scheduled_sr_interval_raw = self.query_one("#scheduled_sr_interval_field", Input).value.strip()
        notifications_enabled = self.query_one("#notifications_enabled_field", Switch).value

        try:
            console_buffer = int(console_buffer_raw)
        except ValueError:
            self.app.notify("Console buffer must be a number", severity="error")
            return

        scheduled_sr_interval = self._settings.scheduled_sr_interval
        if scheduled_sr_enabled:
            try:
                scheduled_sr_interval = int(scheduled_sr_interval_raw)
                if scheduled_sr_interval < 5:
                    raise ValueError
            except ValueError:
                self.app.notify("S/R interval must be a whole number >= 5 minutes", severity="error")
                return

        console_log_level = self.query_one("#console_log_level_field", Select).value
        old_auto_discover = self._settings.auto_discover
        self._settings.export_path = export_path
        self._settings.console_buffer = console_buffer
        self._settings.console_log_level = console_log_level
        self._settings.auto_discover = auto_discover
        self._settings.scheduled_sr_enabled = scheduled_sr_enabled
        self._settings.scheduled_sr_interval = scheduled_sr_interval
        self._settings.notifications_enabled = notifications_enabled

        needs_restart = auto_discover != old_auto_discover
        self.dismiss(needs_restart)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)
