# tests/test_engine/test_engine.py
import queue
import time
import tempfile
import os
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from open_packet.engine.engine import Engine
from open_packet.engine.commands import CheckMailCommand, DisconnectCommand
from open_packet.engine.events import (
    ConnectionStatusEvent, SyncCompleteEvent, ErrorEvent, ConnectionStatus
)
from open_packet.store.database import Database
from open_packet.store.store import Store
from open_packet.store.models import Operator, Node, Message, Bulletin
from open_packet.node.base import MessageHeader, Message as NodeMessage


@pytest.fixture
def db_and_store():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    db = Database(f.name)
    db.initialize()
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    store = Store(db)
    yield db, store, op, node
    db.close()
    os.unlink(f.name)


def make_mock_node(messages=None, bulletins=None):
    node = MagicMock()
    node.list_messages.return_value = messages or []
    node.list_bulletins.return_value = bulletins or []
    node.read_message.return_value = NodeMessage(
        header=MagicMock(bbs_id="1", from_call="W0TEST", to_call="KD9ABC",
                          subject="Hello", date_str="03/22"),
        body="Test body",
    )
    return node


def test_engine_check_mail_emits_sync_complete(db_and_store):
    db, store, op, node_record = db_and_store
    mock_node = make_mock_node(
        messages=[MessageHeader(bbs_id="1", to_call="KD9ABC",
                                from_call="W0TEST", subject="Hello")]
    )
    mock_connection = MagicMock()

    cmd_queue = queue.Queue()
    evt_queue = queue.Queue()

    engine = Engine(
        command_queue=cmd_queue,
        event_queue=evt_queue,
        store=store,
        operator=op,
        node_record=node_record,
        connection=mock_connection,
        node=mock_node,
    )
    engine.start()

    cmd_queue.put(CheckMailCommand())
    # Wait for sync complete event
    events = []
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            events.append(evt_queue.get(timeout=0.5))
        except queue.Empty:
            break

    engine.stop()

    event_types = [type(e).__name__ for e in events]
    assert "SyncCompleteEvent" in event_types


def test_engine_emits_connection_status(db_and_store):
    db, store, op, node_record = db_and_store
    mock_node = make_mock_node()
    mock_connection = MagicMock()

    cmd_queue = queue.Queue()
    evt_queue = queue.Queue()

    engine = Engine(
        command_queue=cmd_queue, event_queue=evt_queue,
        store=store, operator=op, node_record=node_record,
        connection=mock_connection, node=mock_node,
    )
    engine.start()
    cmd_queue.put(CheckMailCommand())

    events = []
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            events.append(evt_queue.get(timeout=0.5))
        except queue.Empty:
            break

    engine.stop()
    status_events = [e for e in events if isinstance(e, ConnectionStatusEvent)]
    assert len(status_events) >= 1
