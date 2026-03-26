import queue
import time
import tempfile
import os
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from open_packet.engine.engine import Engine
from open_packet.engine.commands import CheckMailCommand
from open_packet.engine.events import SyncCompleteEvent
from open_packet.store.database import Database
from open_packet.store.store import Store
from open_packet.store.models import Operator, Node
from open_packet.node.bpq import BPQNode
from open_packet.link.base import ConnectionBase
from open_packet.node.base import MessageHeader, Message as NodeMessage
from open_packet.config.config import AppConfig, NodesConfig


class ReplayConnection(ConnectionBase):
    """Replays a sequence of raw payload bytes as if received from a BBS."""
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.sent_text: list[str] = []

    def connect(self, callsign: str, ssid: int) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def send_frame(self, data: bytes) -> None:
        self.sent_text.append(data.decode(errors="replace").strip())

    def receive_frame(self, timeout: float = 5.0) -> bytes:
        if self._responses:
            return self._responses.pop(0).encode()
        return b""


def test_full_check_mail_cycle():
    """
    Simulate a BPQ session: connect, list messages, read one message,
    disconnect. Verify the message ends up in the database.
    """
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    try:
        db = Database(f.name)
        db.initialize()
        op = db.insert_operator(
            Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True)
        )
        node_record = db.insert_node(
            Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True)
        )
        store = Store(db)

        # BPQ session transcript
        responses = [
            "BPQ> ",                                              # initial prompt for connect_node
            "Msg  To        From      Date   Subject\n"           # list response
            "1    KD9ABC    W0TEST    03/22  Hello World\n"
            "BPQ> ",
            "From: W0TEST\nTo: KD9ABC\nSubject: Hello World\n\n"  # read response
            "This is the message body.\n"
            "BPQ> ",
            "Enter Subject: BPQ> ",                                # send_message prompt 1 with marker
            "Enter Message: BPQ> ",                                # send_message prompt 2 with marker
            "Message Sent\nBPQ> ",                                  # send_message completion
        ]

        connection = ReplayConnection(responses=responses)
        node = BPQNode(
            connection=connection,
            node_callsign="W0BPQ", node_ssid=1,
            my_callsign="KD9ABC", my_ssid=1,
        )

        cmd_queue = queue.Queue()
        evt_queue = queue.Queue()
        engine = Engine(
            command_queue=cmd_queue, event_queue=evt_queue,
            store=store, operator=op, node_record=node_record,
            connection=connection, node=node,
            config=AppConfig(nodes=NodesConfig(auto_discover=False)),
        )
        engine.start()
        cmd_queue.put(CheckMailCommand())

        # Collect events
        events = []
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            try:
                evt = evt_queue.get(timeout=0.5)
                events.append(evt)
                if isinstance(evt, SyncCompleteEvent):
                    break
            except queue.Empty:
                pass

        engine.stop()

        sync_events = [e for e in events if isinstance(e, SyncCompleteEvent)]
        assert sync_events, "No SyncCompleteEvent received"
        assert sync_events[0].messages_retrieved >= 1

        # Verify message in database
        messages = store.list_messages(operator_id=op.id)
        assert any(m.subject == "Hello World" for m in messages)

    finally:
        db.close()
        os.unlink(f.name)
