import pytest
from open_packet.store.database import Database
from open_packet.store.models import Node, NodeGroup


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "test.db"))
    d.initialize()
    yield d
    d.close()


@pytest.fixture
def two_nodes(db):
    n1 = db.insert_node(Node(label="BBS1", callsign="W0AA", ssid=1, node_type="bpq"))
    n2 = db.insert_node(Node(label="BBS2", callsign="W0BB", ssid=2, node_type="bpq"))
    return n1, n2


def test_insert_and_get_node_group(db, two_nodes):
    n1, n2 = two_nodes
    group = db.insert_node_group(NodeGroup(name="Morning Run", node_ids=[n1.id, n2.id]))
    assert group.id is not None
    fetched = db.get_node_group(group.id)
    assert fetched.name == "Morning Run"
    assert fetched.node_ids == [n1.id, n2.id]


def test_insert_preserves_node_order(db, two_nodes):
    n1, n2 = two_nodes
    # Insert in reverse order
    group = db.insert_node_group(NodeGroup(name="Reversed", node_ids=[n2.id, n1.id]))
    fetched = db.get_node_group(group.id)
    assert fetched.node_ids == [n2.id, n1.id]


def test_list_node_groups_empty(db):
    assert db.list_node_groups() == []


def test_list_node_groups_returns_all(db, two_nodes):
    n1, n2 = two_nodes
    db.insert_node_group(NodeGroup(name="Group A", node_ids=[n1.id]))
    db.insert_node_group(NodeGroup(name="Group B", node_ids=[n2.id, n1.id]))
    groups = db.list_node_groups()
    assert len(groups) == 2
    assert groups[0].name == "Group A"
    assert groups[1].name == "Group B"


def test_update_node_group_name(db, two_nodes):
    n1, n2 = two_nodes
    group = db.insert_node_group(NodeGroup(name="Old Name", node_ids=[n1.id]))
    group.name = "New Name"
    db.update_node_group(group)
    fetched = db.get_node_group(group.id)
    assert fetched.name == "New Name"
    assert fetched.node_ids == [n1.id]


def test_update_node_group_changes_members(db, two_nodes):
    n1, n2 = two_nodes
    group = db.insert_node_group(NodeGroup(name="Group", node_ids=[n1.id]))
    assert db.get_node_group(group.id).node_ids == [n1.id]

    group.node_ids = [n2.id, n1.id]
    db.update_node_group(group)
    fetched = db.get_node_group(group.id)
    assert fetched.node_ids == [n2.id, n1.id]


def test_soft_delete_node_group(db, two_nodes):
    n1, n2 = two_nodes
    group = db.insert_node_group(NodeGroup(name="Temp", node_ids=[n1.id, n2.id]))
    db.soft_delete_node_group(group.id)
    assert db.get_node_group(group.id) is None
    assert db.list_node_groups() == []


def test_soft_delete_does_not_affect_other_groups(db, two_nodes):
    n1, n2 = two_nodes
    g1 = db.insert_node_group(NodeGroup(name="Keep", node_ids=[n1.id]))
    g2 = db.insert_node_group(NodeGroup(name="Delete", node_ids=[n2.id]))
    db.soft_delete_node_group(g2.id)
    remaining = db.list_node_groups()
    assert len(remaining) == 1
    assert remaining[0].id == g1.id


def test_get_nonexistent_group_returns_none(db):
    assert db.get_node_group(9999) is None


def test_node_group_with_single_node(db, two_nodes):
    n1, _ = two_nodes
    group = db.insert_node_group(NodeGroup(name="Solo", node_ids=[n1.id]))
    fetched = db.get_node_group(group.id)
    assert fetched.node_ids == [n1.id]


def test_node_group_empty_node_ids(db):
    group = db.insert_node_group(NodeGroup(name="Empty", node_ids=[]))
    fetched = db.get_node_group(group.id)
    assert fetched.node_ids == []


def test_node_group_tables_created(db):
    tables = db.table_names()
    assert "node_groups" in tables
    assert "node_group_members" in tables
