# open_packet/ui/tui/widgets/message_body.py
from __future__ import annotations
from textual.binding import Binding
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

    BINDINGS = [Binding("w", "toggle_wrap", "Word wrap")]

    def __init__(self, **kwargs) -> None:
        super().__init__(wrap=True, **kwargs)

    def action_toggle_wrap(self) -> None:
        self.wrap = not self.wrap

    def show_message(self, message: Message | Bulletin, node_label: str = "") -> None:
        self.clear()
        self.write(f"From:    {message.from_call}")
        if isinstance(message, Bulletin):
            self.write(f"Category: {message.category}")
            if message.body is None:
                self.write("─" * 40)
                source = node_label or f"node #{message.node_id}"
                self.write(f"[dim]Not retrieved — source: {source}[/dim]")
                self.write("[dim]Press r to queue for next sync.[/dim]")
                return
        else:
            self.write(f"To:      {message.to_call}")
        self.write(f"Subject: {message.subject}")
        self.write("─" * 40)
        self.write(message.body)

    def clear_message(self) -> None:
        self.clear()
