# tests/test_ui/test_tui.py
import pytest
from open_packet.ui.tui.app import OpenPacketApp
from open_packet.config.config import AppConfig, TCPConnectionConfig, StoreConfig, UIConfig


@pytest.fixture
def app_config(tmp_path):
    return AppConfig(
        connection=TCPConnectionConfig(type="kiss_tcp", host="localhost", port=8001),
        store=StoreConfig(
            db_path=str(tmp_path / "test.db"),
            export_path=str(tmp_path / "export"),
        ),
        ui=UIConfig(),
    )


@pytest.mark.asyncio
async def test_app_mounts(app_config):
    app = OpenPacketApp(config=app_config)
    async with app.run_test() as pilot:
        assert app.query_one("StatusBar") is not None
        assert app.query_one("FolderTree") is not None
        assert app.query_one("MessageList") is not None
        assert app.query_one("MessageBody") is not None


@pytest.mark.asyncio
async def test_console_toggle(app_config):
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
