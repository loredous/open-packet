# open_packet/ui/tui/widgets/file_list.py
from __future__ import annotations
from textual.app import ComposeResult
from textual.message import Message as TMessage
from textual.widgets import DataTable
from textual.containers import Vertical
from open_packet.store.models import BBSFile


class FileList(Vertical):
    DEFAULT_CSS = """
    FileList {
        width: 1fr;
        height: 1fr;
    }
    FileList DataTable {
        width: 1fr;
        height: 1fr;
    }
    """

    class RetrievalToggled(TMessage):
        def __init__(self, file: BBSFile) -> None:
            self.file = file
            super().__init__()

    class UploadRequested(TMessage):
        """Fired when the user presses 'u' to upload a file."""

    def compose(self) -> ComposeResult:
        yield DataTable(id="file_table", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one("#file_table", DataTable)
        table.add_columns("Status", "Filename", "Size", "Date", "Description")
        self._files: list[BBSFile] = []

    def load_files(self, files: list[BBSFile]) -> None:
        self._files = files
        table = self.query_one("#file_table", DataTable)
        table.clear()
        for f in files:
            if f.content == "\x01":
                status = "[✓]"
            elif f.wants_retrieval:
                status = "[Q]"
            else:
                status = ""
            size_str = str(f.size) if f.size is not None else ""
            table.add_row(status, f.filename, size_str, f.date_str, f.description)

    def action_toggle_retrieval(self) -> None:
        table = self.query_one("#file_table", DataTable)
        if table.cursor_row < 0 or table.cursor_row >= len(self._files):
            return
        f = self._files[table.cursor_row]
        if f.id is None or f.content == "\x01":
            return  # already retrieved, nothing to do
        self.post_message(self.RetrievalToggled(f))

    def action_upload_file(self) -> None:
        self.post_message(self.UploadRequested())

    def on_key(self, event) -> None:
        if event.key == "r":
            self.action_toggle_retrieval()
            event.stop()
        elif event.key == "u":
            self.action_upload_file()
            event.stop()
