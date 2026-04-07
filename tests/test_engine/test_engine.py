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
    MessageQueuedEvent, Event, NeighborsDiscoveredEvent,
)
from open_packet.store.database import Database
from open_packet.store.store import Store
from open_packet.store.models import Operator, Node, Message, Bulletin, NodeHop
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
    """_do_check_mail() phase 4 saves bulletin headers only (body=None, count=0)."""
    db, store, op, node_record = db_and_store
    mock_node = make_mock_node(
        bulletins=[
            MessageHeader(bbs_id="BUL-1", to_call="WX", from_call="W0WX", subject="WX Alert"),
        ]
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
    # Phase 4 saves headers only — no bodies retrieved, so count is 0
    assert sync_events[0].bulletins_retrieved == 0
    bulletins = store.list_bulletins(op.id)
    assert len(bulletins) == 1
    assert bulletins[0].bbs_id == "BUL-1"
    assert bulletins[0].category == "WX"
    assert bulletins[0].body is None
    # read_bulletin must NOT have been called
    mock_node.read_bulletin.assert_not_called()


def test_check_mail_saves_bulletin_headers_only(db_and_store):
    """Phase 4 saves header-only bulletin rows; read_bulletin is NOT called."""
    db, store, op, node_record = db_and_store
    mock_node = make_mock_node(
        bulletins=[
            MessageHeader(bbs_id="B1", to_call="WX", from_call="W0WX",
                          subject="Storm warning", date_str="04/06"),
        ]
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

    # read_bulletin must NOT be called — we only listed headers
    mock_node.read_bulletin.assert_not_called()

    # Header must be stored with body=None
    bulletins = store.list_bulletins(operator_id=op.id)
    assert len(bulletins) == 1
    assert bulletins[0].bbs_id == "B1"
    assert bulletins[0].body is None
    assert bulletins[0].wants_retrieval is False


def test_check_mail_retrieves_body_for_queued_bulletins(db_and_store):
    """Phase 5 calls read_bulletin for bulletins where wants_retrieval=True."""
    db, store, op, node_record = db_and_store

    # Pre-populate a header-only bulletin marked for retrieval
    from datetime import datetime, timezone
    from open_packet.store.models import Bulletin as BulletinModel
    pre = store.save_bulletin(BulletinModel(
        operator_id=op.id, node_id=node_record.id, bbs_id="B2",
        category="WX", from_call="W0WX", subject="Pre-existing header",
        timestamp=datetime.now(timezone.utc),
    ))
    store.mark_bulletin_wants_retrieval(pre.id)

    mock_node = make_mock_node(bulletins=[])  # listing returns nothing new
    mock_node.read_bulletin.return_value = NodeMessage(
        header=MagicMock(bbs_id="B2"), body="Full storm bulletin body."
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

    mock_node.read_bulletin.assert_called_once_with("B2")

    updated = store._get_bulletin(pre.id)
    assert updated.body == "Full storm bulletin body."
    assert updated.synced_at is not None

    sync_events = [e for e in events if isinstance(e, SyncCompleteEvent)]
    assert len(sync_events) == 1
    assert sync_events[0].bulletins_retrieved == 1


def test_neighbors_discovered_event_in_union():
    import typing
    args = typing.get_args(Event)
    assert NeighborsDiscoveredEvent in args


# --- Discovery phase tests ---

from open_packet.config.config import AppConfig, NodesConfig


class MockConnection:
    def connect(self, *a, **kw): pass
    def disconnect(self): pass
    def send_frame(self, d): pass
    def receive_frame(self, timeout=5.0): return b""


class MockNodeWithNeighbors:
    """Like MockNode but list_linked_nodes returns a fixed list."""
    def __init__(self, neighbors):
        self._neighbors = neighbors
        self.connected = False
        self.messages = []
        self.bulletins = []

    def connect_node(self): self.connected = True
    def list_messages(self): return []
    def read_message(self, bbs_id): return None
    def send_message(self, *a): pass
    def delete_message(self, *a): pass
    def list_bulletins(self, **kw): return []
    def read_bulletin(self, bbs_id): return None
    def post_bulletin(self, *a): pass
    def list_linked_nodes(self): return self._neighbors


def _make_engine(neighbors, auto_discover):
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    db = Database(f.name)
    db.initialize()
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="me", is_default=True))
    node_rec = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1,
                                    node_type="bpq", is_default=True))
    store = Store(db)
    mock_node = MockNodeWithNeighbors(neighbors)
    cfg = AppConfig(nodes=NodesConfig(auto_discover=auto_discover))
    cmd_q, evt_q = queue.Queue(), queue.Queue()
    engine = Engine(
        command_queue=cmd_q, event_queue=evt_q, store=store,
        operator=op, node_record=node_rec,
        connection=MockConnection(), node=mock_node,
        config=cfg,
    )
    engine.start()
    return engine, store, mock_node, db, f.name  # return db and path for cleanup


@pytest.fixture
def engine_with_discovery():
    engine, store, node, db, tmp_path = _make_engine(
        neighbors=[NodeHop("W0RELAY-1", port=3)],
        auto_discover=True,
    )
    yield engine, store, node
    engine.stop()
    db.close()
    os.unlink(tmp_path)


@pytest.fixture
def engine_no_discovery():
    engine, store, node, db, tmp_path = _make_engine(
        neighbors=[NodeHop("W0RELAY-1", port=3)],
        auto_discover=False,
    )
    yield engine, store, node
    engine.stop()
    db.close()
    os.unlink(tmp_path)


