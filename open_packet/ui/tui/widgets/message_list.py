# open_packet/ui/tui/widgets/message_list.py
from __future__ import annotations
from textual.widgets import DataTable
from textual.message import Message as TMessage
from open_packet.store.models import Message


class MessageList(DataTable):
    DEFAULT_CSS = """
    MessageList {
        height: 1fr;
    }
    """

    class MessageSelected(TMessage):
        def __init__(self, message: Message) -> None:
            self.message = message
            super().__init__()

    def on_mount(self) -> None:
        self.add_columns("  ", "Subject", "From", "Date")
        self.cursor_type = "row"

    def load_messages(self, messages: list[Message]) -> None:
        self.clear()
        self._messages = messages
        for msg in messages:
            read_marker = " " if msg.read else "●"
            date_str = msg.timestamp.strftime("%m/%d %H:%M") if msg.timestamp else ""
            self.add_row(read_marker, msg.subject[:40], msg.from_call, date_str)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if hasattr(self, "_messages") and event.cursor_row < len(self._messages):
            self.post_message(self.MessageSelected(self._messages[event.cursor_row]))
