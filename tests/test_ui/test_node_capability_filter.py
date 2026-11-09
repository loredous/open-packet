"""Queued messages/bulletins may only target nodes that support their type.

A Winlink message queued to a node without Winlink (or a BBS message/bulletin
queued to a Winlink-only node) would never be sent.
"""
import queue

import pytest

from open_packet.engine.commands import PostBulletinCommand, SendMessageCommand
from open_packet.store.database import Database
from open_packet.store.models import Interface, Node, Operator
from open_packet.ui.tui.app import OpenPacketApp
from open_packet.ui.tui.screens.node_multi_picker import NodeMultiPickerScreen


def _make_db(tmp_path, nodes: list[dict]) -> tuple[str, dict[str, int]]:
    path = str(tmp_path / "caps.db")
    db = Database(path)
    db.initialize()
    db.insert_operator(Operator(callsign="KD9ABC", ssid=1, label="home", is_default=True))
    iface = db.insert_interface(Interface(label="T", iface_type="kiss_tcp", host="localhost", port=8910))
    ids = {}
    for i, spec in enumerate(nodes):
        n = db.insert_node(Node(
            label=spec["label"], callsign=f"W0N{i}", ssid=0, node_type="bpq",
            is_default=(i == 0), interface_id=iface.id,
            has_bbs=spec["bbs"], has_winlink=spec["winlink"],
        ))
        ids[spec["label"]] = n.id
    db.close()
    return path, ids


BBS_ONLY = {"label": "BBS", "bbs": True, "winlink": False}
RMS_ONLY = {"label": "RMS", "bbs": False, "winlink": True}
BOTH = {"label": "Both", "bbs": True, "winlink": True}


def _winlink_msg():
    return SendMessageCommand(to_call="W0XYZ", subject="s", body="b", message_type="winlink")


def _bbs_msg():
    return SendMessageCommand(to_call="W0XYZ", subject="s", body="b", message_type="bbs")


async def _queue_via_picker(app, pilot, cmd) -> queue.Queue:
    q: queue.Queue = queue.Queue()
    app._cmd_queue = q  # detach from the engine so we can observe what is queued
    app._pick_nodes_then(cmd)
    await pilot.pause()
    return q


@pytest.mark.parametrize("make_cmd, expected", [
    (_winlink_msg, "RMS"),
    (_bbs_msg, "BBS"),
    (lambda: PostBulletinCommand(category="WX", subject="s", body="b"), "BBS"),
])
async def test_command_auto_targets_the_single_capable_node(tmp_path, make_cmd, expected):
    path, ids = _make_db(tmp_path, [BBS_ONLY, RMS_ONLY])
    app = OpenPacketApp(db_path=path)
    async with app.run_test() as pilot:
        await pilot.pause()
        q = await _queue_via_picker(app, pilot, make_cmd())
        assert not isinstance(app.screen, NodeMultiPickerScreen)
    queued = q.get_nowait()
    assert queued.node_ids == [ids[expected]]


async def test_picker_lists_only_capable_nodes(tmp_path):
    path, ids = _make_db(tmp_path, [BBS_ONLY, RMS_ONLY, BOTH])
    app = OpenPacketApp(db_path=path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await _queue_via_picker(app, pilot, _winlink_msg())
        assert isinstance(app.screen, NodeMultiPickerScreen)
        assert [n.id for n in app.screen._node_list] == [ids["RMS"], ids["Both"]]


async def test_winlink_message_without_winlink_nodes_is_not_queued_and_user_is_told(tmp_path, monkeypatch):
    path, _ = _make_db(tmp_path, [BBS_ONLY])
    app = OpenPacketApp(db_path=path)
    notes: list[str] = []
    async with app.run_test() as pilot:
        await pilot.pause()
        monkeypatch.setattr(app, "notify", lambda msg, **kw: notes.append(msg))
        q = await _queue_via_picker(app, pilot, _winlink_msg())
    assert q.empty()
    assert any("Winlink" in n for n in notes)
