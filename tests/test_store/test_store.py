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
from open_packet.store.exporter import export_messages, export_bulletins
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


def test_export_messages_writes_files(store, tmp_path):
    s, op, node = store
    msg = Message(
        operator_id=op.id, node_id=node.id, bbs_id="005",
        from_call="W0TEST", to_call="KD9ABC",
        subject="Export test", body="Export body",
        timestamp=datetime(2026, 3, 22, 12, 0, 0, tzinfo=timezone.utc),
    )
    saved = s.save_message(msg)
    export_messages([saved], base_path=str(tmp_path))
    inbox_dir = tmp_path / "inbox" / "KD9ABC"
    files = list(inbox_dir.iterdir())
    assert len(files) == 1
    content = files[0].read_text()
    assert "Export test" in content
    assert "Export body" in content


def test_export_bulletins_writes_files(store, tmp_path):
    s, op, node = store
    bul = Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="B005",
        category="WX", from_call="W0WX",
        subject="Weather", body="Sunny",
        timestamp=datetime(2026, 3, 22, 12, 0, 0, tzinfo=timezone.utc),
    )
    saved = s.save_bulletin(bul)
    export_bulletins([saved], base_path=str(tmp_path))
    wx_dir = tmp_path / "bulletins" / "WX"
    files = list(wx_dir.iterdir())
    assert len(files) == 1
    content = files[0].read_text()
    assert "Weather" in content


def test_export_sent_messages(store, tmp_path):
    s, op, node = store
    msg = Message(
        operator_id=op.id, node_id=node.id, bbs_id="006",
        from_call="KD9ABC", to_call="W0TEST",
        subject="Outbound", body="Sent body",
        timestamp=datetime(2026, 3, 22, 12, 0, 0, tzinfo=timezone.utc),
        sent=True,
    )
    saved = s.save_message(msg)
    export_messages([saved], base_path=str(tmp_path))
    sent_dir = tmp_path / "sent"
    files = list(sent_dir.iterdir())
    assert len(files) == 1


def test_message_model_queued_defaults_false():
    from datetime import datetime, timezone
    msg = Message(
        operator_id=1, node_id=1, bbs_id="x",
        from_call="W0A", to_call="W0B",
        subject="s", body="b",
        timestamp=datetime.now(timezone.utc),
    )
    assert msg.queued is False


def test_database_schema_has_queued_column(db):
    cols = [row[1] for row in db._conn.execute("PRAGMA table_info(messages)").fetchall()]
    assert "queued" in cols


def test_row_to_message_preserves_queued_flag(store):
    s, op, node = store
    msg = Message(
        operator_id=op.id, node_id=node.id, bbs_id="",
        from_call="KD9ABC-1", to_call="W0TEST",
        subject="Queued", body="Body",
        timestamp=datetime.now(timezone.utc),
        queued=True,
    )
    saved = s.save_message(msg)
    fetched = s.get_message(saved.id)
    assert fetched.queued is True


def test_multiple_queued_messages_all_saved(store):
    """Each compose action must produce its own row (dedup bypass for queued=True)."""
    s, op, node = store
    for i in range(3):
        s.save_message(Message(
            operator_id=op.id, node_id=node.id, bbs_id="",
            from_call="KD9ABC-1", to_call="W0TEST",
            subject=f"Msg {i}", body="Body",
            timestamp=datetime.now(timezone.utc),
            queued=True,
        ))
    outbox = s.list_outbox(op.id)
    assert len(outbox) == 3


def test_received_messages_still_deduplicated(store):
    s, op, node = store
    msg = Message(
        operator_id=op.id, node_id=node.id, bbs_id="007",
        from_call="W0TEST", to_call="KD9ABC",
        subject="Dupe", body="Body",
        timestamp=datetime.now(timezone.utc),
    )
    s.save_message(msg)
    s.save_message(msg)
    messages = s.list_messages(op.id)
    assert len([m for m in messages if m.bbs_id == "007"]) == 1


def test_list_outbox_excludes_sent_and_deleted(store):
    s, op, node = store
    # queued + sent (transmitted) — should NOT appear
    transmitted = s.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="",
        from_call="KD9ABC-1", to_call="W0TEST",
        subject="Sent", body="Body",
        timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    s.mark_message_sent(transmitted.id)
    # queued + deleted — should NOT appear
    deleted = s.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="",
        from_call="KD9ABC-1", to_call="W0TEST",
        subject="Deleted", body="Body",
        timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    s.delete_message(deleted.id)
    # queued + pending — SHOULD appear
    s.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="",
        from_call="KD9ABC-1", to_call="W0TEST",
        subject="Pending", body="Body",
        timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    outbox = s.list_outbox(op.id)
    assert len(outbox) == 1
    assert outbox[0].subject == "Pending"


