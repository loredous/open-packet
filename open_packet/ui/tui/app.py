# open_packet/ui/tui/app.py
from __future__ import annotations
import logging
import os
import queue
import threading
from typing import Optional

from textual.app import App, ComposeResult

from open_packet.config.config import AppConfig, load_config
from open_packet.engine.commands import (
    CheckMailCommand, DeleteMessageCommand, SendMessageCommand
)
from open_packet.engine.engine import Engine
from open_packet.engine.events import (
    ConnectionStatusEvent, MessageReceivedEvent, SyncCompleteEvent,
    ErrorEvent, ConnectionStatus,
)
from open_packet.link.kiss import KISSLink
from open_packet.node.bpq import BPQNode
from open_packet.store.database import Database
from open_packet.store.store import Store
from open_packet.transport.tcp import TCPTransport
from open_packet.transport.serial import SerialTransport
from open_packet.ui.tui.screens.compose import ComposeScreen
from open_packet.ui.tui.screens.main import MainScreen

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "~/.config/open-packet/config.yaml"


def _setup_logging(log_path: str) -> None:
    from logging.handlers import RotatingFileHandler
    os.makedirs(os.path.dirname(os.path.expanduser(log_path)), exist_ok=True)
    handler = RotatingFileHandler(
        os.path.expanduser(log_path), maxBytes=5_000_000, backupCount=5
    )
    logging.basicConfig(
        level=logging.INFO,
        handlers=[handler],
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )


class OpenPacketApp(App):
    SCREENS = {"compose": ComposeScreen}
    TITLE = "open-packet"

    def __init__(self, config: AppConfig, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self._cmd_queue: queue.Queue = queue.Queue()
        self._evt_queue: queue.Queue = queue.Queue()
        self._engine: Optional[Engine] = None
        self._selected_message = None
        self._store: Optional[Store] = None
        self._active_operator = None
        self._active_folder = "Inbox"
        self._active_category = ""

    def get_default_screen(self) -> MainScreen:
        return MainScreen()

    def on_mount(self) -> None:
        self._init_engine()
        self.set_interval(0.1, self._poll_events)
        self.call_after_refresh(self._refresh_message_list)

    def _init_engine(self) -> None:
        db_path = os.path.expanduser(self.config.store.db_path)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        db = Database(db_path)
        db.initialize()
        store = Store(db)

        operator = db.get_default_operator()
        node_record = db.get_default_node()
        if not operator or not node_record:
            self.notify("No operator or node configured. Add them to the database.", severity="error")
            return

        self._store = store
        self._active_operator = operator

        # Build transport + link
        conn_cfg = self.config.connection
        if conn_cfg.type == "kiss_tcp":
            transport = TCPTransport(host=conn_cfg.host, port=conn_cfg.port)
        else:
            transport = SerialTransport(device=conn_cfg.device, baud=conn_cfg.baud)

        connection = KISSLink(transport=transport)
        node = BPQNode(
            connection=connection,
            node_callsign=node_record.callsign,
            node_ssid=node_record.ssid,
            my_callsign=operator.callsign,
            my_ssid=operator.ssid,
        )

        export_path = os.path.expanduser(self.config.store.export_path) if self.config.store.export_path else None

        self._engine = Engine(
            command_queue=self._cmd_queue,
            event_queue=self._evt_queue,
            store=store,
            operator=operator,
            node_record=node_record,
            connection=connection,
            node=node,
            export_path=export_path,
        )
        self._engine.start()

    def _poll_events(self) -> None:
        while not self._evt_queue.empty():
            try:
                event = self._evt_queue.get_nowait()
                self._handle_event(event)
            except queue.Empty:
                break

    def _handle_event(self, event) -> None:
        try:
            status_bar = self.query_one("StatusBar")
        except Exception:
            return

        if isinstance(event, ConnectionStatusEvent):
            status_bar.status = event.status
            if event.status == ConnectionStatus.ERROR:
                self.notify(f"Error: {event.detail}", severity="error")
        elif isinstance(event, SyncCompleteEvent):
            from datetime import datetime
            status_bar.last_sync = datetime.now().strftime("%H:%M")
            self.notify(
                f"Sync complete: {event.messages_retrieved} new, {event.messages_sent} sent"
            )
            self._refresh_message_list()
        elif isinstance(event, ErrorEvent):
            self.notify(f"Error: {event.message}", severity="error")

    def _refresh_message_list(self) -> None:
        if not self._store or not self._active_operator:
            return
        try:
            msg_list = self.query_one("MessageList")
            folder = self._active_folder
            category = self._active_category
            operator_id = self._active_operator.id

            if folder == "Inbox":
                messages = [
                    m for m in self._store.list_messages(operator_id=operator_id)
                    if not m.sent
                ]
            elif folder == "Sent":
                messages = [
                    m for m in self._store.list_messages(operator_id=operator_id)
                    if m.sent
                ]
            elif folder == "Bulletins":
                messages = self._store.list_bulletins(
                    operator_id=operator_id,
                    category=category or None,
                )
            else:
                messages = []

            msg_list.load_messages(messages)
        except Exception:
            logger.exception("Failed to refresh message list")

    def check_mail(self) -> None:
        if self._engine:
            self._cmd_queue.put(CheckMailCommand())

    def delete_selected_message(self) -> None:
        if self._selected_message and self._engine:
            self._cmd_queue.put(DeleteMessageCommand(
                message_id=self._selected_message.id,
                bbs_id=self._selected_message.bbs_id,
            ))

    def reply_to_selected(self) -> None:
        if self._selected_message:
            self.push_screen(ComposeScreen())

    def on_compose_screen_dismiss(self, result) -> None:
        if result and isinstance(result, SendMessageCommand):
            self._cmd_queue.put(result)

    def on_message_list_message_selected(self, event) -> None:
        self._selected_message = event.message
        try:
            self.query_one("MessageBody").show_message(event.message)
        except Exception:
            pass

    def on_folder_tree_folder_selected(self, event) -> None:
        self._active_folder = event.folder
        self._active_category = getattr(event, "category", "")
        self._refresh_message_list()


def main() -> None:
    import sys
    config_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CONFIG_PATH
    _setup_logging("~/.local/share/open-packet/open-packet.log")
    try:
        config = load_config(os.path.expanduser(config_path))
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        sys.exit(1)
    app = OpenPacketApp(config=config)
    app.run()
