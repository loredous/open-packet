import socket
from unittest.mock import MagicMock, patch, call
import pytest
from open_packet.link.base import ConnectionError
from open_packet.link.telnet import TelnetLink, _strip_iac


# --- Unit tests for IAC stripping ---

def test_strip_iac_removes_3byte_will_sequence():
    # IAC WILL SUPPRESS-GO-AHEAD + IAC WILL ECHO
    data = b'\xff\xfb\x03\xff\xfb\x01user:'
    assert _strip_iac(data) == b'user:'


def test_strip_iac_removes_2byte_ga():
    # IAC GA (Go Ahead) — 2-byte command
    data = b'hello\xff\xf9world'
    assert _strip_iac(data) == b'helloworld'


def test_strip_iac_leaves_normal_data_unchanged():
    assert _strip_iac(b'de N0WHR>') == b'de N0WHR>'


def test_strip_iac_empty():
    assert _strip_iac(b'') == b''


# --- TelnetLink tests using mock socket ---

def _make_mock_sock(responses):
    """
    responses: list of bytes chunks returned by successive recv() calls.
    """
    sock = MagicMock()
    sock.recv.side_effect = responses + [socket.timeout]
    return sock


@patch('open_packet.link.telnet.socket.socket')
def test_connect_sends_username_then_password(MockSocket):
    mock_sock = _make_mock_sock([
        b'\xff\xfb\x03\xff\xfb\x01user:',   # banner + user prompt
        b'password:',                          # password prompt
        b'de N0WHR>',                          # BPQ node prompt
    ])
    MockSocket.return_value = mock_sock

    link = TelnetLink(host='localhost', port=8023, username='K0JLB', password='secret')
    link.connect('W0BPQ', 0)  # callsign/ssid ignored

    send_calls = mock_sock.sendall.call_args_list
    assert send_calls[0] == call(b'K0JLB\r\n')
    assert send_calls[1] == call(b'secret\r\n')


@patch('open_packet.link.telnet.socket.socket')
def test_connect_strips_iac_from_banner(MockSocket):
    """IAC bytes in banner are stripped before prompt matching."""
    mock_sock = _make_mock_sock([
        b'\xff\xfb\x03\xff\xfb\x01user:',
        b'password:',
        b'de N0WHR>',
    ])
    MockSocket.return_value = mock_sock

    link = TelnetLink('localhost', 8023, 'K0JLB', 'pw')
    # Should not raise — IAC bytes stripped before checking for 'user:'
    link.connect('W0BPQ', 0)


@patch('open_packet.link.telnet.time')
@patch('open_packet.link.telnet.socket.socket')
def test_connect_raises_on_timeout(MockSocket, mock_time):
    """connect() raises ConnectionError when deadline expires waiting for user: prompt."""
    mock_sock = MagicMock()
    mock_sock.recv.side_effect = socket.timeout  # each recv times out
    MockSocket.return_value = mock_sock

    # Make deadline expire immediately: first call returns 0.0 (deadline set),
    # second call returns 11.0 (past deadline), so loop exits after one iteration
    mock_time.monotonic.side_effect = [0.0, 11.0]

    link = TelnetLink('localhost', 8023, 'K0JLB', 'pw')
    with pytest.raises(ConnectionError, match="Timed out"):
        link.connect('W0BPQ', 0)


@patch('open_packet.link.telnet.socket.socket')
def test_receive_frame_returns_empty_on_timeout(MockSocket):
    mock_sock = MagicMock()
    mock_sock.recv.side_effect = socket.timeout
    MockSocket.return_value = mock_sock

    link = TelnetLink('localhost', 8023, 'K0JLB', 'pw')
    link._sock = mock_sock
    result = link.receive_frame(timeout=0.1)
    assert result == b''


@patch('open_packet.link.telnet.socket.socket')
def test_receive_frame_strips_iac(MockSocket):
    mock_sock = MagicMock()
    mock_sock.recv.return_value = b'\xff\xf9de N0WHR>'  # IAC GA + prompt
    MockSocket.return_value = mock_sock

    link = TelnetLink('localhost', 8023, 'K0JLB', 'pw')
    link._sock = mock_sock
    result = link.receive_frame(timeout=1.0)
    assert result == b'de N0WHR>'


@patch('open_packet.link.telnet.socket.socket')
def test_send_frame_calls_sendall(MockSocket):
    mock_sock = MagicMock()
    MockSocket.return_value = mock_sock

    link = TelnetLink('localhost', 8023, 'K0JLB', 'pw')
    link._sock = mock_sock
    link.send_frame(b'L\r')
    mock_sock.sendall.assert_called_once_with(b'L\r')


@patch('open_packet.link.telnet.socket.socket')
def test_disconnect_closes_socket(MockSocket):
    mock_sock = MagicMock()
    MockSocket.return_value = mock_sock

    link = TelnetLink('localhost', 8023, 'K0JLB', 'pw')
    link._sock = mock_sock
    link.disconnect()
    mock_sock.close.assert_called_once()
    assert link._sock is None


@patch('open_packet.link.telnet.socket.socket')
def test_connect_multi_chunk_login(MockSocket):
    """Login prompts may arrive split across multiple recv() calls."""
    mock_sock = _make_mock_sock([
        b'\xff\xfb\x03',    # IAC chunk
        b'\xff\xfb\x01',    # IAC chunk
        b'user:',           # prompt arrives separately
        b'pass',
        b'word:',           # password prompt split across chunks
        b'de N0WHR>',
    ])
    MockSocket.return_value = mock_sock

    link = TelnetLink('localhost', 8023, 'K0JLB', 'pw')
    link.connect('W0BPQ', 0)  # should not raise
