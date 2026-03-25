# open_packet/ui/tui/widgets/message_body.py
from __future__ import annotations
from textual.widgets import RichLog
from open_packet.store.models import Message, Bulletin


class MessageBody(RichLog):
    DEFAULT_CSS = """
    MessageBody {
        height: 1fr;
        border-top: solid $primary;
        padding: 0 1;
    }
    """

    def show_message(self, message: Message | Bulletin) -> None:
        self.clear()
        self.write(f"From:    {message.from_call}")
        if isinstance(message, Bulletin):
            self.write(f"Category: {message.category}")
        else:
            self.write(f"To:      {message.to_call}")
        self.write(f"Subject: {message.subject}")
        self.write("─" * 40)
        self.write(message.body)

    def clear_message(self) -> None:
        self.clear()
