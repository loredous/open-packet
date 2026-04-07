import pytest
from open_packet.store.database import Database
from open_packet.store.models import Operator, Node, Interface


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "test.db"))
    d.initialize()
    yield d
    d.close()


def test_soft_delete_operator_hides_from_list(db):
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=False))
    db.soft_delete_operator(op.id)
    assert all(o.id != op.id for o in db.list_operators())


def test_soft_delete_operator_hides_from_get(db):
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=False))
    db.soft_delete_operator(op.id)
    assert db.get_operator(op.id) is None


def test_soft_delete_operator_clears_default(db):
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=True))
    db.soft_delete_operator(op.id)
    assert db.get_default_operator() is None


def test_soft_delete_node_hides_from_list(db):
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=False))
    db.soft_delete_node(node.id)
    assert all(n.id != node.id for n in db.list_nodes())


def test_soft_delete_node_hides_from_get(db):
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=False))
    db.soft_delete_node(node.id)
    assert db.get_node(node.id) is None


def test_soft_delete_node_clears_default(db):
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    db.soft_delete_node(node.id)
    assert db.get_default_node() is None


def test_soft_delete_interface_hides_from_list(db):
    iface = db.insert_interface(Interface(label="TNC", iface_type="kiss_tcp", host="localhost", port=8910))
    db.soft_delete_interface(iface.id)
    assert all(i.id != iface.id for i in db.list_interfaces())


def test_soft_delete_interface_hides_from_get(db):
    iface = db.insert_interface(Interface(label="TNC", iface_type="kiss_tcp", host="localhost", port=8910))
    db.soft_delete_interface(iface.id)
    assert db.get_interface(iface.id) is None


def test_soft_delete_interface_blocked_by_active_node(db):
    iface = db.insert_interface(Interface(label="TNC", iface_type="kiss_tcp", host="localhost", port=8910))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    with pytest.raises(ValueError, match="referenced by one or more nodes"):
        db.soft_delete_interface(iface.id)


def test_soft_delete_interface_allowed_when_node_also_deleted(db):
    iface = db.insert_interface(Interface(label="TNC", iface_type="kiss_tcp", host="localhost", port=8910))
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
                               is_default=True, interface_id=iface.id))
    db.soft_delete_node(node.id)
    db.soft_delete_interface(iface.id)  # should not raise
    assert db.get_interface(iface.id) is None


def test_count_operator_dependents(db):
    from open_packet.store.models import Message
    from datetime import datetime, timezone
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=True))
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    from open_packet.store.store import Store
    store = Store(db)
    store.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="001",
        from_call="W0TEST", to_call="KD9ABC", subject="Hello", body="Hi",
        timestamp=datetime.now(timezone.utc),
    ))
    messages, bulletins = db.count_operator_dependents(op.id)
    assert messages == 1
    assert bulletins == 0


def test_count_node_dependents(db):
    from open_packet.store.models import Message
    from datetime import datetime, timezone
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=True))
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    from open_packet.store.store import Store
    store = Store(db)
    store.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="001",
        from_call="W0TEST", to_call="KD9ABC", subject="Hello", body="Hi",
        timestamp=datetime.now(timezone.utc),
    ))
    messages, bulletins = db.count_node_dependents(node.id)
    assert messages == 1
    assert bulletins == 0
