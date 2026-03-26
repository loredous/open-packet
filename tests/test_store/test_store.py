import pytest
import tempfile
import os
import json
from open_packet.store.database import Database
from open_packet.store.models import Operator, Node, Message, Bulletin, NodeHop


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


def test_save_bulletin_queued_skips_dedup(store):
    """Outgoing bulletins (queued=True) are always inserted fresh, not deduped."""
    s, op, node = store
    from datetime import datetime, timezone
    bul = Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="OUT-aabbccdd",
        category="WX", from_call="KD9ABC", subject="WX Report",
        body="Sunny.", timestamp=datetime.now(timezone.utc),
        queued=True, sent=False,
    )
    b1 = s.save_bulletin(bul)
    b2 = s.save_bulletin(bul)   # second save of same bbs_id
    assert b1.id != b2.id       # both inserted (no dedup)
    assert b1.queued is True
    assert b1.sent is False


def test_save_bulletin_received_deduplicates(store):
    """Received bulletins (queued=False) are deduped by bbs_id + node_id."""
    s, op, node = store
    from datetime import datetime, timezone
    bul = Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="BBS-001",
        category="NTS", from_call="W0TEST", subject="NTS msg",
        body="Test.", timestamp=datetime.now(timezone.utc),
    )
    b1 = s.save_bulletin(bul)
    b2 = s.save_bulletin(bul)
    assert b1.id == b2.id   # deduped


def test_row_to_bulletin_maps_queued_sent(store):
    """Bulletins retrieved from DB have queued/sent fields correctly mapped."""
    s, op, node = store
    from datetime import datetime, timezone
    bul = Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="OUT-xyz",
        category="WX", from_call="KD9ABC", subject="Test",
        body="Body.", timestamp=datetime.now(timezone.utc),
        queued=True, sent=False,
    )
    saved = s.save_bulletin(bul)
    fetched = s._get_bulletin(saved.id)
    assert fetched.queued is True
    assert fetched.sent is False


def test_list_bulletins_excludes_queued(store):
    """list_bulletins() does not return outgoing (queued) bulletins."""
    s, op, node = store
    from datetime import datetime, timezone
    s.save_bulletin(Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="BBS-001",
        category="WX", from_call="W0TEST", subject="Received",
        body="Body", timestamp=datetime.now(timezone.utc),
    ))
    s.save_bulletin(Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="OUT-aabb",
        category="WX", from_call="KD9ABC", subject="Outgoing",
        body="Body", timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    bulletins = s.list_bulletins(operator_id=op.id)
    assert len(bulletins) == 1
    assert bulletins[0].subject == "Received"


def test_list_outbox_includes_bulletins(store):
    """list_outbox() returns both queued messages and queued bulletins."""
    s, op, node = store
    from datetime import datetime, timezone
    from open_packet.store.models import Message
    s.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="",
        from_call="KD9ABC", to_call="W0TEST", subject="Msg",
        body="Body", timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    s.save_bulletin(Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="OUT-aabb",
        category="WX", from_call="KD9ABC", subject="Bul",
        body="Body", timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    outbox = s.list_outbox(operator_id=op.id)
    assert len(outbox) == 2
    subjects = {item.subject for item in outbox}
    assert "Msg" in subjects
    assert "Bul" in subjects


def test_list_outbox_messages_only(store):
    """list_outbox_messages() returns only Message objects."""
    s, op, node = store
    from datetime import datetime, timezone
    from open_packet.store.models import Message
    s.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="",
        from_call="KD9ABC", to_call="W0TEST", subject="Msg",
        body="Body", timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    s.save_bulletin(Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="OUT-aabb",
        category="WX", from_call="KD9ABC", subject="Bul",
        body="Body", timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    msgs = s.list_outbox_messages(operator_id=op.id)
    assert len(msgs) == 1
    assert isinstance(msgs[0], Message)
    assert msgs[0].subject == "Msg"


def test_list_outbox_bulletins_only(store):
    """list_outbox_bulletins() returns only Bulletin objects."""
    s, op, node = store
    from datetime import datetime, timezone
    from open_packet.store.models import Message
    s.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="",
        from_call="KD9ABC", to_call="W0TEST", subject="Msg",
        body="Body", timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    s.save_bulletin(Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="OUT-aabb",
        category="WX", from_call="KD9ABC", subject="Bul",
        body="Body", timestamp=datetime.now(timezone.utc),
        queued=True,
    ))
    buls = s.list_outbox_bulletins(operator_id=op.id)
    assert len(buls) == 1
    assert isinstance(buls[0], Bulletin)
    assert buls[0].subject == "Bul"


def test_count_folder_stats_includes_bulletin_counts(store):
    """count_folder_stats() returns per-category bulletin counts under 'Bulletins' key."""
    s, op, node = store
    from datetime import datetime, timezone
    s.save_bulletin(Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="B001",
        category="WX", from_call="W0TEST", subject="WX1",
        body="Body", timestamp=datetime.now(timezone.utc), read=True,
    ))
    s.save_bulletin(Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="B002",
        category="WX", from_call="W0TEST", subject="WX2",
        body="Body", timestamp=datetime.now(timezone.utc), read=False,
    ))
    s.save_bulletin(Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="B003",
        category="NTS", from_call="W0TEST", subject="NTS1",
        body="Body", timestamp=datetime.now(timezone.utc), read=False,
    ))
    s.save_bulletin(Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="OUT-xx",
        category="WX", from_call="KD9ABC", subject="Out",
        body="Body", timestamp=datetime.now(timezone.utc), queued=True,
    ))
    stats = s.count_folder_stats(op.id)
    assert "Bulletins" in stats
    wx = stats["Bulletins"]["WX"]
    nts = stats["Bulletins"]["NTS"]
    assert wx == (2, 1)
    assert nts == (1, 1)


