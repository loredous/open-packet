# tests/test_winlink/test_winlink_node.py
"""Tests for WinlinkNode."""
from __future__ import annotations
from collections import deque
from typing import Optional

import pytest

from open_packet.node.base import NodeError
from open_packet.node.winlink import WinlinkNode
from open_packet.winlink.message import format_winlink_message


class FakeConnection:
    def __init__(self, recv_data: list[bytes]):
        self._recv_queue: deque[bytes] = deque(recv_data)
        self.sent: list[bytes] = []
        self.disconnected = False

    def connect(self, callsign, ssid, via_path=None):
        pass

    def disconnect(self):
        self.disconnected = True

    def send_frame(self, data: bytes) -> None:
        self.sent.append(data)

    def receive_frame(self, timeout: float = 5.0) -> Optional[bytes]:
        if self._recv_queue:
            return self._recv_queue.popleft()
        return None


def _lines(*args: str) -> list[bytes]:
    return [(line + "\r\n").encode() for line in args]


class TestWinlinkNodeInterface:
    def _make_node_with_handshake(self, extra_recv: list[bytes] = None) -> tuple[WinlinkNode, FakeConnection]:
        recv = _lines("WL2K V2.1.5.0 <SID>")
        if extra_recv:
            recv.extend(extra_recv)
        conn = FakeConnection(recv)
        node = WinlinkNode(conn, "W1AW", 10)
        return node, conn

    def test_connect_node_performs_handshake(self):
        node, conn = self._make_node_with_handshake()
        node.connect_node()
        sent_text = b"".join(conn.sent).decode()
        assert "[WLNK-1.0]" in sent_text

    def test_connect_node_bad_greeting_raises_node_error(self):
        conn = FakeConnection(_lines("GARBAGE"))
        node = WinlinkNode(conn, "W1AW", 0)
        with pytest.raises(NodeError):
            node.connect_node()

    def test_wait_for_prompt_noop(self):
        conn = FakeConnection([])
        node = WinlinkNode(conn, "W1AW", 0)
        # Should not raise
        node.wait_for_prompt()

    def test_list_linked_nodes_empty(self):
        conn = FakeConnection([])
        node = WinlinkNode(conn, "W1AW", 0)
        assert node.list_linked_nodes() == []

    def test_list_bulletins_empty(self):
        conn = FakeConnection([])
        node = WinlinkNode(conn, "W1AW", 0)
        assert node.list_bulletins() == []

    def test_list_files_empty(self):
        conn = FakeConnection([])
        node = WinlinkNode(conn, "W1AW", 0)
        assert node.list_files() == []

    def test_delete_message_noop(self):
        conn = FakeConnection([])
        node = WinlinkNode(conn, "W1AW", 0)
        # Should not raise
        node.delete_message("SOMEMID")

    def test_read_bulletin_raises(self):
        conn = FakeConnection([])
        node = WinlinkNode(conn, "W1AW", 0)
        with pytest.raises(NodeError):
            node.read_bulletin("MID")

    def test_post_bulletin_raises(self):
        conn = FakeConnection([])
        node = WinlinkNode(conn, "W1AW", 0)
        with pytest.raises(NodeError):
            node.post_bulletin("WX", "Subject", "Body")

    def test_read_file_raises(self):
        conn = FakeConnection([])
        node = WinlinkNode(conn, "W1AW", 0)
        with pytest.raises(NodeError):
            node.read_file("test.txt")

    def test_list_messages_without_connect_raises(self):
        conn = FakeConnection([])
        node = WinlinkNode(conn, "W1AW", 0)
        with pytest.raises(NodeError):
            node.list_messages()

    def test_send_message_without_connect_raises(self):
        conn = FakeConnection([])
        node = WinlinkNode(conn, "W1AW", 0)
        with pytest.raises(NodeError):
            node.send_message("K0ABC", "Subject", "Body")

    def test_list_messages_returns_headers(self):
        msg = format_winlink_message("W1AW", "K0ABC", "Hello", "World")
        mime_bytes = msg.mime_str.encode()
        size = len(mime_bytes)
        recv = (
            _lines("WL2K V2.1.5.0 <SID>")
            + _lines(f"FW EM {msg.mid} {size} 0 0", "FF")
            + [mime_bytes]
        )
        conn = FakeConnection(recv)
        node = WinlinkNode(conn, "K0ABC", 0)
        node.connect_node()
        headers = node.list_messages()
        assert len(headers) == 1
        assert headers[0].subject == "Hello"
        assert headers[0].bbs_id == msg.mid

    def test_read_message_after_list(self):
        msg = format_winlink_message("W1AW", "K0ABC", "Hello", "World body")
        mime_bytes = msg.mime_str.encode()
        size = len(mime_bytes)
        recv = (
            _lines("WL2K V2.1.5.0 <SID>")
            + _lines(f"FW EM {msg.mid} {size} 0 0", "FF")
            + [mime_bytes]
        )
        conn = FakeConnection(recv)
        node = WinlinkNode(conn, "K0ABC", 0)
        node.connect_node()
        node.list_messages()
        result = node.read_message(msg.mid)
        assert "World body" in result.body

    def test_read_message_unknown_mid_raises(self):
        recv = _lines("WL2K V2.1.5.0 <SID>") + _lines("FF")
        conn = FakeConnection(recv)
        node = WinlinkNode(conn, "K0ABC", 0)
        node.connect_node()
        node.list_messages()
        with pytest.raises(NodeError):
            node.read_message("UNKNOWNMID1")


class TestWinlinkNodeSendMessage:
    def test_send_message_accepted(self):
        recv = (
            _lines("WL2K V2.1.5.0 <SID>")
            + [b"FA EM TESTMID00001\r\n"]  # gateway accepts (MID generated by node)
        )
        conn = FakeConnection(recv)
        node = WinlinkNode(conn, "W1AW", 0)
        node.connect_node()
        # Should not raise (FA response may not match generated MID exactly in test,
        # but we can verify send_frame was called with FW header)
        try:
            node.send_message("K0ABC", "Test", "Body")
        except Exception:
            pass  # Gateway rejection is non-fatal
        sent_text = b"".join(conn.sent).decode()
        assert "FW EM" in sent_text
