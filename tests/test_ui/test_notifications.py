# tests/test_ui/test_notifications.py
"""Tests for the optional new-message notification feature (issue #11)."""
import pytest
from open_packet.engine.events import SyncCompleteEvent
from open_packet.store.database import Database
from open_packet.store.models import Operator, Node, Interface
from open_packet.ui.tui.app import OpenPacketApp


@pytest.fixture
def populated_db(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    iface = db.insert_interface(Interface(
        label="Test", iface_type="kiss_tcp", host="localhost", port=8910
    ))
    db.insert_node(Node(label="BBS", callsign="W0BPQ", ssid=1, node_type="bpq",
                        is_default=True, interface_id=iface.id))
    yield db
    db.close()


@pytest.mark.asyncio
async def test_notification_shown_when_enabled_and_new_messages(populated_db, tmp_path):
    """When notifications are enabled and new messages arrived, a notification is shown."""
    db_path = str(tmp_path / "test.db")
    app = OpenPacketApp(db_path=db_path)
    notifications = []

    async with app.run_test() as pilot:
        assert app._settings is not None
        app._settings.notifications_enabled = True

        app.notify = lambda msg, **kw: notifications.append(msg)

        event = SyncCompleteEvent(messages_retrieved=3, messages_sent=0, bulletins_retrieved=0)
        app._handle_event(event)

    assert any("3 new message(s)" in n for n in notifications), f"Expected notification, got: {notifications}"


@pytest.mark.asyncio
async def test_notification_shown_for_new_bulletins(populated_db, tmp_path):
    """A notification is shown when new bulletins are retrieved and notifications are on."""
    db_path = str(tmp_path / "test.db")
    app = OpenPacketApp(db_path=db_path)
    notifications = []

    async with app.run_test() as pilot:
        assert app._settings is not None
        app._settings.notifications_enabled = True

        app.notify = lambda msg, **kw: notifications.append(msg)

        event = SyncCompleteEvent(messages_retrieved=0, messages_sent=1, bulletins_retrieved=2)
        app._handle_event(event)

    assert any("2 new bulletin(s)" in n for n in notifications), f"Expected bulletin notification, got: {notifications}"


@pytest.mark.asyncio
async def test_no_notification_when_disabled(populated_db, tmp_path):
    """When notifications are disabled, no notification is shown after sync."""
    db_path = str(tmp_path / "test.db")
    app = OpenPacketApp(db_path=db_path)
    notifications = []

    async with app.run_test() as pilot:
        assert app._settings is not None
        app._settings.notifications_enabled = False

        app.notify = lambda msg, **kw: notifications.append(msg)

        event = SyncCompleteEvent(messages_retrieved=5, messages_sent=0, bulletins_retrieved=3)
        app._handle_event(event)

    assert len(notifications) == 0, f"Expected no notifications when disabled, got: {notifications}"


@pytest.mark.asyncio
async def test_no_notification_when_no_new_items(populated_db, tmp_path):
    """No notification is shown when sync completes with no new received items."""
    db_path = str(tmp_path / "test.db")
    app = OpenPacketApp(db_path=db_path)
    notifications = []

    async with app.run_test() as pilot:
        assert app._settings is not None
        app._settings.notifications_enabled = True

        app.notify = lambda msg, **kw: notifications.append(msg)

        # Only messages_sent > 0, no received items
        event = SyncCompleteEvent(messages_retrieved=0, messages_sent=2, bulletins_retrieved=0)
        app._handle_event(event)

    assert len(notifications) == 0, f"Expected no notification for sent-only sync, got: {notifications}"


@pytest.mark.asyncio
async def test_notification_shown_for_new_files(populated_db, tmp_path):
    """A notification is shown when new files are retrieved and notifications are on."""
    db_path = str(tmp_path / "test.db")
    app = OpenPacketApp(db_path=db_path)
    notifications = []

    async with app.run_test() as pilot:
        assert app._settings is not None
        app._settings.notifications_enabled = True

        app.notify = lambda msg, **kw: notifications.append(msg)

        event = SyncCompleteEvent(
            messages_retrieved=0, messages_sent=0, bulletins_retrieved=0, files_retrieved=4
        )
        app._handle_event(event)

    assert any("4 file(s)" in n for n in notifications), f"Expected file notification, got: {notifications}"
