from __future__ import annotations
import queue
import threading
import time
from unittest.mock import MagicMock

from open_packet.terminal.session import TerminalSession, TerminalConnectResult
from open_packet.store.models import Interface


# --- Unit tests (no threads) ---

def test_poll_drains_queue():
    conn = MagicMock()
    session = TerminalSession(label="W0TEST", connection=conn)
    session._rx_queue.put("hello")
    session._rx_queue.put("world")
    lines = session.poll()
    assert lines == ["hello", "world"]
    assert session.poll() == []


def test_poll_empty_returns_empty_list():
    conn = MagicMock()
    session = TerminalSession(label="W0TEST", connection=conn)
    assert session.poll() == []


def test_send_encodes_text_with_carriage_return():
    conn = MagicMock()
    session = TerminalSession(label="W0TEST", connection=conn)
    session.status = "connected"
    session.send("hello")
    conn.send_frame.assert_called_once_with(b"hello\r")


def test_send_is_noop_when_not_connected():
    conn = MagicMock()
    session = TerminalSession(label="W0TEST", connection=conn)
    # status is "connecting" — send should not call send_frame
    session.send("hello")
    conn.send_frame.assert_not_called()


def test_initial_status_is_connecting():
    conn = MagicMock()
    session = TerminalSession(label="W0TEST", connection=conn)
    assert session.status == "connecting"
    assert session.has_unread is False


# --- Integration tests (with threads) ---

def _make_blocking_session(frames: list[bytes]):
    """Session whose fake connection yields `frames` then blocks indefinitely."""
    conn = MagicMock()
    frame_q: queue.Queue[bytes] = queue.Queue()
    for f in frames:
        frame_q.put(f)
    stop = threading.Event()

    def fake_recv(timeout=1.0):
        try:
            return frame_q.get(timeout=min(timeout, 0.05))
        except queue.Empty:
            stop.wait(timeout=min(timeout, 0.05))
            return b''

    conn.receive_frame.side_effect = fake_recv
    session = TerminalSession(
        label="W0TEST", connection=conn,
        target_callsign="W0XYZ", target_ssid=0,
    )
    return session, stop


def _wait_for(condition, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_run_thread_sets_connected_status():
    session, stop = _make_blocking_session([])
    session.start()
    assert _wait_for(lambda: session.status == "connected")
    stop.set()
    session.disconnect()


def test_run_thread_receives_frame_into_poll():
    session, stop = _make_blocking_session([b"hello\r\n"])
    session.start()
    # Collect lines in a container to work around walrus operator scoping in lambdas
    collected = {}
    assert _wait_for(lambda: bool(collected.update({'lines': session.poll()}) or collected['lines']))
    lines = collected['lines']
    assert any("hello" in l for l in lines)
    stop.set()
    session.disconnect()


def test_connect_error_sets_error_status():
    conn = MagicMock()
    conn.connect.side_effect = Exception("refused")
    session = TerminalSession(label="W0TEST", connection=conn)
    session.start()
    assert _wait_for(lambda: session.status == "error")
    lines = session.poll()
    assert any("connection error" in l for l in lines)


def test_disconnect_sets_disconnected_status():
    session, stop = _make_blocking_session([])
    session.start()
    _wait_for(lambda: session.status == "connected")
    stop.set()
    session.disconnect()
    assert session.status == "disconnected"


# --- TerminalConnectResult ---

def test_terminal_connect_result_fields():
    iface = Interface(id=1, label="Home", iface_type="kiss_tcp", host="localhost", port=8910)
    result = TerminalConnectResult(
        label="W0XYZ",
        interface=iface,
        target_callsign="W0XYZ",
        target_ssid=3,
    )
    assert result.label == "W0XYZ"
    assert result.interface is iface
    assert result.target_callsign == "W0XYZ"
    assert result.target_ssid == 3
