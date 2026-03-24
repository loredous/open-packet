# open_packet/engine/engine.py
from __future__ import annotations
import logging
import queue
import threading
from datetime import datetime, timezone
from typing import Optional

from open_packet.engine.commands import (
    Command, CheckMailCommand, ConnectCommand, DisconnectCommand,
    SendMessageCommand, DeleteMessageCommand,
)
from open_packet.engine.events import (
    ConnectionStatusEvent, ConnectionStatus, MessageReceivedEvent,
    SyncCompleteEvent, ErrorEvent, MessageQueuedEvent,
)
from open_packet.link.base import ConnectionBase
from open_packet.node.base import NodeBase
from open_packet.store.models import Operator, Node, Message, Bulletin
from open_packet.store.store import Store

logger = logging.getLogger(__name__)


class Engine:
    def __init__(
        self,
        command_queue: queue.Queue,
        event_queue: queue.Queue,
        store: Store,
        operator: Operator,
        node_record: Node,
        connection: ConnectionBase,
        node: NodeBase,
        export_path: Optional[str] = None,
    ):
        self._cmd_queue = command_queue
        self._evt_queue = event_queue
        self._store = store
        self._operator = operator
        self._node_record = node_record
        self._connection = connection
        self._node = node
        self._export_path = export_path

        # In-memory state
        self._status = ConnectionStatus.DISCONNECTED
        self._last_sync: Optional[datetime] = None
        self._messages_last_sync = 0

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=5.0)

    @property
    def last_sync(self) -> Optional[datetime]:
        return self._last_sync

    @property
    def status(self) -> ConnectionStatus:
        return self._status

    def _emit(self, event) -> None:
        self._evt_queue.put(event)

    def _set_status(self, status: ConnectionStatus, detail: str = "") -> None:
        self._status = status
        self._emit(ConnectionStatusEvent(status=status, detail=detail))

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                cmd = self._cmd_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self._handle(cmd)
            except Exception as e:
                logger.exception("Engine error handling %s", type(cmd).__name__)
                self._emit(ErrorEvent(message=str(e)))
                self._set_status(ConnectionStatus.ERROR, str(e))

    def _handle(self, cmd: Command) -> None:
        if isinstance(cmd, CheckMailCommand):
            self._do_check_mail()
        elif isinstance(cmd, SendMessageCommand):
            self._do_send_message(cmd)
        elif isinstance(cmd, DeleteMessageCommand):
            self._do_delete_message(cmd)
        elif isinstance(cmd, ConnectCommand):
            self._do_connect()
        elif isinstance(cmd, DisconnectCommand):
            self._do_disconnect()

    def _do_connect(self) -> None:
        self._set_status(ConnectionStatus.CONNECTING)
        self._connection.connect(
            callsign=self._node_record.callsign,
            ssid=self._node_record.ssid,
        )
        self._node.connect_node()
        self._set_status(ConnectionStatus.CONNECTED)

    def _do_disconnect(self) -> None:
        self._connection.disconnect()
        self._set_status(ConnectionStatus.DISCONNECTED)

    def _do_check_mail(self) -> None:
        self._set_status(ConnectionStatus.CONNECTING)
        try:
            self._connection.connect(
                callsign=self._node_record.callsign,
                ssid=self._node_record.ssid,
            )
            self._node.connect_node()
            self._set_status(ConnectionStatus.SYNCING)

            retrieved = 0
            headers = self._node.list_messages()
            for header in headers:
                msg = self._node.read_message(header.bbs_id)
                now = datetime.now(timezone.utc)
                saved = self._store.save_message(Message(
                    operator_id=self._operator.id,
                    node_id=self._node_record.id,
                    bbs_id=header.bbs_id,
                    from_call=header.from_call,
                    to_call=header.to_call,
                    subject=header.subject,
                    body=msg.body,
                    timestamp=now,
                ))
                if saved:
                    retrieved += 1
                    self._emit(MessageReceivedEvent(
                        message_id=saved.id,
                        from_call=header.from_call,
                        subject=header.subject,
                    ))

            # Send queued outbound messages
            sent = 0
            outbound = self._store.list_outbox(self._operator.id)
            for m in outbound:
                self._node.send_message(m.to_call, m.subject, m.body)
                self._store.mark_message_sent(m.id)
                sent += 1

            self._last_sync = datetime.now(timezone.utc)
            self._messages_last_sync = retrieved
            self._emit(SyncCompleteEvent(
                messages_retrieved=retrieved,
                messages_sent=sent,
            ))
        finally:
            self._connection.disconnect()
            self._set_status(ConnectionStatus.DISCONNECTED)

    def _do_send_message(self, cmd: SendMessageCommand) -> None:
        now = datetime.now(timezone.utc)
        self._store.save_message(Message(
            operator_id=self._operator.id,
            node_id=self._node_record.id,
            bbs_id="",
            from_call=f"{self._operator.callsign}-{self._operator.ssid}",
            to_call=cmd.to_call,
            subject=cmd.subject,
            body=cmd.body,
            timestamp=now,
            queued=True,
        ))
        self._emit(MessageQueuedEvent())

    def _do_delete_message(self, cmd: DeleteMessageCommand) -> None:
        self._store.delete_message(cmd.message_id)
