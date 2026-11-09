# open_packet/ui/tui/screens/search.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label

from open_packet.store.models import Bulletin, Message
from open_packet.store.store import Store


def _folder_for_message(msg: Message) -> str:
    if msg.archived:
        return "Archive"
    if msg.queued and not msg.sent:
        return "Outbox"
    if msg.sent:
        return "Sent"
    return "Inbox"


class SearchScreen(ModalScreen[Optional[Message | Bulletin]]):
    """Modal search screen: search messages and bulletins by keyword."""

    DEFAULT_CSS = """
    SearchScreen {
        align: center middle;
    }
    #search_dialog {
        width: 90;
        height: 30;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    #search_title {
        text-align: center;
        margin-bottom: 1;
    }
    #search_row {
        height: 3;
        margin-bottom: 1;
    }
    #search_input {
        width: 1fr;
    }
    #search_btn {
        width: 12;
        margin-left: 1;
    }
    #results_label {
        margin-bottom: 1;
    }
    #results_table {
        height: 1fr;
        border: solid $primary-darken-2;
    }
    #footer_row {
        height: 3;
        align: right middle;
        margin-top: 1;
    }
    #close_btn {
        width: 12;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("enter", "search", "Search"),
    ]

    def __init__(self, store: Store, operator_id: int, **kwargs) -> None:
        super().__init__(**kwargs)
        self._store = store
        self._operator_id = operator_id
        self._results: list[tuple[str, Message | Bulletin]] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="search_dialog"):
            yield Label("Search Messages & Bulletins", id="search_title")
            with Horizontal(id="search_row"):
                yield Input(placeholder="callsign, subject, keyword…", id="search_input")
                yield Button("Search", id="search_btn", variant="primary")
            yield Label("Results will appear here. Press Enter or click Search.", id="results_label")
            yield DataTable(id="results_table")
            with Horizontal(id="footer_row"):
                yield Button("Close", id="close_btn", variant="default")

    def on_mount(self) -> None:
        table = self.query_one("#results_table", DataTable)
        table.add_columns("  ", "Folder/Category", "Subject", "From", "Date")
        table.cursor_type = "row"
        self.query_one("#search_input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "search_btn":
            self._do_search()
        elif event.button.id == "close_btn":
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._do_search()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.cursor_row < len(self._results):
            _, item = self._results[event.cursor_row]
            self.dismiss(item)

    def _do_search(self) -> None:
        query = self.query_one("#search_input", Input).value.strip()
        if not query:
            return

        messages = self._store.search_messages(self._operator_id, query)
        bulletins = self._store.search_bulletins(self._operator_id, query)

        self._results = []
        for msg in messages:
            self._results.append((_folder_for_message(msg), msg))
        for bul in bulletins:
            self._results.append((f"Bulletins/{bul.category}", bul))

        self._results.sort(key=lambda x: x[1].timestamp, reverse=True)

        table = self.query_one("#results_table", DataTable)
        table.clear()
        for folder, item in self._results:
            read_marker = " " if item.read else "●"
            date_str = item.timestamp.strftime("%m/%d %H:%M") if item.timestamp else "—"
            subject = item.subject[:35] if item.subject else "—"
            table.add_row(read_marker, folder, subject, item.from_call, date_str)

        count = len(self._results)
        self.query_one("#results_label", Label).update(
            f"{count} result(s) for '{query}'. Press Enter or double-click to open."
            if count else f"No results found for '{query}'."
        )

    def action_search(self) -> None:
        self._do_search()

    def action_close(self) -> None:
        self.dismiss(None)
