# open_packet/ui/tui/screens/upload_file.py
from __future__ import annotations
from pathlib import Path
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label
from textual.containers import Vertical, Horizontal
from open_packet.engine.commands import UploadFileCommand


class UploadFileScreen(ModalScreen):
    """Modal dialog for uploading a local file to the BBS."""

    DEFAULT_CSS = """
    UploadFileScreen {
        align: center middle;
    }
    UploadFileScreen Vertical {
        width: 80%;
        height: auto;
        max-height: 90%;
        overflow-y: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    UploadFileScreen #error_label {
        color: $error;
        display: none;
    }
    UploadFileScreen #error_label.visible {
        display: block;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Upload File to BBS", id="upload_title")
            yield Label("Local file path:")
            yield Input(placeholder="/path/to/file", id="local_path_field")
            yield Label("BBS filename (as it will appear on the BBS):")
            yield Input(placeholder="filename.txt", id="bbs_filename_field")
            yield Label("Description (one line, shown in DIR listing):")
            yield Input(placeholder="Short description", id="description_field")
            yield Label("", id="error_label")
            with Horizontal():
                yield Button("Upload", variant="primary", id="upload_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.dismiss(None)
            return

        if event.button.id == "upload_btn":
            local_path = self.query_one("#local_path_field", Input).value.strip()
            bbs_filename = self.query_one("#bbs_filename_field", Input).value.strip()
            description = self.query_one("#description_field", Input).value.strip()

            error = self._validate(local_path, bbs_filename, description)
            if error:
                label = self.query_one("#error_label", Label)
                label.update(error)
                label.add_class("visible")
                return

            self.dismiss(UploadFileCommand(
                local_path=local_path,
                bbs_filename=bbs_filename,
                description=description,
            ))

    def on_input_changed(self, event: Input.Changed) -> None:
        # Auto-fill BBS filename from local path if BBS filename is still empty.
        if event.input.id == "local_path_field":
            bbs_field = self.query_one("#bbs_filename_field", Input)
            if not bbs_field.value.strip():
                local_path = event.value.strip()
                if local_path:
                    bbs_field.value = Path(local_path).name

        # Clear error label on any input change.
        label = self.query_one("#error_label", Label)
        label.remove_class("visible")

    def _validate(self, local_path: str, bbs_filename: str, description: str) -> str:
        """Return an error message, or empty string if valid."""
        if not local_path:
            return "Local file path is required."
        path = Path(local_path)
        if not path.exists():
            return f"File not found: {local_path}"
        if not path.is_file():
            return f"Not a file: {local_path}"
        if not bbs_filename:
            return "BBS filename is required."
        if not description:
            return "Description is required."
        from open_packet.node.bpq import MAX_FILE_SIZE
        try:
            size = len(path.read_text(errors="replace").encode())
        except OSError as exc:
            return f"Cannot read file: {exc}"
        if size > MAX_FILE_SIZE:
            return (
                f"File too large: {size:,} bytes "
                f"(maximum is {MAX_FILE_SIZE:,} bytes)."
            )
        return ""
