# open_packet/ui/tui/app.py
from __future__ import annotations
import logging
import os
import queue
from typing import Optional

from textual.app import App

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
from open_packet.store.models import Operator, Node
from open_packet.store.store import Store
from open_packet.transport.tcp import TCPTransport
from open_packet.transport.serial import SerialTransport
from open_packet.ui.tui.screens.compose import ComposeScreen
from open_packet.ui.tui.screens.main import MainScreen
from open_packet.ui.tui.screens.setup_operator import OperatorSetupScreen
from open_packet.ui.tui.screens.setup_node import NodeSetupScreen

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
        self._active_operator: Optional[Operator] = None
        self._active_folder = "Inbox"
        self._active_category = ""
        self._db: Optional[Database] = None

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
        # Assign self._db BEFORE any early return so _restart_engine can close it.
        self._db = db

        operator = db.get_default_operator()
        node_record = db.get_default_node()

        if not operator:
            self.call_after_refresh(
                lambda: self.push_screen(OperatorSetupScreen(), callback=self._on_operator_setup_result)
            )
            return
        elif not node_record:
            self.call_after_refresh(
                lambda: self.push_screen(NodeSetupScreen(), callback=self._on_node_setup_result)
            )
            return

        self._start_engine(db, operator, node_record)

    def _start_engine(self, db: Database, operator: Operator, node_record: Node) -> None:
        store = Store(db)
        self._store = store
        self._active_operator = operator

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

        export_path = (
            os.path.expanduser(self.config.store.export_path)
            if self.config.store.export_path else None
        )

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

    def _restart_engine(self) -> None:
        if self._engine is not None:
            self._engine.stop()
        if self._db is not None:
            self._db.close()
        self._engine = None
        self._store = None
        self._active_operator = None
        self._db = None
        self._init_engine()

    def _save_operator(self, op: Operator) -> None:
        assert self._db is not None
        if op.is_default:
            self._db.clear_default_operator()
        self._db.insert_operator(op)

    def _save_node(self, node: Node) -> None:
        assert self._db is not None
        if node.is_default:
            self._db.clear_default_node()
        self._db.insert_node(node)

    # --- Dismiss callbacks ---

    def _on_operator_setup_result(self, result) -> None:
        if result is None:
            return
        self._save_operator(result)
        # Check DB state to determine next step (works for both first-run and settings flow)
        if self._db.get_default_node() is None:
            self.push_screen(NodeSetupScreen(), callback=self._on_node_setup_result)
        else:
            self._restart_engine()

    def _on_node_setup_result(self, result) -> None:
        if result is None:
            return
        self._save_node(result)
        self._restart_engine()

    def _on_settings_result(self, result) -> None:
        if result == "operator":
            self.push_screen(OperatorSetupScreen(), callback=self._on_operator_setup_result)
        elif result == "node":
            self.push_screen(NodeSetupScreen(), callback=self._on_node_setup_result)

    # --- Event polling ---

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
            self.push_screen(ComposeScreen(), callback=self._on_compose_result)

    def _on_compose_result(self, result) -> None:
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
