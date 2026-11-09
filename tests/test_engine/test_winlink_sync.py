"""Engine._do_winlink_sync connection handling."""
import queue
from unittest.mock import MagicMock

import pytest

from open_packet.engine.engine import Engine
from open_packet.store.database import Database
from open_packet.store.models import Node, NodeHop, Operator
from open_packet.store.store import Store


@pytest.fixture
def store_and_op(tmp_path):
    db = Database(str(tmp_path / "wl.db"))
    db.initialize()
    op = db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    yield Store(db), op
    db.close()


def _engine(store, op, node_record, connection):
    return Engine(
        command_queue=queue.Queue(), event_queue=queue.Queue(), store=store,
        operator=op, node_record=node_record, connection=connection, node=MagicMock(),
    )


def test_failed_digipeated_connect_is_not_retried_direct(store_and_op):
    """If connecting via the configured digipeater path fails, the engine must
    not silently retry a direct (pathless) connection to the node."""
    store, op = store_and_op
    node_record = Node(
        id=1, label="RMS", callsign="W0RMS", ssid=10, node_type="bpq",
        has_bbs=False, has_winlink=True,
        path_strategy="digipeat", hop_path=[NodeHop(callsign="W0DIG", port=None)],
    )
    connection = MagicMock()
    connection.connect.side_effect = ConnectionError("link timeout")

    with pytest.raises(ConnectionError, match="link timeout"):
        _engine(store, op, node_record, connection)._do_winlink_sync()

    assert connection.connect.call_count == 1
    assert connection.connect.call_args.kwargs.get("via_path") == node_record.hop_path
