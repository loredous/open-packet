# tests/test_winlink/test_b2f.py
"""Tests for the B2F protocol session handler."""
from __future__ import annotations
from collections import deque
from typing import Optional

import pytest

from open_packet.winlink.b2f import B2FError, B2FSession
from open_packet.winlink.message import format_winlink_message


class FakeConnection:
    """Fake ConnectionBase for testing B2F sessions without real sockets."""

    def __init__(self, recv_data: list[bytes]):
        self._recv_queue: deque[bytes] = deque(recv_data)
        self.sent: list[bytes] = []

    def connect(self, callsign, ssid, via_path=None):
        pass

    def disconnect(self):
        pass

    def send_frame(self, data: bytes) -> None:
        self.sent.append(data)

    def receive_frame(self, timeout: float = 5.0) -> Optional[bytes]:
        if self._recv_queue:
            return self._recv_queue.popleft()
        return None


def _lines(*args: str) -> list[bytes]:
    """Convert string lines to list of bytes packets (each terminated with CRLF)."""
    return [(line + "\r\n").encode() for line in args]


class TestB2FHandshake:
    def test_rf_handshake(self):
        conn = FakeConnection(_lines(
            "WL2K V2.1.5.0 <TestSID>",    # gateway greeting
        ))
        session = B2FSession(conn, "W1AW", 10)
        session.handshake(is_telnet_cms=False)
        # Should have sent [WLNK-1.0]
        sent_text = b"".join(conn.sent).decode()
        assert "[WLNK-1.0]" in sent_text

    def test_telnet_cms_handshake(self):
        conn = FakeConnection(_lines(
            "WL2K V2.1.5.0 <TestSID>",          # gateway greeting
            "[WL2K-2.0-B2FWISP-2.2.2-]",        # server capabilities
        ))
        session = B2FSession(conn, "W1AW", 10)
        session.handshake(is_telnet_cms=True)
        sent_text = b"".join(conn.sent).decode()
        # Should have sent callsign and [WLNK-1.0]
        assert "[W1AW-10]" in sent_text
        assert "[WLNK-1.0]" in sent_text

    def test_bad_greeting_raises(self):
        conn = FakeConnection(_lines("BADGREETING"))
        session = B2FSession(conn, "W1AW", 0)
        with pytest.raises(B2FError):
            session.handshake()

    def test_timeout_raises(self):
        conn = FakeConnection([])  # no data
        session = B2FSession(conn, "W1AW", 0)
        with pytest.raises(B2FError):
            session.handshake()


class TestB2FReceiveProposals:
    def test_no_proposals(self):
        conn = FakeConnection(_lines("FF"))
        session = B2FSession(conn, "W1AW", 0)
        proposals = session.receive_proposals()
        assert proposals == []

    def test_uncompressed_proposal(self):
        conn = FakeConnection(_lines(
            "FW EM TESTMID00001 256 0 0",
            "FF",
        ))
        session = B2FSession(conn, "W1AW", 0)
        proposals = session.receive_proposals()
        assert len(proposals) == 1
        mid, size, compressed = proposals[0]
        assert mid == "TESTMID00001"
        assert size == 256
        assert compressed is False

    def test_compressed_proposal(self):
        conn = FakeConnection(_lines(
            "FC EM TESTMID00002 128 256 0",
            "FF",
        ))
        session = B2FSession(conn, "W1AW", 0)
        proposals = session.receive_proposals()
        assert len(proposals) == 1
        _, _, compressed = proposals[0]
        assert compressed is True

    def test_multiple_proposals(self):
        conn = FakeConnection(_lines(
            "FW EM MSG0000001A 100 0 0",
            "FW EM MSG0000002B 200 0 0",
            "FF",
        ))
        session = B2FSession(conn, "W1AW", 0)
        proposals = session.receive_proposals()
        assert len(proposals) == 2


class TestB2FReceiveMessages:
    def _build_conn_for_message(self, mime_str: str) -> FakeConnection:
        """Build a FakeConnection that yields an FW proposal + MIME data."""
        mime_bytes = mime_str.encode()
        size = len(mime_bytes)
        mid = "TESTMID00001"
        packets = _lines(f"FW EM {mid} {size} 0 0", "FF")
        # FA response and FS line will be sent by session; data follows
        packets.append(mime_bytes)
        return FakeConnection(packets)

    def test_receive_uncompressed_message(self):
        msg = format_winlink_message("W1AW", "K0ABC", "Test Subject", "Test body")
        conn = self._build_conn_for_message(msg.mime_str)
        session = B2FSession(conn, "K0ABC", 0)
        received = session.receive_messages()
        assert len(received) == 1
        assert received[0].subject == "Test Subject"

    def test_receive_compressed_skips(self):
        conn = FakeConnection(_lines(
            "FC EM TESTMID00001 128 256 0",
            "FF",
        ))
        session = B2FSession(conn, "K0ABC", 0)
        received = session.receive_messages()
        # Compressed messages are skipped in v1
        assert len(received) == 0
        # FR should have been sent for the skipped message
        sent_text = b"".join(conn.sent).decode()
        assert "FR" in sent_text


class TestB2FSendProposals:
    def test_send_message(self):
        wl_msg = format_winlink_message("W1AW", "K0ABC", "Outgoing", "Body text")
        # Gateway accepts: FA EM <mid>
        conn = FakeConnection(_lines(f"FA EM {wl_msg.mid}"))
        session = B2FSession(conn, "W1AW", 0)
        session.send_proposals([wl_msg])
        sent_text = b"".join(conn.sent).decode()
        assert "FW EM" in sent_text
        assert wl_msg.mid in sent_text
        assert "Body text" in sent_text

    def test_send_rejected(self):
        wl_msg = format_winlink_message("W1AW", "K0ABC", "Outgoing", "Body")
        # Gateway rejects: FR EM <mid>
        conn = FakeConnection(_lines(f"FR EM {wl_msg.mid}"))
        session = B2FSession(conn, "W1AW", 0)
        # Should not raise; just log a warning
        session.send_proposals([wl_msg])


class TestB2FFinish:
    def test_finish_sends_ff_fq(self):
        conn = FakeConnection(_lines("QU"))
        session = B2FSession(conn, "W1AW", 0)
        session.finish()
        sent_text = b"".join(conn.sent).decode()
        assert "FF" in sent_text
        assert "FQ" in sent_text
