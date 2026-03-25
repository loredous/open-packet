# tests/test_ui/test_tui.py
import pytest
from open_packet.ui.tui.app import OpenPacketApp
from open_packet.config.config import AppConfig, StoreConfig, UIConfig


@pytest.fixture
def app_config(tmp_path):
    return AppConfig(
        store=StoreConfig(
            db_path=str(tmp_path / "test.db"),
            export_path=str(tmp_path / "export"),
        ),
        ui=UIConfig(),
    )


def test_app_store_has_outbox_methods():
    """Smoke-check: Store has the methods app.py will call for Outbox and folder counts."""
    from open_packet.store.store import Store
    assert hasattr(Store, "list_outbox"), "Store.list_outbox missing — Task 2 not complete"
    assert hasattr(Store, "count_folder_stats"), "Store.count_folder_stats missing — Task 2 not complete"


@pytest.mark.asyncio
async def test_app_mounts(app_config, tmp_path):
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node, Interface

    # Pre-populate DB so no setup screen is pushed during test
    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    iface = db.insert_interface(Interface(
        label="Test", iface_type="kiss_tcp", host="localhost", port=8910
    ))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        assert app.query_one("StatusBar") is not None
        assert app.query_one("FolderTree") is not None
        assert app.query_one("MessageList") is not None
        assert app.query_one("MessageBody") is not None


@pytest.mark.asyncio
async def test_console_toggle(app_config, tmp_path):
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node, Interface

    # Pre-populate DB so no setup screen is pushed during test
    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    iface = db.insert_interface(Interface(
        label="Test", iface_type="kiss_tcp", host="localhost", port=8910
    ))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        # Console starts hidden by default
        console = app.query_one("ConsolePanel")
        assert not console.display
        # Backtick toggles console
        await pilot.press("`")
        assert console.display
        await pilot.press("`")
        assert not console.display


@pytest.mark.asyncio
async def test_folder_selection_loads_inbox(app_config, tmp_path):
    """Selecting Inbox in the folder tree populates the message list."""
    from open_packet.store.database import Database
    from open_packet.store.store import Store
    from open_packet.store.models import Operator, Node, Message
    from datetime import datetime, timezone
    from open_packet.ui.tui.app import OpenPacketApp

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    node = db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq", is_default=True))
    store = Store(db)
    from open_packet.store.models import Message
    from datetime import datetime, timezone
    store.save_message(Message(
        operator_id=op.id, node_id=node.id, bbs_id="001",
        from_call="W0TEST", to_call="KD9ABC", subject="Test",
        body="Body", timestamp=datetime.now(timezone.utc),
    ))

    app_config.store.db_path = str(tmp_path / "test.db")
    app = OpenPacketApp(config=app_config)
    # Inject store/operator directly to bypass engine init
    app._store = store
    app._active_operator = op
    app._active_folder = "Inbox"
    app._active_category = ""

    async with app.run_test() as pilot:
        app._refresh_message_list()
        await pilot.pause()
        msg_list = app.query_one("MessageList")
        assert msg_list.row_count == 1


@pytest.mark.asyncio
async def test_update_counts_inbox_labels(app_config, tmp_path):
    """update_counts() sets correct Inbox label variants on the mounted FolderTree."""
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node, Interface

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    iface = db.insert_interface(Interface(
        label="Test", iface_type="kiss_tcp", host="localhost", port=8910
    ))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        tree = app.query_one("FolderTree")

        # No messages → plain labels
        tree.update_counts({"Inbox": (0, 0), "Sent": (0,), "Outbox": (0,)})
        await pilot.pause()
        assert str(tree._inbox_node.label) == "Inbox"
        assert str(tree._sent_node.label) == "Sent"
        assert str(tree._outbox_node.label) == "Outbox"

        # Inbox with messages, no unread
        tree.update_counts({"Inbox": (5, 0), "Sent": (2,), "Outbox": (0,)})
        await pilot.pause()
        assert str(tree._inbox_node.label) == "Inbox (5)"
        assert str(tree._sent_node.label) == "Sent (2)"

        # Inbox with unread
        tree.update_counts({"Inbox": (10, 3), "Sent": (0,), "Outbox": (0,)})
        await pilot.pause()
        inbox_label = tree._inbox_node.label
        assert "10" in str(inbox_label)
        assert "3" in str(inbox_label)

        # Outbox with pending messages → gold background
        from rich.text import Text
        tree.update_counts({"Inbox": (0, 0), "Sent": (0,), "Outbox": (4,)})
        await pilot.pause()
        outbox_label = tree._outbox_node.label
        assert isinstance(outbox_label, Text)
        assert "4" in outbox_label.plain
        assert outbox_label.style.bgcolor is not None


@pytest.mark.asyncio
async def test_update_counts_outbox_cleared(app_config, tmp_path):
    """When Outbox count drops to 0, label returns to plain 'Outbox' with no background."""
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node, Interface
    from rich.text import Text

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    iface = db.insert_interface(Interface(
        label="Test", iface_type="kiss_tcp", host="localhost", port=8910
    ))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        tree = app.query_one("FolderTree")
        tree.update_counts({"Inbox": (0, 0), "Sent": (0,), "Outbox": (2,)})
        await pilot.pause()
        tree.update_counts({"Inbox": (0, 0), "Sent": (0,), "Outbox": (0,)})
        await pilot.pause()
        label = tree._outbox_node.label
        assert str(label) == "Outbox"
        # The cleared outbox uses Text("Outbox", style=Style()) so .style is always
        # a Style object (not a bare string), making .bgcolor accessible unconditionally.
        assert isinstance(label, Text)
        assert label.style.bgcolor is None


def _label_text(label) -> str:
    """Return the text content of a Label, compatible across Textual versions."""
    if hasattr(label, "renderable"):
        return str(label.renderable)
    return str(label.content)


@pytest.mark.asyncio
async def test_status_bar_shows_operator_node_interface(app_config, tmp_path):
    """After mounting with full config, status bar right section shows callsign, node, interface."""
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node, Interface

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="W1AW", ssid=0, label="home", is_default=True))
    iface = db.insert_interface(Interface(
        label="Home TNC", iface_type="kiss_tcp", host="localhost", port=8910
    ))
    db.insert_node(Node(label="Home BBS", callsign="W0BPQ", ssid=0, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        await pilot.pause()
        right = app.query_one("#status_right")
        text = _label_text(right)
        assert "W1AW" in text       # ssid=0, no suffix
        assert "Home BBS" in text
        assert "Home TNC" in text


@pytest.mark.asyncio
async def test_status_bar_shows_ssid_when_nonzero(app_config, tmp_path):
    """Operator with ssid>0 is shown as callsign-ssid."""
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node, Interface

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="W1AW", ssid=3, label="mobile", is_default=True))
    iface = db.insert_interface(Interface(
        label="Mobile TNC", iface_type="kiss_tcp", host="localhost", port=8910
    ))
    db.insert_node(Node(label="Local BBS", callsign="W0BPQ", ssid=0, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        await pilot.pause()
        right = app.query_one("#status_right")
        assert "W1AW-3" in _label_text(right)


@pytest.mark.asyncio
async def test_status_bar_right_empty_when_no_operator(app_config, tmp_path):
    """When no operator is configured, the right section of the status bar is empty."""
    # Don't insert any operator — DB is empty
    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        await pilot.pause()
        # The OperatorSetupScreen will be pushed, but we can still check the bar
        right = app.query_one("#status_right")
        assert _label_text(right) == ""
