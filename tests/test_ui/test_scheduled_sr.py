# tests/test_ui/test_scheduled_sr.py
import queue
import pytest
from open_packet.store.database import Database
from open_packet.store.models import Operator, Node, Interface
from open_packet.engine.commands import CheckMailCommand
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


def test_do_scheduled_sr_queues_command_when_engine_present():
    """_do_scheduled_sr puts a CheckMailCommand in the queue when engine is running."""
    app = OpenPacketApp(db_path=":memory:")
    app._cmd_queue = queue.Queue()
    app._engine = object()  # non-None sentinel

    app._do_scheduled_sr()

    assert not app._cmd_queue.empty()
    cmd = app._cmd_queue.get_nowait()
    assert isinstance(cmd, CheckMailCommand)


def test_do_scheduled_sr_does_nothing_without_engine():
    """_do_scheduled_sr is a no-op when no engine is running."""
    app = OpenPacketApp(db_path=":memory:")
    app._cmd_queue = queue.Queue()
    app._engine = None

    app._do_scheduled_sr()

    assert app._cmd_queue.empty()


@pytest.mark.asyncio
async def test_scheduled_sr_timer_starts_when_enabled(populated_db, tmp_path):
    db_path = str(tmp_path / "test.db")
    app = OpenPacketApp(db_path=db_path)

    async with app.run_test() as pilot:
        # Enable scheduled SR (30-minute interval)
        app._settings.scheduled_sr_enabled = True
        app._settings.scheduled_sr_interval = 30

        app._update_scheduled_sr()

        assert app._scheduled_sr_timer is not None


@pytest.mark.asyncio
async def test_scheduled_sr_timer_stops_when_disabled(populated_db, tmp_path):
    db_path = str(tmp_path / "test.db")
    app = OpenPacketApp(db_path=db_path)

    async with app.run_test() as pilot:
        # First enable, then disable
        app._settings.scheduled_sr_enabled = True
        app._settings.scheduled_sr_interval = 30
        app._update_scheduled_sr()
        assert app._scheduled_sr_timer is not None

        app._settings.scheduled_sr_enabled = False
        app._update_scheduled_sr()
        assert app._scheduled_sr_timer is None


@pytest.mark.asyncio
async def test_scheduled_sr_timer_none_by_default(populated_db, tmp_path):
    """When scheduled SR is disabled (default), timer is not created on mount."""
    db_path = str(tmp_path / "test.db")
    app = OpenPacketApp(db_path=db_path)

    async with app.run_test() as pilot:
        # Default setting is disabled
        assert app._settings is not None
        assert app._settings.scheduled_sr_enabled is False
        assert app._scheduled_sr_timer is None
