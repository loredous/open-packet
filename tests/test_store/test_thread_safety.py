"""Store operations must be atomic: other threads never observe, and later
commits never persist, a half-applied multi-statement operation.

The Engine thread and the TUI thread share one Database/Store (one sqlite3
connection), so these guarantees have to come from the store layer itself.
"""
import sqlite3
import threading

import pytest

from open_packet.store.database import Database
from open_packet.store.models import Node, NodeGroup
from open_packet.store.store import Store


class _PausingConnection:
    """Delegates to a real sqlite3 connection, but pauses (or fails) right
    before executing the first statement containing ``trigger_sql``.

    Pausing happens *before* delegating, so the real connection's own mutex is
    not held while paused — only whatever locking the store layer provides.
    """

    def __init__(self, real: sqlite3.Connection, trigger_sql: str, fail: bool = False):
        self._real = real
        self._trigger_sql = trigger_sql
        self._fail = fail
        self._fired = False
        self.paused = threading.Event()
        self.resume = threading.Event()

    def execute(self, sql, *args, **kwargs):
        if not self._fired and self._trigger_sql in sql:
            self._fired = True
            if self._fail:
                raise sqlite3.IntegrityError("simulated failure mid-operation")
            self.paused.set()
            self.resume.wait(timeout=5)
        return self._real.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def db(db_path):
    d = Database(db_path)
    d.initialize()
    yield d
    d.close()


@pytest.fixture
def group(db):
    n1 = db.insert_node(Node(label="BBS1", callsign="W0AA", ssid=1, node_type="bpq"))
    n2 = db.insert_node(Node(label="BBS2", callsign="W0BB", ssid=2, node_type="bpq"))
    return db.insert_node_group(NodeGroup(name="Run", node_ids=[n1.id, n2.id]))


def test_reader_thread_never_sees_half_applied_group_update(db, group):
    real = db._conn
    proxy = _PausingConnection(real, "INSERT INTO node_group_members")
    db._conn = proxy
    try:
        writer = threading.Thread(target=db.update_node_group, args=(group,))
        writer.start()
        assert proxy.paused.wait(timeout=5), "writer never reached the pause point"

        # Writer is now mid-operation: memberships deleted, not yet re-inserted.
        seen: list = []
        reader = threading.Thread(target=lambda: seen.append(Store(db).get_node_group(group.id)))
        reader.start()
        reader.join(timeout=0.3)
        proxy.resume.set()
        writer.join(timeout=5)
        reader.join(timeout=5)
    finally:
        proxy.resume.set()
        db._conn = real

    assert seen, "reader did not complete"
    assert seen[0].node_ids == group.node_ids


def test_failed_operation_is_not_persisted_by_a_later_commit(db, db_path, group):
    real = db._conn
    db._conn = _PausingConnection(real, "INSERT INTO node_group_members", fail=True)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            db.update_node_group(NodeGroup(id=group.id, name="Renamed", node_ids=group.node_ids))
    finally:
        db._conn = real

    # An unrelated write commits on the shared connection.
    db.insert_node(Node(label="BBS3", callsign="W0CC", ssid=3, node_type="bpq"))

    # Check on-disk state through an independent connection.
    other = Database(db_path)
    other.initialize()
    try:
        persisted = other.get_node_group(group.id)
    finally:
        other.close()
    assert persisted.name == "Run"
    assert persisted.node_ids == group.node_ids
