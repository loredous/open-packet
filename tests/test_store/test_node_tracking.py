"""Tests for per-node tracking of messages and bulletins (issue #14)."""
import pytest
from datetime import datetime, timezone

from open_packet.store.database import Database
from open_packet.store.store import Store
from open_packet.store.models import Operator, Node, Message, Bulletin


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "test.db"))
    d.initialize()
    yield d
    d.close()


@pytest.fixture
def db_with_data(db):
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=True))
    node_a = db.insert_node(Node(label="Node A", callsign="W0AAA", ssid=0, node_type="bpq"))
    node_b = db.insert_node(Node(label="Node B", callsign="W0BBB", ssid=0, node_type="bpq"))
    store = Store(db)
    return store, op, node_a, node_b


def _make_queued_message(op_id: int, node_id: int, subject: str = "Test") -> Message:
    return Message(
        operator_id=op_id,
        node_id=node_id,
        bbs_id="",
        from_call="KD9ABC",
        to_call="W0TEST",
        subject=subject,
        body="body",
        timestamp=datetime.now(timezone.utc),
        queued=True,
    )


def _make_queued_bulletin(op_id: int, node_id: int) -> Bulletin:
    return Bulletin(
        operator_id=op_id,
        node_id=node_id,
        bbs_id=f"OUT-{node_id}",
        category="WX",
        from_call="KD9ABC",
        subject="WX Report",
        timestamp=datetime.now(timezone.utc),
        body="Sunny.",
        queued=True,
        sent=False,
    )


# --- message_target_nodes ---

def test_add_and_get_message_target_nodes(db_with_data):
    store, op, node_a, node_b = db_with_data
    msg = store.save_message(_make_queued_message(op.id, node_a.id))
    store.add_message_target_nodes(msg.id, [node_a.id, node_b.id])
    targets = store.get_message_target_nodes(msg.id)
    assert set(targets) == {node_a.id, node_b.id}


def test_add_message_target_nodes_idempotent(db_with_data):
    store, op, node_a, node_b = db_with_data
    msg = store.save_message(_make_queued_message(op.id, node_a.id))
    store.add_message_target_nodes(msg.id, [node_a.id])
    store.add_message_target_nodes(msg.id, [node_a.id])  # duplicate insert
    targets = store.get_message_target_nodes(msg.id)
    assert targets.count(node_a.id) == 1


def test_get_message_target_nodes_empty(db_with_data):
    store, op, node_a, node_b = db_with_data
    msg = store.save_message(_make_queued_message(op.id, node_a.id))
    # No target nodes added
    assert store.get_message_target_nodes(msg.id) == []


# --- list_outbox_messages with node_id filter ---

def test_list_outbox_messages_no_filter_returns_all(db_with_data):
    store, op, node_a, node_b = db_with_data
    store.save_message(_make_queued_message(op.id, node_a.id, "Msg A"))
    store.save_message(_make_queued_message(op.id, node_b.id, "Msg B"))
    outbox = store.list_outbox_messages(op.id)
    assert len(outbox) == 2


def test_list_outbox_messages_filters_by_target_node(db_with_data):
    """Messages with target nodes set are only returned when node matches."""
    store, op, node_a, node_b = db_with_data

    msg_a = store.save_message(_make_queued_message(op.id, node_a.id, "For A"))
    store.add_message_target_nodes(msg_a.id, [node_a.id])

    msg_b = store.save_message(_make_queued_message(op.id, node_b.id, "For B"))
    store.add_message_target_nodes(msg_b.id, [node_b.id])

    outbox_a = store.list_outbox_messages(op.id, node_id=node_a.id)
    assert len(outbox_a) == 1
    assert outbox_a[0].subject == "For A"

    outbox_b = store.list_outbox_messages(op.id, node_id=node_b.id)
    assert len(outbox_b) == 1
    assert outbox_b[0].subject == "For B"


def test_list_outbox_messages_multi_node_target(db_with_data):
    """Message targeting both nodes appears in both nodes' outboxes."""
    store, op, node_a, node_b = db_with_data

    msg = store.save_message(_make_queued_message(op.id, node_a.id, "For Both"))
    store.add_message_target_nodes(msg.id, [node_a.id, node_b.id])

    outbox_a = store.list_outbox_messages(op.id, node_id=node_a.id)
    outbox_b = store.list_outbox_messages(op.id, node_id=node_b.id)

    assert any(m.subject == "For Both" for m in outbox_a)
    assert any(m.subject == "For Both" for m in outbox_b)


def test_list_outbox_messages_legacy_fallback_to_node_id(db_with_data):
    """Legacy messages with no target nodes fall back to message.node_id for filtering."""
    store, op, node_a, node_b = db_with_data

    # Pre-existing queued message without any message_target_nodes entries
    store.save_message(_make_queued_message(op.id, node_a.id, "Legacy A"))

    outbox_a = store.list_outbox_messages(op.id, node_id=node_a.id)
    outbox_b = store.list_outbox_messages(op.id, node_id=node_b.id)

    assert len(outbox_a) == 1
    assert len(outbox_b) == 0


def test_list_outbox_messages_sent_messages_excluded(db_with_data):
    store, op, node_a, node_b = db_with_data
    msg = store.save_message(_make_queued_message(op.id, node_a.id))
    store.add_message_target_nodes(msg.id, [node_a.id])
    store.mark_message_sent(msg.id)
    assert store.list_outbox_messages(op.id, node_id=node_a.id) == []


# --- list_outbox_bulletins with node_id filter ---

def test_list_outbox_bulletins_no_filter_returns_all(db_with_data):
    store, op, node_a, node_b = db_with_data
    store.save_bulletin(_make_queued_bulletin(op.id, node_a.id))
    store.save_bulletin(_make_queued_bulletin(op.id, node_b.id))
    outbox = store.list_outbox_bulletins(op.id)
    assert len(outbox) == 2


def test_list_outbox_bulletins_filters_by_node(db_with_data):
    store, op, node_a, node_b = db_with_data

    bul_a = _make_queued_bulletin(op.id, node_a.id)
    bul_b = _make_queued_bulletin(op.id, node_b.id)
    bul_b.bbs_id = "OUT-B"
    store.save_bulletin(bul_a)
    store.save_bulletin(bul_b)

    outbox_a = store.list_outbox_bulletins(op.id, node_id=node_a.id)
    outbox_b = store.list_outbox_bulletins(op.id, node_id=node_b.id)

    assert len(outbox_a) == 1
    assert outbox_a[0].node_id == node_a.id
    assert len(outbox_b) == 1
    assert outbox_b[0].node_id == node_b.id


def test_list_outbox_bulletins_sent_excluded(db_with_data):
    store, op, node_a, node_b = db_with_data
    bul = store.save_bulletin(_make_queued_bulletin(op.id, node_a.id))
    store.mark_bulletin_sent(bul.id)
    assert store.list_outbox_bulletins(op.id, node_id=node_a.id) == []


# --- message_target_nodes table in schema ---

def test_message_target_nodes_table_exists(db):
    tables = db.table_names()
    assert "message_target_nodes" in tables
