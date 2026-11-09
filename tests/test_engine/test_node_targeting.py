"""Tests for per-node targeting of outbound messages/bulletins (issue #14)."""
import queue
import time
import tempfile
import os
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from open_packet.engine.engine import Engine
from open_packet.engine.commands import SendMessageCommand, PostBulletinCommand, CheckMailCommand
from open_packet.engine.events import MessageQueuedEvent, SyncCompleteEvent
from open_packet.store.database import Database
from open_packet.store.store import Store
from open_packet.store.models import Operator, Node


@pytest.fixture
def db_with_two_nodes():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    db = Database(f.name)
    db.initialize()
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    node_a = db.insert_node(Node(label="Node A", callsign="W0AAA", ssid=0, node_type="bpq", is_default=True))
    node_b = db.insert_node(Node(label="Node B", callsign="W0BBB", ssid=0, node_type="bpq"))
    store = Store(db)
    yield db, store, op, node_a, node_b
    db.close()
    os.unlink(f.name)


def _make_engine(store, op, node_record, mock_node=None, mock_connection=None):
    if mock_node is None:
        mock_node = MagicMock()
        mock_node.list_messages.return_value = []
        mock_node.list_bulletins.return_value = []
        mock_node.list_files.return_value = []
    if mock_connection is None:
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
    return engine, cmd_queue, evt_queue


def _drain(evt_queue, timeout=3.0):
    events = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            events.append(evt_queue.get(timeout=0.3))
        except queue.Empty:
            break
    return events


def test_send_message_stores_target_nodes(db_with_two_nodes):
    """SendMessageCommand with node_ids stores them in message_target_nodes."""
    db, store, op, node_a, node_b = db_with_two_nodes
    engine, cmd_queue, evt_queue = _make_engine(store, op, node_a)
    engine.start()

    cmd_queue.put(SendMessageCommand(
        to_call="W0TEST", subject="Multi-node msg", body="body",
        node_ids=[node_a.id, node_b.id],
    ))
    _drain(evt_queue)
    engine.stop()

    outbox = store.list_outbox_messages(op.id)
    assert len(outbox) == 1
    targets = store.get_message_target_nodes(outbox[0].id)
    assert set(targets) == {node_a.id, node_b.id}


def test_send_message_no_node_ids_defaults_to_active_node(db_with_two_nodes):
    """SendMessageCommand without node_ids defaults to the engine's active node."""
    db, store, op, node_a, node_b = db_with_two_nodes
    engine, cmd_queue, evt_queue = _make_engine(store, op, node_a)
    engine.start()

    cmd_queue.put(SendMessageCommand(to_call="W0TEST", subject="Default", body="b"))
    _drain(evt_queue)
    engine.stop()

    outbox = store.list_outbox_messages(op.id)
    assert len(outbox) == 1
    targets = store.get_message_target_nodes(outbox[0].id)
    assert targets == [node_a.id]


def test_post_bulletin_with_node_ids_creates_one_per_node(db_with_two_nodes):
    """PostBulletinCommand with node_ids creates one bulletin per selected node."""
    db, store, op, node_a, node_b = db_with_two_nodes
    engine, cmd_queue, evt_queue = _make_engine(store, op, node_a)
    engine.start()

    cmd_queue.put(PostBulletinCommand(
        category="WX", subject="WX Report", body="Sunny.",
        node_ids=[node_a.id, node_b.id],
    ))
    _drain(evt_queue)
    engine.stop()

    outbox = store.list_outbox_bulletins(op.id)
    assert len(outbox) == 2
    node_ids_in_outbox = {b.node_id for b in outbox}
    assert node_ids_in_outbox == {node_a.id, node_b.id}


def test_post_bulletin_no_node_ids_defaults_to_active_node(db_with_two_nodes):
    """PostBulletinCommand without node_ids defaults to the engine's active node."""
    db, store, op, node_a, node_b = db_with_two_nodes
    engine, cmd_queue, evt_queue = _make_engine(store, op, node_a)
    engine.start()

    cmd_queue.put(PostBulletinCommand(category="WX", subject="WX", body="body"))
    _drain(evt_queue)
    engine.stop()

    outbox = store.list_outbox_bulletins(op.id)
    assert len(outbox) == 1
    assert outbox[0].node_id == node_a.id


def test_check_mail_only_sends_messages_targeted_at_syncing_node(db_with_two_nodes):
    """During sync with node A, only messages targeting node A are sent."""
    db, store, op, node_a, node_b = db_with_two_nodes

    # Create a message targeting only node B (not node A)
    from open_packet.store.models import Message
    msg_b = store.save_message(Message(
        operator_id=op.id, node_id=node_b.id, bbs_id="",
        from_call="KD9ABC-1", to_call="W0TEST",
        subject="For Node B only", body="body",
        timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    store.add_message_target_nodes(msg_b.id, [node_b.id])

    # Also create a message targeting node A
    msg_a = store.save_message(Message(
        operator_id=op.id, node_id=node_a.id, bbs_id="",
        from_call="KD9ABC-1", to_call="W0TEST",
        subject="For Node A only", body="body",
        timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    store.add_message_target_nodes(msg_a.id, [node_a.id])

    mock_node = MagicMock()
    mock_node.list_messages.return_value = []
    mock_node.list_bulletins.return_value = []
    mock_node.list_files.return_value = []

    engine, cmd_queue, evt_queue = _make_engine(store, op, node_a, mock_node=mock_node)
    engine.start()
    cmd_queue.put(CheckMailCommand())
    events = _drain(evt_queue, timeout=5.0)
    engine.stop()

    sync_events = [e for e in events if isinstance(e, SyncCompleteEvent)]
    assert sync_events
    assert sync_events[0].messages_sent == 1  # only node A message

    # send_message called once with the node A subject
    mock_node.send_message.assert_called_once()
    args = mock_node.send_message.call_args[0]
    assert args[1] == "For Node A only"


def test_check_mail_send_failure_leaves_message_in_outbox(db_with_two_nodes):
    """If send_message raises, the message stays unsent in the outbox."""
    db, store, op, node_a, node_b = db_with_two_nodes

    from open_packet.store.models import Message
    msg = store.save_message(Message(
        operator_id=op.id, node_id=node_a.id, bbs_id="",
        from_call="KD9ABC-1", to_call="W0TEST",
        subject="Failing Msg", body="body",
        timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    store.add_message_target_nodes(msg.id, [node_a.id])

    mock_node = MagicMock()
    mock_node.list_messages.return_value = []
    mock_node.list_bulletins.return_value = []
    mock_node.list_files.return_value = []
    mock_node.send_message.side_effect = RuntimeError("Connection dropped")

    engine, cmd_queue, evt_queue = _make_engine(store, op, node_a, mock_node=mock_node)
    engine.start()
    cmd_queue.put(CheckMailCommand())
    _drain(evt_queue, timeout=5.0)
    engine.stop()

    # Message should still be in outbox (not marked sent)
    remaining = store.list_outbox_messages(op.id, node_id=node_a.id)
    assert len(remaining) == 1
    assert remaining[0].subject == "Failing Msg"
