# tests/test_engine/test_engine.py
import queue
import time
import tempfile
import os
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from open_packet.engine.engine import Engine
from open_packet.engine.commands import CheckMailCommand, DisconnectCommand, SendMessageCommand, PostBulletinCommand
from open_packet.engine.events import (
    ConnectionStatusEvent, SyncCompleteEvent, ErrorEvent, ConnectionStatus,
    MessageQueuedEvent,
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


def test_send_message_command_saves_to_outbox(db_and_store):
    """SendMessageCommand saves a queued message; does NOT transmit immediately."""
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
    cmd_queue.put(SendMessageCommand(to_call="W0TEST", subject="Hi", body="Body"))

    events = []
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        try:
            events.append(evt_queue.get(timeout=0.3))
        except queue.Empty:
            pass

    engine.stop()

    # MessageQueuedEvent must be emitted
    assert any(isinstance(e, MessageQueuedEvent) for e in events)
    # Message must be in the outbox
    outbox = store.list_outbox(op.id)
    assert len(outbox) == 1
    assert outbox[0].to_call == "W0TEST"
    # Node send_message must NOT have been called (not a sync)
    mock_node.send_message.assert_not_called()


def test_check_mail_sends_only_queued_messages(db_and_store):
    """Only outbox messages are transmitted during sync; received messages are never re-sent."""
    db, store, op, node_record = db_and_store

    # Pre-populate: one received inbox message (queued=False)
    store.save_message(Message(
        operator_id=op.id, node_id=node_record.id, bbs_id="RX1",
        from_call="W0A", to_call="KD9ABC",
        subject="Received", body="body",
        timestamp=datetime.now(timezone.utc),
    ))
    # Pre-populate: one outbox message (queued=True)
    store.save_message(Message(
        operator_id=op.id, node_id=node_record.id, bbs_id="",
        from_call="KD9ABC-1", to_call="W0B",
        subject="Outgoing", body="body",
        timestamp=datetime.now(timezone.utc),
        queued=True,
    ))

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

    sync_events = [e for e in events if isinstance(e, SyncCompleteEvent)]
    assert len(sync_events) == 1
    assert sync_events[0].messages_sent == 1   # only the queued message
    # send_message called exactly once, with outgoing subject
    mock_node.send_message.assert_called_once()
    call_args = mock_node.send_message.call_args
    assert call_args[0][1] == "Outgoing"  # subject is second positional arg


def test_multiple_compose_actions_each_queued(db_and_store):
    """Composing three messages results in three outbox rows."""
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
    for i in range(3):
        cmd_queue.put(SendMessageCommand(to_call="W0TEST", subject=f"Msg {i}", body="b"))

    # Drain events
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        try:
            evt_queue.get(timeout=0.2)
        except queue.Empty:
            break

    engine.stop()
    assert len(store.list_outbox(op.id)) == 3


def test_engine_do_post_bulletin_saves_to_outbox(db_and_store):
    """PostBulletinCommand saves a queued Bulletin to the store outbox."""
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
    cmd_queue.put(PostBulletinCommand(category="WX", subject="WX Report", body="Sunny."))

    events = []
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            events.append(evt_queue.get(timeout=0.5))
        except queue.Empty:
            break
    engine.stop()

    assert any(isinstance(e, MessageQueuedEvent) for e in events)
    outbox = store.list_outbox_bulletins(op.id)
    assert len(outbox) == 1
    assert outbox[0].category == "WX"
    assert outbox[0].queued is True
    assert outbox[0].sent is False


def test_engine_check_mail_retrieves_bulletins(db_and_store):
    """_do_check_mail() phase 4 saves retrieved bulletins and reports count."""
    db, store, op, node_record = db_and_store
    mock_node = make_mock_node(
        bulletins=[
            MessageHeader(bbs_id="BUL-1", to_call="WX", from_call="W0WX", subject="WX Alert"),
        ]
    )
    mock_node.read_bulletin.return_value = NodeMessage(
        header=mock_node.list_bulletins.return_value[0],
        body="Tornado watch.",
    )
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

    sync_events = [e for e in events if isinstance(e, SyncCompleteEvent)]
    assert sync_events
    assert sync_events[0].bulletins_retrieved == 1
    bulletins = store.list_bulletins(op.id)
    assert len(bulletins) == 1
    assert bulletins[0].bbs_id == "BUL-1"
    assert bulletins[0].category == "WX"
