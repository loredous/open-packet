# tests/test_node/test_bpq.py
import pytest
from open_packet.node.bpq import BPQNode, parse_message_list, parse_message_header
from open_packet.node.base import MessageHeader, NodeBase, NodeError
from open_packet.store.models import NodeHop


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

    def connect(self, callsign, ssid, via_path=None): pass
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


def test_node_base_has_post_bulletin():
    """NodeBase declares post_bulletin as abstract."""
    abstract_methods = getattr(NodeBase, '__abstractmethods__', set())
    assert 'post_bulletin' in abstract_methods


def test_post_bulletin_sends_correct_frames():
    """post_bulletin sends SB {category}, subject, body lines, then /EX."""
    conn = MockConn(responses=[
        b"Subject: BPQ>",
        b"Body: BPQ>",
        b"BPQ>",
    ])
    node = BPQNode(connection=conn, node_callsign="W0BPQ", node_ssid=1,
                   my_callsign="KD9ABC", my_ssid=0)
    node.post_bulletin("WX", "Storm warning", "Heavy rain\nHigh winds")
    assert conn.sent[0] == b"SB WX\r"
    assert conn.sent[1] == b"Storm warning\r"
    assert conn.sent[2] == b"Heavy rain\r"
    assert conn.sent[3] == b"High winds\r"
    assert conn.sent[4] == b"/EX\r"


# --- Hop traversal and node discovery tests ---

NODES_OUTPUT = """\
Nodes
Callsign  Port  Quality  Hops
W0RELAY-1    3      200     1
W0DIST       1      150     2
:
BPQ>
"""


def test_parse_nodes_list():
    from open_packet.node.bpq import parse_nodes_list
    hops = parse_nodes_list(NODES_OUTPUT)
    assert len(hops) == 2
    assert hops[0].callsign == "W0RELAY-1"
    assert hops[0].port == 3
    assert hops[1].callsign == "W0DIST"
    assert hops[1].port == 1


def test_parse_nodes_list_missing_port():
    from open_packet.node.bpq import parse_nodes_list
    output = "Nodes\nW0RELAY-1    bad   200   1\nBPQ>\n"
    hops = parse_nodes_list(output)
    assert hops[0].port is None


def test_parse_nodes_list_empty():
    from open_packet.node.bpq import parse_nodes_list
    assert parse_nodes_list("No nodes\nBPQ>\n") == []


def test_list_linked_nodes_sends_nodes_command():
    conn = MockConn(responses=[
        (NODES_OUTPUT).encode(),
    ])
    node = BPQNode(connection=conn, node_callsign="W0BPQ", node_ssid=1,
                   my_callsign="KD9ABC", my_ssid=0)
    hops = node.list_linked_nodes()
    assert conn.sent[0] == b"NODES\r"
    assert len(hops) == 2


def test_connect_node_single_hop_sends_only_bbs():
    """Single hop: hop_path[1:] is empty, so no C command — only BBS\r.
    hop_path[0] is the link-layer target; connect_node only traverses [1:]."""
    conn = MockConn(responses=[b"BPQ>"])
    node = BPQNode(
        connection=conn, node_callsign="W0BPQ", node_ssid=1,
        my_callsign="KD9ABC", my_ssid=0,
        hop_path=[NodeHop(callsign="W0RELAY", port=3)],
        path_strategy="path_route",
    )
    node.connect_node()
    assert conn.sent[0] == b"BBS\r"


def test_connect_node_path_route_two_hops():
    """Two hops: connect_node traverses hop_path[1:] only — one C command then BBS."""
    conn = MockConn(responses=[b"W0HOP2>", b"BPQ>"])
    node = BPQNode(
        connection=conn, node_callsign="W0BPQ", node_ssid=1,
        my_callsign="KD9ABC", my_ssid=0,
        hop_path=[NodeHop("W0HOP1", port=2), NodeHop("W0HOP2", port=1)],
        path_strategy="path_route",
    )
    node.connect_node()
    # hop_path[0] handled by link layer; hop_path[1:] = [W0HOP2:1]
    assert conn.sent[0] == b"C 1 W0HOP2\r"
    assert conn.sent[1] == b"BBS\r"


def test_connect_node_path_route_two_hops_no_port():
    """Second hop with no port: C command has no port prefix."""
    conn = MockConn(responses=[b"W0HOP2>", b"BPQ>"])
    node = BPQNode(
        connection=conn, node_callsign="W0BPQ", node_ssid=1,
        my_callsign="KD9ABC", my_ssid=0,
        hop_path=[NodeHop("W0HOP1"), NodeHop("W0HOP2")],
        path_strategy="path_route",
    )
    node.connect_node()
    assert conn.sent[0] == b"C W0HOP2\r"


def test_connect_node_digipeat_no_c_commands():
    """Digipeat strategy: connect_node sends BBS only regardless of hop_path."""
    conn = MockConn(responses=[b"BPQ>"])
    node = BPQNode(
        connection=conn, node_callsign="W0BPQ", node_ssid=1,
        my_callsign="KD9ABC", my_ssid=0,
        hop_path=[NodeHop(callsign="W0RELAY", port=3)],
        path_strategy="digipeat",
    )
    node.connect_node()
    assert conn.sent[0] == b"BBS\r"
