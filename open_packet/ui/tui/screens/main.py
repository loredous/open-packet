# open_packet/ui/tui/screens/main.py
from __future__ import annotations
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer
from open_packet.ui.tui.widgets.status_bar import StatusBar
from open_packet.ui.tui.widgets.folder_tree import FolderTree
from open_packet.ui.tui.widgets.message_list import MessageList
from open_packet.ui.tui.widgets.message_body import MessageBody
from open_packet.ui.tui.widgets.console_panel import ConsolePanel
from open_packet.ui.tui.widgets.terminal_view import TerminalView
from open_packet.ui.tui.widgets.file_list import FileList


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
        Binding("ctrl+a", "archive_message", "Archive", priority=True),
        Binding("`", "toggle_console", "Console", priority=True),
        Binding("ctrl+x", "delete_message", "Delete", priority=True),
        Binding("ctrl+d", "disconnect_session", "Disconnect", priority=True),
        Binding("ctrl+n", "new_item", "New...", priority=True),
        Binding("ctrl+u", "queue_bulletin_retrieval", "Queue Retrieval", priority=True),
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("ctrl+r", "reply_message", "Reply", priority=True),
        Binding("ctrl+c", "check_mail", "Send/Receive", priority=True),
        Binding("ctrl+s", "settings", "Settings", priority=True),
        Binding("ctrl+t", "terminal_connect", "Terminal", priority=True),
    ]

    def compose(self) -> ComposeResult:
        yield StatusBar(id="status_bar")
        with Horizontal(id="main_area"):
            yield FolderTree("Folders", id="folder_tree")
            with Vertical(id="right_pane"):
                yield MessageList(id="message_list")
                yield MessageBody(id="message_body")
                yield FileList(id="file_list")
                yield TerminalView(id="terminal_view")
        yield ConsolePanel(id="console_panel")
        yield Footer()

    def on_mount(self) -> None:
        settings = getattr(self.app, "_settings", None)
        self.query_one("ConsolePanel").display = settings.console_visible if settings else False
        self.query_one(TerminalView).display = False
        self.query_one(FileList).display = False

    def show_terminal(self) -> None:
        self.query_one(TerminalView).display = True
        self.query_one(MessageList).display = False
        self.query_one(MessageBody).display = False
        self.query_one(FileList).display = False

    def show_messages(self) -> None:
        self.query_one(TerminalView).display = False
        self.query_one(MessageList).display = True
        self.query_one(MessageBody).display = True
        self.query_one(FileList).display = False

    def show_files(self) -> None:
        self.query_one(TerminalView).display = False
        self.query_one(MessageList).display = False
        self.query_one(MessageBody).display = False
        self.query_one(FileList).display = True

    def action_toggle_console(self) -> None:
        panel = self.query_one("ConsolePanel")
        panel.display = not panel.display

    def action_check_mail(self) -> None:
        self.app.check_mail()

    def action_new_item(self) -> None:
        self.app.open_new_item()

    def action_terminal_connect(self) -> None:
        self.app.open_terminal_connect()

    def action_delete_message(self) -> None:
        self.app.delete_selected_message()

    def action_archive_message(self) -> None:
        self.app.archive_selected_message()

    def action_reply_message(self) -> None:
        self.app.reply_to_selected()

    def action_settings(self) -> None:
        self.app.open_settings()

    def action_disconnect_session(self) -> None:
        self.app.disconnect_session()

    def action_queue_bulletin_retrieval(self) -> None:
        self.app.queue_bulletin_retrieval()

    def action_quit(self) -> None:
        self.app.exit()

