import pytest
import tempfile
import os
from open_packet.store.database import Database
from open_packet.store.models import Operator, Node, Message, Bulletin


@pytest.fixture
def db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    database = Database(f.name)
    database.initialize()
    yield database
    database.close()
    os.unlink(f.name)


def test_database_creates_tables(db):
    tables = db.table_names()
    assert "operators" in tables
    assert "nodes" in tables
    assert "messages" in tables
    assert "bulletins" in tables


def test_insert_and_fetch_operator(db):
    op = Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True)
    inserted = db.insert_operator(op)
    assert inserted.id is not None
    fetched = db.get_operator(inserted.id)
    assert fetched.callsign == "KD9ABC"
    assert fetched.ssid == 1
    assert fetched.label == "home"
    assert fetched.is_default is True


def test_insert_and_fetch_node(db):
    node = Node(label="Home BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True)
    inserted = db.insert_node(node)
    assert inserted.id is not None
    fetched = db.get_node(inserted.id)
    assert fetched.callsign == "W0BPQ"
    assert fetched.node_type == "bpq"
    assert fetched.is_default is True


def test_get_default_operator(db):
    db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    op = db.get_default_operator()
    assert op is not None
    assert op.callsign == "KD9ABC"


def test_get_default_node(db):
    db.insert_node(Node(label="Home BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    node = db.get_default_node()
    assert node is not None
    assert node.callsign == "W0BPQ"


from open_packet.store.store import Store
from datetime import datetime, timezone


@pytest.fixture
def store(db):
    s = Store(db)
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    node = db.insert_node(Node(label="Home BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    return s, op, node


def test_store_and_list_messages(store):
    s, op, node = store
    msg = Message(
        operator_id=op.id, node_id=node.id, bbs_id="001",
        from_call="W0TEST", to_call="KD9ABC",
        subject="Hello", body="Test body",
        timestamp=datetime.now(timezone.utc),
    )
    s.save_message(msg)
    messages = s.list_messages(operator_id=op.id)
    assert len(messages) == 1
    assert messages[0].subject == "Hello"
    assert messages[0].read is False


def test_mark_message_read(store):
    s, op, node = store
    msg = Message(
        operator_id=op.id, node_id=node.id, bbs_id="002",
        from_call="W0TEST", to_call="KD9ABC",
        subject="Read me", body="Body",
        timestamp=datetime.now(timezone.utc),
    )
    saved = s.save_message(msg)
    s.mark_message_read(saved.id)
    fetched = s.get_message(saved.id)
    assert fetched.read is True


def test_soft_delete_message(store):
    s, op, node = store
    msg = Message(
        operator_id=op.id, node_id=node.id, bbs_id="003",
        from_call="W0TEST", to_call="KD9ABC",
        subject="Delete me", body="Body",
        timestamp=datetime.now(timezone.utc),
    )
    saved = s.save_message(msg)
    s.delete_message(saved.id)
    messages = s.list_messages(operator_id=op.id)
    # Deleted messages excluded from list
    assert all(m.id != saved.id for m in messages)


def test_store_and_list_bulletins(store):
    s, op, node = store
    bul = Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="B001",
        category="WX", from_call="W0WX",
        subject="Weather alert", body="Thunderstorms",
        timestamp=datetime.now(timezone.utc),
    )
    s.save_bulletin(bul)
    bulletins = s.list_bulletins(operator_id=op.id, category="WX")
    assert len(bulletins) == 1
    assert bulletins[0].subject == "Weather alert"


def test_message_not_duplicated(store):
    s, op, node = store
    msg = Message(
        operator_id=op.id, node_id=node.id, bbs_id="004",
        from_call="W0TEST", to_call="KD9ABC",
        subject="Unique", body="Body",
        timestamp=datetime.now(timezone.utc),
    )
    s.save_message(msg)
    s.save_message(msg)  # same bbs_id + node_id — should not duplicate
    messages = s.list_messages(operator_id=op.id)
    assert len(messages) == 1