def test_count_folder_stats_outbox_includes_queued_bulletins(store):
    """Outbox count includes both queued messages and queued bulletins."""
    s, op, node = store
    from datetime import datetime, timezone
    from open_packet.store.models import Message
    s.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="",
        from_call="KD9ABC", to_call="W0TEST", subject="Msg",
        body="Body", timestamp=datetime.now(timezone.utc), queued=True,
    ))
    s.save_bulletin(Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="OUT-aabb",
        category="WX", from_call="KD9ABC", subject="Bul",
        body="Body", timestamp=datetime.now(timezone.utc), queued=True,
    ))
    stats = s.count_folder_stats(op.id)
    assert stats["Outbox"] == (2,)


def test_mark_bulletin_sent(store):
    """mark_bulletin_sent() sets sent=1 for the bulletin."""
    s, op, node = store
    from datetime import datetime, timezone
    bul = Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="OUT-abc",
        category="WX", from_call="KD9ABC", subject="Test",
        body="Body", timestamp=datetime.now(timezone.utc),
        queued=True, sent=False,
    )
    saved = s.save_bulletin(bul)
    assert saved.sent is False
    s.mark_bulletin_sent(saved.id)
    fetched = s._get_bulletin(saved.id)
    assert fetched.sent is True


def test_bulletin_exists(store):
    """bulletin_exists() returns True only when bbs_id+node_id exists in DB."""
    s, op, node = store
    from datetime import datetime, timezone
    bul = Bulletin(
        operator_id=op.id, node_id=node.id, bbs_id="BBS-999",
        category="WX", from_call="W0TEST", subject="Test",
        body="Body", timestamp=datetime.now(timezone.utc),
    )
    assert s.bulletin_exists("BBS-999", node.id) is False
    s.save_bulletin(bul)
    assert s.bulletin_exists("BBS-999", node.id) is True
    assert s.bulletin_exists("BBS-999", node.id + 1) is False


def test_post_bulletin_command_exists():
    """PostBulletinCommand is a dataclass in the Command union."""
    from open_packet.engine.commands import PostBulletinCommand, Command
    cmd = PostBulletinCommand(category="WX", subject="Test", body="Body")
    assert cmd.category == "WX"
    assert cmd.subject == "Test"
    import typing
    args = typing.get_args(Command)
    assert PostBulletinCommand in args


def test_sync_complete_event_has_bulletins_retrieved():
    """SyncCompleteEvent accepts bulletins_retrieved with default 0."""
    from open_packet.engine.events import SyncCompleteEvent
    e1 = SyncCompleteEvent(messages_retrieved=3, messages_sent=1)
    assert e1.bulletins_retrieved == 0
    e2 = SyncCompleteEvent(messages_retrieved=2, messages_sent=0, bulletins_retrieved=5)
    assert e2.bulletins_retrieved == 5


def test_nodehop_defaults():
    h = NodeHop(callsign="W0RELAY-1")
    assert h.port is None


def test_nodehop_with_port():
    h = NodeHop(callsign="W0RELAY-1", port=3)
    assert h.port == 3


def test_node_has_hop_path():
    n = Node(label="x", callsign="W0BPQ", ssid=0, node_type="bpq")
    assert n.hop_path == []
    assert n.path_strategy == "path_route"
    assert n.auto_forward is False


def test_nodehop_json_roundtrip():
    hops = [NodeHop(callsign="W0RELAY-1", port=3), NodeHop(callsign="W0DIST")]
    serialized = json.dumps([{"callsign": h.callsign, "port": h.port} for h in hops])
    parsed = [NodeHop(**d) for d in json.loads(serialized)]
    assert parsed[0].callsign == "W0RELAY-1"
    assert parsed[0].port == 3
    assert parsed[1].port is None


def test_nodes_table_has_hop_path_column(db):
    cols = [r[1] for r in db._conn.execute("PRAGMA table_info(nodes)").fetchall()]
    assert "hop_path" in cols
    assert "path_strategy" in cols
    assert "auto_forward" in cols


def test_node_neighbors_table_exists(db):
    assert "node_neighbors" in db.table_names()


def test_node_neighbors_table_has_columns(db):
    cols = [r[1] for r in db._conn.execute("PRAGMA table_info(node_neighbors)").fetchall()]
    for c in ("id", "node_id", "callsign", "port", "first_seen", "last_seen"):
        assert c in cols


def test_node_hop_path_roundtrip(db):
    node = Node(
        label="Relay BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
        hop_path=[NodeHop("W0RELAY", port=3)],
        path_strategy="path_route",
        auto_forward=True,
    )
    inserted = db.insert_node(node)
    fetched = db.get_node(inserted.id)
    assert fetched.hop_path[0].callsign == "W0RELAY"
    assert fetched.hop_path[0].port == 3
    assert fetched.path_strategy == "path_route"
    assert fetched.auto_forward is True


def test_node_hop_path_defaults_on_existing_rows(db):
    # Simulate a node inserted without the new columns (migration scenario)
    db._conn.execute(
        "INSERT INTO nodes (label, callsign, ssid, node_type, is_default) VALUES (?, ?, ?, ?, ?)",
        ("Old Node", "W0OLD", 0, "bpq", 0),
    )
    db._conn.commit()
    nodes = db.list_nodes()
    old = next(n for n in nodes if n.callsign == "W0OLD")
    assert old.hop_path == []
    assert old.path_strategy == "path_route"
    assert old.auto_forward is False