def test_discovery_phase_upserts_neighbors(engine_with_discovery):
    """When auto_discover=True, check_mail upserts discovered neighbors."""
    engine, store, mock_node = engine_with_discovery
    engine._cmd_queue.put(CheckMailCommand())
    import time
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        neighbors = store.get_node_neighbors(engine._node_record.id)
        if any(n.callsign == "W0RELAY-1" for n in neighbors):
            break
        time.sleep(0.05)
    neighbors = store.get_node_neighbors(engine._node_record.id)
    assert any(n.callsign == "W0RELAY-1" for n in neighbors)


def test_discovery_phase_emits_new_neighbor_event(engine_with_discovery):
    engine, store, mock_node = engine_with_discovery
    engine._cmd_queue.put(CheckMailCommand())
    import time
    neighbor_events = []
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and not neighbor_events:
        while not engine._evt_queue.empty():
            evt = engine._evt_queue.get_nowait()
            if isinstance(evt, NeighborsDiscoveredEvent):
                neighbor_events.append(evt)
        time.sleep(0.05)
    assert len(neighbor_events) == 1
    assert neighbor_events[0].new_neighbors[0].callsign == "W0RELAY-1"


def test_discovery_phase_skipped_when_disabled(engine_no_discovery):
    engine, store, mock_node = engine_no_discovery
    engine._cmd_queue.put(CheckMailCommand())
    import time
    # Wait for sync to complete (SyncCompleteEvent), then check neighbors
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if not engine._evt_queue.empty():
            break
        time.sleep(0.05)
    time.sleep(0.1)  # Small extra wait after first event
    neighbors = store.get_node_neighbors(engine._node_record.id)
    assert neighbors == []


def test_neighbors_discovered_event_fields(db_and_store):
    db, store, op, node_record = db_and_store
    node = Node(label="x", callsign="W0BPQ", ssid=0, node_type="bpq", id=1)
    evt = NeighborsDiscoveredEvent(
        node_id=1,
        new_neighbors=[NodeHop("W0RELAY-1", port=3)],
        shorter_path_candidates=[(node, [NodeHop("W0RELAY-1", port=3)])],
    )
    assert evt.node_id == 1
    assert evt.new_neighbors[0].callsign == "W0RELAY-1"
    assert evt.shorter_path_candidates[0][0].callsign == "W0BPQ"


def test_queue_neighbor_prompts_builds_correct_entries():
    """_queue_neighbor_prompts builds one 'new' entry and one 'shorter' entry."""
    from open_packet.engine.events import NeighborsDiscoveredEvent
    from open_packet.store.models import NodeHop, Node

    existing = Node(label="BBS2", callsign="W0DIST", ssid=0, node_type="bpq",
                    hop_path=[NodeHop("W0LONG1"), NodeHop("W0LONG2"), NodeHop("W0DIST")],
                    id=99)
    new_hop = NodeHop("W0NEW-1", port=2)
    shorter_hop = NodeHop("W0DIST", port=1)
    evt = NeighborsDiscoveredEvent(
        node_id=1,
        new_neighbors=[new_hop],
        shorter_path_candidates=[(existing, [shorter_hop])],
    )
    # Build the prompts list manually using the same logic as _queue_neighbor_prompts
    prompts = []
    for hop in evt.new_neighbors:
        prompts.append(("new", hop, None))
    for existing_node, new_path in evt.shorter_path_candidates:
        prompts.append(("shorter", None, (existing_node, new_path)))

    assert len(prompts) == 2
    assert prompts[0][0] == "new"
    assert prompts[0][1].callsign == "W0NEW-1"
    assert prompts[1][0] == "shorter"
    assert prompts[1][1] is None  # must be None, not an unbound variable
    assert prompts[1][2][0].callsign == "W0DIST"


def test_auto_forward_syncs_via_neighbors(tmp_path):
    """When auto_forward=True on a node, engine re-connects to each stored neighbor."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    db = Database(f.name); db.initialize()
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="me", is_default=True))
    node_rec = db.insert_node(Node(
        label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
        is_default=True, auto_forward=True,
    ))
    store = Store(db)
    # Pre-seed a neighbor
    store.upsert_node_neighbor(node_rec.id, "W0RELAY-1", port=3)

    connect_calls = []
    class TrackingConnection:
        def connect(self, *a, **kw): connect_calls.append((a, kw))
        def disconnect(self): pass
        def send_frame(self, d): pass
        def receive_frame(self, timeout=5.0): return b""

    mock_node = MockNodeWithNeighbors([])
    cfg = AppConfig(nodes=NodesConfig(auto_discover=False))
    cmd_q, evt_q = queue.Queue(), queue.Queue()
    engine = Engine(
        command_queue=cmd_q, event_queue=evt_q, store=store,
        operator=op, node_record=node_rec,
        connection=TrackingConnection(), node=mock_node, config=cfg,
    )
    engine.start()
    cmd_q.put(CheckMailCommand())
    import time
    # Wait up to 3s for at least 2 connect calls
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and len(connect_calls) < 2:
        time.sleep(0.05)
    engine.stop()
    db.close()
    os.unlink(f.name)
    # Should have connected at least twice: primary + auto-forward neighbor
    assert len(connect_calls) >= 2
