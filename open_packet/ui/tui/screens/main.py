# open_packet/ui/tui/screens/main.py
from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Horizontal, Vertical
from open_packet.ui.tui.widgets.status_bar import StatusBar
from open_packet.ui.tui.widgets.folder_tree import FolderTree
from open_packet.ui.tui.widgets.message_list import MessageList
from open_packet.ui.tui.widgets.message_body import MessageBody
from open_packet.ui.tui.widgets.console_panel import ConsolePanel


class MainScreen(Screen):
    DEFAULT_CSS = """
    MainScreen {
        layout: vertical;
    }
    #main_area {
        height: 1fr;
    }
    #right_pane {
        layout: vertical;
        width: 1fr;
    }
    """

    BINDINGS = [
        ("c", "check_mail", "Check Mail"),
        ("n", "new_message", "New"),
        ("d", "delete_message", "Delete"),
        ("r", "reply_message", "Reply"),
        ("s", "settings", "Settings"),
        ("`", "toggle_console", "Console"),
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield StatusBar(id="status_bar")
        with Horizontal(id="main_area"):
            yield FolderTree("Folders", id="folder_tree")
            with Vertical(id="right_pane"):
                yield MessageList(id="message_list")
                yield MessageBody(id="message_body")
        yield ConsolePanel(id="console_panel")

    def on_mount(self) -> None:
        self.query_one("ConsolePanel").display = self.app.config.ui.console_visible

    def action_toggle_console(self) -> None:
        panel = self.query_one("ConsolePanel")
        panel.display = not panel.display

    def action_check_mail(self) -> None:
        self.app.check_mail()

    def action_new_message(self) -> None:
        self.app.open_compose()

    def action_delete_message(self) -> None:
        self.app.delete_selected_message()

    def action_reply_message(self) -> None:
        self.app.reply_to_selected()

    def action_settings(self) -> None:
        self.app.open_settings()

    def action_quit(self) -> None:
        self.app.exit()
