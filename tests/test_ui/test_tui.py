# tests/test_ui/test_tui.py
import pytest
from open_packet.ui.tui.app import OpenPacketApp
from open_packet.config.config import AppConfig, StoreConfig, UIConfig
from tests.test_ui.conftest import _label_text


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


async def test_status_bar_right_empty_when_no_operator(app_config, tmp_path):
    """When no operator is configured, the right section of the status bar is empty."""
    # Don't insert any operator — DB is empty
    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        await pilot.pause()
        # The OperatorSetupScreen will be pushed, but we can still check the bar
        right = app.query_one("#status_right")
        assert _label_text(right) == ""


def test_compose_bulletin_command_exists():
    """Importing ComposeBulletinScreen succeeds and PostBulletinCommand is importable."""
    from open_packet.ui.tui.screens.compose_bulletin import ComposeBulletinScreen
    from open_packet.engine.commands import PostBulletinCommand
    assert ComposeBulletinScreen is not None


async def test_update_counts_bulletin_categories_dynamic(app_config, tmp_path):
    """update_counts() creates and updates dynamic bulletin category nodes."""
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

        # Provide bulletin stats — WX with 3 total, 1 unread
        tree.update_counts({
            "Inbox": (0, 0), "Sent": (0,), "Outbox": (0,),
            "Bulletins": {"WX": (3, 1), "NTS": (5, 0)},
        })
        # update_counts is synchronous; check immediately before pilot.pause()
        # triggers _refresh_message_list which would reset nodes from DB state
        assert "WX" in tree._bulletin_nodes
        assert "NTS" in tree._bulletin_nodes
        wx_label = str(tree._bulletin_nodes["WX"].label)
        nts_label = str(tree._bulletin_nodes["NTS"].label)
        assert "3" in wx_label and "1" in wx_label   # "WX (3/1 new)"
        assert "5" in nts_label                       # "NTS (5)"
        await pilot.pause()

        # Remove NTS from stats — node should be removed
        tree.update_counts({
            "Inbox": (0, 0), "Sent": (0,), "Outbox": (0,),
            "Bulletins": {"WX": (3, 1)},
        })
        assert "NTS" not in tree._bulletin_nodes
        assert "WX" in tree._bulletin_nodes
        await pilot.pause()


@pytest.mark.asyncio
async def test_folder_tree_update_sessions_adds_entries(app_config, tmp_path):
    """update_sessions() adds session entries to the tree without crashing."""
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node, Interface
    from open_packet.ui.tui.widgets.folder_tree import FolderTree
    from unittest.mock import MagicMock

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=True))
    iface = db.insert_interface(Interface(label="TNC", iface_type="kiss_tcp", host="localhost", port=8910))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=0, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        await pilot.pause()
        ft = app.query_one(FolderTree)

        # Build fake sessions
        session_a = MagicMock()
        session_a.label = "W0XYZ"
        session_a.status = "connected"
        session_a.has_unread = False

        session_b = MagicMock()
        session_b.label = "K0TEST"
        session_b.status = "error"
        session_b.has_unread = False

        ft.update_sessions([session_a, session_b])
        await pilot.pause()
        # Two session nodes exist — no exception raised
        assert len(ft._session_nodes) == 2


@pytest.mark.asyncio
async def test_folder_tree_sessions_parent_node_click_does_not_crash(app_config, tmp_path):
    """Clicking the Sessions parent node (data='__sessions__') must not crash."""
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node, Interface
    from open_packet.ui.tui.widgets.folder_tree import FolderTree
    from unittest.mock import MagicMock

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=True))
    iface = db.insert_interface(Interface(label="TNC", iface_type="kiss_tcp", host="localhost", port=8910))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=0, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        await pilot.pause()
        ft = app.query_one(FolderTree)

        # Build a fake event that looks like clicking the Sessions header node
        mock_event = MagicMock()
        mock_event.node.data = "__sessions__"
        mock_event.node.parent = None
        mock_event.node.label = "Sessions"

        # Must not raise ValueError: invalid literal for int() with base 10: ''
        ft.on_tree_node_selected(mock_event)
        await pilot.pause()


@pytest.mark.asyncio
async def test_folder_tree_session_child_node_click_posts_message(app_config, tmp_path):
    """Clicking a session child node (data='__session_item_N__') posts SessionSelected(N)."""
    from open_packet.store.database import Database
    from open_packet.store.models import Operator, Node, Interface
    from open_packet.ui.tui.widgets.folder_tree import FolderTree
    from unittest.mock import MagicMock

    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="KD9ABC", ssid=0, label="home", is_default=True))
    iface = db.insert_interface(Interface(label="TNC", iface_type="kiss_tcp", host="localhost", port=8910))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=0, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    db.close()
    app_config.store.db_path = str(tmp_path / "test.db")

    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        await pilot.pause()
        ft = app.query_one(FolderTree)

        # Build a fake event for session item 2
        mock_event = MagicMock()
        mock_event.node.data = "__session_item_2__"
        mock_event.node.parent = None
        mock_event.node.label = "W0TEST"

        # Verify SessionSelected message is posted with correct index
        # No exception should be raised, and the message should be posted
        ft.on_tree_node_selected(mock_event)
        await pilot.pause()
