# open_packet/ui/tui/widgets/message_list.py
from __future__ import annotations
from textual.coordinate import Coordinate
from textual.widgets import DataTable
from textual.message import Message as TMessage
from open_packet.store.models import Message, Bulletin


class MessageList(DataTable):
    DEFAULT_CSS = """
    MessageList {
        height: 1fr;
    }
    """

    class MessageSelected(TMessage):
        def __init__(self, message: Message | Bulletin, row_index: int) -> None:
            self.message = message
            self.row_index = row_index
            super().__init__()

    def on_mount(self) -> None:
        self.add_columns("  ", "Subject", "From", "Sent", "Retrieved")
        self.cursor_type = "row"
        self._loading = False

    def load_messages(self, messages: list[Message | Bulletin]) -> None:
        self._loading = True
        self.clear()
        self._messages = messages
        for msg in messages:
            read_marker = " " if msg.read else "●"
            sent_str = msg.timestamp.strftime("%m/%d %H:%M") if msg.timestamp else "—"
            retrieved_str = msg.synced_at.strftime("%m/%d %H:%M") if msg.synced_at else "—"
            self.add_row(read_marker, msg.subject[:40], msg.from_call, sent_str, retrieved_str)
        self.call_after_refresh(self._finish_loading)

    def _finish_loading(self) -> None:
        self._loading = False

    def mark_row_read(self, row_index: int) -> None:
        self.update_cell_at(Coordinate(row_index, 0), " ")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if getattr(self, "_loading", False):
            return
        if hasattr(self, "_messages") and event.cursor_row < len(self._messages):
            self.post_message(self.MessageSelected(self._messages[event.cursor_row], event.cursor_row))
