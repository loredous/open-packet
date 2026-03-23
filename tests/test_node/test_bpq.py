# tests/test_node/test_bpq.py
import pytest
from open_packet.node.bpq import BPQNode, parse_message_list, parse_message_header
from open_packet.node.base import MessageHeader, NodeError


# --- Parser unit tests (no connection needed) ---

LIST_OUTPUT = """\
Msg  To        From      Date   Subject
1    KD9ABC    W0TEST    03/22  Hello there
2    KD9ABC    W0FOO     03/21  Test message
"""

def test_parse_message_list():
    headers = parse_message_list(LIST_OUTPUT)
    assert len(headers) == 2
    assert headers[0].bbs_id == "1"
    assert headers[0].to_call == "KD9ABC"
    assert headers[0].from_call == "W0TEST"
    assert headers[0].subject == "Hello there"


def test_parse_message_header_strips_whitespace():
    headers = parse_message_list(LIST_OUTPUT)
    assert headers[1].bbs_id == "2"
    assert headers[1].from_call == "W0FOO"
    assert headers[1].subject == "Test message"


def test_parse_empty_list():
    assert parse_message_list("No messages\n") == []


# --- BPQNode session tests using a mock connection ---

class MockConn:
    def __init__(self, responses: list[bytes]):
        self._responses = list(responses)
        self.sent: list[bytes] = []

    def connect(self, callsign, ssid): pass
    def disconnect(self): pass
    def send_frame(self, data: bytes): self.sent.append(data)
    def receive_frame(self, timeout=5.0) -> bytes:
        return self._responses.pop(0) if self._responses else b""


def test_bpqnode_list_messages():
    conn = MockConn(responses=[
        b"BPQ> ",
        (LIST_OUTPUT + "BPQ> ").encode(),
    ])
    node = BPQNode(connection=conn, node_callsign="W0BPQ", node_ssid=1,
                   my_callsign="KD9ABC", my_ssid=0)
    node.connect_node()
    headers = node.list_messages()
    assert len(headers) == 2


def test_bpqnode_delete_message():
    conn = MockConn(responses=[
        b"BPQ> ",
        b"Message 1 killed\nBPQ> ",
    ])
    node = BPQNode(connection=conn, node_callsign="W0BPQ", node_ssid=1,
                   my_callsign="KD9ABC", my_ssid=0)
    node.connect_node()
    node.delete_message("1")  # should not raise


def test_connect_node_receives_prompt():
    conn = MockConn(responses=[b"BPQ>"])
    node = BPQNode(connection=conn, node_callsign="W0BPQ", node_ssid=1,
                   my_callsign="KD9ABC", my_ssid=0)
    node.connect_node()  # should not raise


def test_list_messages_sends_l_command():
    conn = MockConn(responses=[
        b"1  KD9ABC  W1XYZ   2024-01-01  Hello\r\nBPQ>",
    ])
    node = BPQNode(connection=conn, node_callsign="W0BPQ", node_ssid=1,
                   my_callsign="KD9ABC", my_ssid=0)
    headers = node.list_messages()
    assert conn.sent[0] == b"L\r"
    assert len(headers) == 1
