# tests/test_node/test_bpq.py
import pytest
from unittest.mock import MagicMock, call
from open_packet.node.bpq import BPQNode, parse_message_list, parse_message_header
from open_packet.node.base import MessageHeader, NodeError
from open_packet.ax25.frame import encode_frame, decode_frame, AX25Frame


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

def make_mock_connection(responses: list[str], source: str = "KD9ABC",
                         source_ssid: int = 0, dest: str = "W0BPQ",
                         dest_ssid: int = 1):
    conn = MagicMock()
    frames = [
        encode_frame(AX25Frame(
            destination=source, destination_ssid=source_ssid,
            source=dest, source_ssid=dest_ssid,
            info=r.encode(),
        ))
        for r in responses
    ] + [b""]

    conn.receive_frame.side_effect = frames
    return conn


def test_bpqnode_list_messages():
    responses = [
        "BPQ> ",  # initial prompt
        LIST_OUTPUT + "BPQ> ",  # response to L command
    ]
    conn = make_mock_connection(responses)
    node = BPQNode(connection=conn, node_callsign="W0BPQ", node_ssid=1,
                   my_callsign="KD9ABC", my_ssid=0)
    node.connect_node()
    headers = node.list_messages()
    assert len(headers) == 2


def test_bpqnode_delete_message():
    responses = [
        "BPQ> ",
        "Message 1 killed\nBPQ> ",
    ]
    conn = make_mock_connection(responses)
    node = BPQNode(connection=conn, node_callsign="W0BPQ", node_ssid=1,
                   my_callsign="KD9ABC", my_ssid=0)
    node.connect_node()
    node.delete_message("1")  # should not raise