def test_count_folder_stats_empty_db(store):
    s, op, node = store
    stats = s.count_folder_stats(op.id)
    assert stats["Inbox"] == (0, 0)
    assert stats["Sent"] == (0,)
    assert stats["Outbox"] == (0,)


def test_count_folder_stats_counts_correctly(store):
    s, op, node = store
    now = datetime.now(timezone.utc)
    # 2 received, 1 unread
    m1 = s.save_message(Message(operator_id=op.id, node_id=node.id, bbs_id="A1",
        from_call="W0A", to_call="KD9ABC", subject="s", body="b", timestamp=now))
    m2 = s.save_message(Message(operator_id=op.id, node_id=node.id, bbs_id="A2",
        from_call="W0A", to_call="KD9ABC", subject="s", body="b", timestamp=now))
    s.mark_message_read(m1.id)
    # 1 queued (outbox)
    s.save_message(Message(operator_id=op.id, node_id=node.id, bbs_id="",
        from_call="KD9ABC-1", to_call="W0A", subject="s", body="b",
        timestamp=now, queued=True))
    # 1 transmitted (queued+sent → appears in Sent)
    tx = s.save_message(Message(operator_id=op.id, node_id=node.id, bbs_id="",
        from_call="KD9ABC-1", to_call="W0B", subject="s", body="b",
        timestamp=now, queued=True))
    s.mark_message_sent(tx.id)

    stats = s.count_folder_stats(op.id)
    assert stats["Inbox"] == (2, 1)    # 2 total, 1 unread
    assert stats["Outbox"] == (1,)     # 1 pending
    assert stats["Sent"] == (1,)       # 1 transmitted


def test_migration_adds_queued_column_to_existing_db():
    """Simulates an old DB that lacks the queued column."""
    import tempfile, os, sqlite3 as _sqlite3
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    # Create old-style schema without queued
    old_conn = _sqlite3.connect(f.name)
    old_conn.executescript("""
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator_id INTEGER NOT NULL,
            node_id INTEGER NOT NULL,
            bbs_id TEXT NOT NULL,
            from_call TEXT NOT NULL,
            to_call TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            read INTEGER NOT NULL DEFAULT 0,
            sent INTEGER NOT NULL DEFAULT 0,
            deleted INTEGER NOT NULL DEFAULT 0,
            synced_at TEXT
        );
        CREATE TABLE operators (id INTEGER PRIMARY KEY, callsign TEXT, ssid INTEGER, label TEXT, is_default INTEGER, created_at TEXT);
        CREATE TABLE nodes (id INTEGER PRIMARY KEY, label TEXT, callsign TEXT, ssid INTEGER, node_type TEXT, is_default INTEGER, created_at TEXT);
        CREATE TABLE bulletins (id INTEGER PRIMARY KEY, operator_id INTEGER, node_id INTEGER, bbs_id TEXT, category TEXT, from_call TEXT, subject TEXT, body TEXT, timestamp TEXT, read INTEGER, synced_at TEXT);
    """)
    old_conn.close()
    # Now open with Database — should migrate transparently
    from open_packet.store.database import Database
    db2 = Database(f.name)
    db2.initialize()
    cols = [row[1] for row in db2._conn.execute("PRAGMA table_info(messages)").fetchall()]
    db2.close()
    os.unlink(f.name)
    assert "queued" in cols


def test_migration_adds_queued_sent_columns_to_bulletins():
    """DB.initialize() on an existing bulletins table adds queued and sent columns."""
    import sqlite3
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    try:
        # Create old schema without queued/sent
        conn = sqlite3.connect(f.name)
        conn.execute("""CREATE TABLE bulletins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator_id INTEGER, node_id INTEGER, bbs_id TEXT,
            category TEXT, from_call TEXT, subject TEXT, body TEXT,
            timestamp TEXT, read INTEGER NOT NULL DEFAULT 0,
            synced_at TEXT
        )""")
        conn.commit()
        conn.close()

        db = Database(f.name)
        db.initialize()
        conn2 = sqlite3.connect(f.name)
        cols = [r[1] for r in conn2.execute("PRAGMA table_info(bulletins)").fetchall()]
        conn2.close()
        db.close()
        assert "queued" in cols
        assert "sent" in cols
    finally:
        os.unlink(f.name)
