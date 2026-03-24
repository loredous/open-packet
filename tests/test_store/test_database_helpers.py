import pytest
from open_packet.store.database import Database
from open_packet.store.models import Operator, Node
from open_packet.store.models import Interface


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "test.db"))
    d.initialize()
    yield d
    d.close()


def test_clear_default_operator_clears_existing(db):
    db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="a", is_default=True))
    db.insert_operator(Operator(callsign="W0TEST", ssid=0, label="b", is_default=True))
    db.clear_default_operator()
    assert db.get_default_operator() is None


def test_clear_default_operator_noop_when_none_set(db):
    # Should not raise when no default exists
    db.clear_default_operator()
    assert db.get_default_operator() is None


def test_clear_default_node_clears_existing(db):
    db.insert_node(Node(label="BBS1", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    db.insert_node(Node(label="BBS2", callsign="W0FOO", ssid=0, node_type="bpq", is_default=True))
    db.clear_default_node()
    assert db.get_default_node() is None


def test_clear_default_node_noop_when_none_set(db):
    db.clear_default_node()
    assert db.get_default_node() is None


def test_list_operators_returns_all(db):
    db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=True))
    db.insert_operator(Operator(callsign="W0TEST", ssid=1, label="car", is_default=False))
    ops = db.list_operators()
    assert len(ops) == 2
    assert ops[0].callsign == "KD9ABC"
    assert ops[1].callsign == "W0TEST"


def test_list_operators_empty(db):
    assert db.list_operators() == []


def test_list_nodes_returns_all(db):
    db.insert_node(Node(label="BBS1", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    db.insert_node(Node(label="BBS2", callsign="W0FOO", ssid=0, node_type="bpq", is_default=False))
    nodes = db.list_nodes()
    assert len(nodes) == 2
    assert nodes[0].label == "BBS1"


def test_update_operator(db):
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=True))
    op.callsign = "W0NEW"
    op.label = "updated"
    db.update_operator(op)
    refreshed = db.get_operator(op.id)
    assert refreshed.callsign == "W0NEW"
    assert refreshed.label == "updated"


def test_update_node(db):
    node = db.insert_node(Node(label="BBS1", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    node.label = "New BBS"
    node.callsign = "W0NEW"
    db.update_node(node)
    refreshed = db.get_node(node.id)
    assert refreshed.label == "New BBS"
    assert refreshed.callsign == "W0NEW"


def test_update_operator_changes_default(db):
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=False))
    db.clear_default_operator()
    op.is_default = True
    db.update_operator(op)
    assert db.get_default_operator().id == op.id


def test_insert_and_get_interface(db):
    iface = db.insert_interface(Interface(
        label="Home TNC", iface_type="kiss_tcp", host="localhost", port=8910
    ))
    assert iface.id is not None
    fetched = db.get_interface(iface.id)
    assert fetched.label == "Home TNC"
    assert fetched.iface_type == "kiss_tcp"
    assert fetched.host == "localhost"
    assert fetched.port == 8910


def test_list_interfaces(db):
    db.insert_interface(Interface(label="TNC1", iface_type="kiss_tcp", host="localhost", port=8910))
    db.insert_interface(Interface(label="BBS", iface_type="telnet", host="192.168.1.1", port=8023,
                                  username="K0JLB", password="pw"))
    ifaces = db.list_interfaces()
    assert len(ifaces) == 2
    assert ifaces[0].label == "TNC1"
    assert ifaces[1].username == "K0JLB"


def test_update_interface(db):
    iface = db.insert_interface(Interface(label="Old", iface_type="kiss_tcp", host="localhost", port=8910))
    iface.label = "New"
    iface.port = 9000
    db.update_interface(iface)
    fetched = db.get_interface(iface.id)
    assert fetched.label == "New"
    assert fetched.port == 9000


def test_delete_interface(db):
    iface = db.insert_interface(Interface(label="Temp", iface_type="kiss_serial", device="/dev/ttyUSB0", baud=9600))
    db.delete_interface(iface.id)
    assert db.get_interface(iface.id) is None


def test_interface_telnet_fields_round_trip(db):
    iface = db.insert_interface(Interface(
        label="Telnet BBS", iface_type="telnet",
        host="192.168.1.209", port=8023, username="K0JLB", password="secret"
    ))
    fetched = db.get_interface(iface.id)
    assert fetched.host == "192.168.1.209"
    assert fetched.port == 8023
    assert fetched.username == "K0JLB"
    assert fetched.password == "secret"
    assert fetched.device is None
    assert fetched.baud is None


def test_interface_serial_fields_round_trip(db):
    iface = db.insert_interface(Interface(
        label="Serial TNC", iface_type="kiss_serial", device="/dev/ttyUSB0", baud=9600
    ))
    fetched = db.get_interface(iface.id)
    assert fetched.device == "/dev/ttyUSB0"
    assert fetched.baud == 9600
    assert fetched.host is None
    assert fetched.port is None


def test_node_interface_id_round_trip(db):
    iface = db.insert_interface(Interface(label="TNC", iface_type="kiss_tcp", host="localhost", port=8910))
    node = db.insert_node(Node(
        label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
        is_default=True, interface_id=iface.id
    ))
    fetched = db.get_node(node.id)
    assert fetched.interface_id == iface.id


def test_node_interface_id_none_by_default(db):
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    fetched = db.get_node(node.id)
    assert fetched.interface_id is None


def test_interface_id_migration_on_db_with_interfaces_table(tmp_path):
    """Migration works when interfaces table exists but nodes.interface_id is missing."""
    import sqlite3
    db_path = str(tmp_path / "partial.db")
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE interfaces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            iface_type TEXT NOT NULL,
            host TEXT, port INTEGER, username TEXT, password TEXT, device TEXT, baud INTEGER
        );
        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            callsign TEXT NOT NULL,
            ssid INTEGER NOT NULL DEFAULT 0,
            node_type TEXT NOT NULL,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()

    d = Database(db_path)
    d.initialize()  # should not raise
    conn2 = sqlite3.connect(db_path)
    cols = [r[1] for r in conn2.execute("PRAGMA table_info(nodes)").fetchall()]
    assert "interface_id" in cols
    conn2.close()
    d.close()


def test_delete_interface_with_linked_node_raises(db):
    """Deleting an interface that a node references raises ValueError."""
    iface = db.insert_interface(Interface(label="TNC", iface_type="kiss_tcp", host="localhost", port=8910))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    with pytest.raises(ValueError, match="referenced by one or more nodes"):
        db.delete_interface(iface.id)


def test_interface_id_migration_on_existing_db(tmp_path):
    """Calling initialize() on a pre-existing DB (without interface_id column) adds it cleanly."""
    import sqlite3
    db_path = str(tmp_path / "old.db")
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            callsign TEXT NOT NULL,
            ssid INTEGER NOT NULL DEFAULT 0,
            node_type TEXT NOT NULL,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()

    d = Database(db_path)
    d.initialize()  # should not raise
    conn2 = sqlite3.connect(db_path)
    conn2.row_factory = sqlite3.Row
    cols = [r["name"] for r in conn2.execute("PRAGMA table_info(nodes)").fetchall()]
    assert "interface_id" in cols
    tables = [r[0] for r in conn2.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "interfaces" in tables
    conn2.close()
    d.close()
