import pytest
import tempfile
import os
from open_packet.store.database import Database
from open_packet.store.models import Operator, Node


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
