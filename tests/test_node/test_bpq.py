# tests/test_node/test_bpq.py
import pytest
from open_packet.node.bpq import BPQNode, parse_message_list, parse_message_header, _has_prompt
from open_packet.node.base import MessageHeader, NodeBase, NodeError
from open_packet.store.models import NodeHop


# --- _has_prompt unit tests ---

def test_has_prompt_bare():
    assert _has_prompt("BPQ>")

def test_has_prompt_with_menu():
    assert _has_prompt("Welcome to Node.\rW0IA> BBS CHAT NODES ROUTES MHEARD\r")

def test_has_prompt_lowercase_callsign():
    assert _has_prompt("Welcome to K0ARK.\rk0ark> BBS RMS NODES\r")

def test_has_prompt_de_prefix():
    # BPQ32 BBS prompts use "de CALLSIGN>" format
    assert _has_prompt("[BPQ-6.0.25]\rHello K0JLB. Latest 66\rde k0ark>\r")

def test_has_prompt_de_prefix_at_start():
    assert _has_prompt("de k0ark>")

def test_has_prompt_not_in_connected_to():
    # "Connected to K0ARK-7" must NOT trigger a false positive
    assert not _has_prompt("W0IA-7} Connected to K0ARK-7\r")

def test_has_prompt_not_in_nodes_output():
    assert not _has_prompt("W0IA-7} Nodes\rBCARES:W0IA-1   BCARES:W0IA-10\r")


# --- Parser unit tests (no connection needed) ---

# Real BPQ32 format: ID  DATE  TYPE  SIZE  TO  FROM  SUBJECT
LIST_OUTPUT = """\
Msg  Date    Type  Size  To        From      Subject
1    22-Mar  PY     234  KD9ABC    W0TEST    Hello there
2    21-Mar  PY     156  KD9ABC    W0FOO     Test message
60   01-Jun  BN     594  BCARES    KD0YYY    Message of the Week 06/01/24
"""

def test_parse_message_list():
    headers = parse_message_list(LIST_OUTPUT)
    assert len(headers) == 3
    assert headers[0].bbs_id == "1"
    assert headers[0].to_call == "KD9ABC"
    assert headers[0].from_call == "W0TEST"
    assert headers[0].subject == "Hello there"


def test_parse_message_header_strips_whitespace():
    headers = parse_message_list(LIST_OUTPUT)
    assert headers[1].bbs_id == "2"
    assert headers[1].from_call == "W0FOO"
    assert headers[1].subject == "Test message"


def test_parse_bulletin_header():
    headers = parse_message_list(LIST_OUTPUT)
    assert headers[2].bbs_id == "60"
    assert headers[2].to_call == "BCARES"
    assert headers[2].from_call == "KD0YYY"
    assert headers[2].subject == "Message of the Week 06/01/24"


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
    def receive_frame(self, timeout=5.0) -> bytes | None:
        return self._responses.pop(0) if self._responses else None


def test_bpqnode_list_messages():
    conn = MockConn(responses=[
        b"BPQ> ",
        (LIST_OUTPUT + "BPQ> ").encode(),
    ])
    node = BPQNode(connection=conn, node_callsign="W0BPQ", node_ssid=1,
                   my_callsign="KD9ABC", my_ssid=0)
    node.connect_node()
    headers = node.list_messages()
    assert len(headers) == 3


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
        b"1  22-Mar  PY  234  KD9ABC  W1XYZ  Hello\r\nBPQ>",
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


def test_list_linked_nodes_terminates_on_cr_without_prompt():
    """NODES response ends with CR (0x0d) — no prompt follows. Should not wait for idle timeout."""
    nodes_cr_terminated = b"W0IA-7} Nodes\rBCARES:W0IA-1   W0RELAY-3\r"
    conn = MockConn(responses=[nodes_cr_terminated])
    node = BPQNode(connection=conn, node_callsign="W0BPQ", node_ssid=1,
                   my_callsign="KD9ABC", my_ssid=0)
    hops = node.list_linked_nodes()
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


def test_connect_node_node_style_prompt_with_menu():
    """Node prompts look like 'CALL> CMD1 CMD2 ...' — > is not the last character."""
    conn = MockConn(responses=[
        b"Welcome to W0IA Node.\rW0IA> BBS CHAT NODES ROUTES MHEARD\r",
        b"BPQ>",
    ])
    node = BPQNode(
        connection=conn, node_callsign="W0BPQ", node_ssid=1,
        my_callsign="KD9ABC", my_ssid=0,
        hop_path=[NodeHop("W0HOP1", port=2), NodeHop("W0IA", port=1)],
        path_strategy="path_route",
    )
    node.connect_node()  # must not raise
    assert conn.sent[0] == b"C 1 W0IA\r"
    assert conn.sent[1] == b"BBS\r"


def test_connect_node_relay_connected_to_then_greeting():
    """Relay sends 'Connected to X' in one frame; remote node's greeting arrives next."""
    conn = MockConn(responses=[
        b"W0HOP1} Connected to W0HOP2\r",  # relay confirmation — no '>'
        b"W0HOP2> ",                         # remote node greeting
        b"BPQ>",
    ])
    node = BPQNode(
        connection=conn, node_callsign="W0BPQ", node_ssid=1,
        my_callsign="KD9ABC", my_ssid=0,
        hop_path=[NodeHop("W0HOP1", port=2), NodeHop("W0HOP2", port=1)],
        path_strategy="path_route",
    )
    node.connect_node()  # must not raise
    assert conn.sent[0] == b"C 1 W0HOP2\r"
    assert conn.sent[1] == b"BBS\r"


def test_connect_node_relay_connected_to_and_greeting_in_one_frame():
    """Relay confirmation and remote greeting arrive in the same frame — still works."""
    conn = MockConn(responses=[
        b"W0HOP1} Connected to W0HOP2\rW0HOP2> ",
        b"BPQ>",
    ])
    node = BPQNode(
        connection=conn, node_callsign="W0BPQ", node_ssid=1,
        my_callsign="KD9ABC", my_ssid=0,
        hop_path=[NodeHop("W0HOP1", port=2), NodeHop("W0HOP2", port=1)],
        path_strategy="path_route",
    )
    node.connect_node()  # must not raise
    assert conn.sent[0] == b"C 1 W0HOP2\r"
    assert conn.sent[1] == b"BBS\r"


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


# --- Multi-chunk and slow response handling ---

def test_list_linked_nodes_collects_response_across_multiple_frames():
    """Nodes list arriving across several receive_frame calls is fully assembled."""
    # Response split: body in one frame, prompt in the next (simulates slow BPQ32 node)
    conn = MockConn(responses=[
        b"K0ARK-7} Nodes\rK0RELAY 1\r",
        b"",           # one empty poll between chunks
        b"K0TEST 2\rk0ark> ",    # rest of data + prompt in a later frame
    ])
    node = BPQNode(connection=conn, node_callsign="K0ARK", node_ssid=7,
                   my_callsign="KD9ABC", my_ssid=0)
    hops = node.list_linked_nodes()
    callsigns = [h.callsign for h in hops]
    assert "K0RELAY" in callsigns
    assert "K0TEST" in callsigns


# --- Callsign deduplication ---

def test_parse_nodes_list_deduplicates_by_base_callsign():
    """Multiple SSIDs of the same physical station appear as a single entry."""
    text = "W0IA-1 1\nW0IA-10 2\nW0IA-11 3\nk0ark> "
    from open_packet.node.bpq import parse_nodes_list
    hops = parse_nodes_list(text)
    assert len(hops) == 1
    assert hops[0].callsign == "W0IA-1"  # first occurrence kept


def test_parse_nodes_list_keeps_distinct_stations():
    """Different base callsigns are preserved as separate entries."""
    text = "W0IA-1 1\nK0TEST-2 2\nW0IA-5 3\nk0ark> "
    from open_packet.node.bpq import parse_nodes_list
    hops = parse_nodes_list(text)
    assert len(hops) == 2
    callsigns = [h.callsign for h in hops]
    assert "W0IA-1" in callsigns
    assert "K0TEST-2" in callsigns


def test_wait_for_prompt_consumes_greeting():
    """wait_for_prompt drains the initial node greeting so NODES is sent after the prompt."""
    conn = MockConn(responses=[b"K0ARK-7} BPQ32 ...\rK0ARK-7>"])
    node = BPQNode(connection=conn, node_callsign="K0ARK", node_ssid=7,
                   my_callsign="KD9ABC", my_ssid=0)
    node.wait_for_prompt()  # should not raise
    assert conn.sent == []  # nothing sent — only received


def test_parse_nodes_list_alias_prefix_format():
    """BPQ32 can emit 'ALIAS:CALLSIGN' tokens, multiple per line."""
    text = "W0IA-7} Nodes\rBCARES:W0IA-1       BCARES:W0IA-10      BCARES:W0IA-11      \rBPQ>\r"
    from open_packet.node.bpq import parse_nodes_list
    hops = parse_nodes_list(text)
    # All three share base W0IA — deduped to one entry (first occurrence kept)
    assert len(hops) == 1
    assert hops[0].callsign == "W0IA-1"
    assert hops[0].port is None


def test_parse_nodes_list_alias_mixed_with_column_format():
    """Alias-prefixed callsigns alongside plain callsigns on the same or different lines."""
    text = "BCARES:W0IA-1\nK0TEST 2\nBPQ>\n"
    from open_packet.node.bpq import parse_nodes_list
    hops = parse_nodes_list(text)
    assert len(hops) == 2
    callsigns = [h.callsign for h in hops]
    assert "W0IA-1" in callsigns
    assert "K0TEST" in callsigns
    k0test = next(h for h in hops if h.callsign == "K0TEST")
    assert k0test.port == 2


def test_parse_nodes_list_node_header_line_ignored():
    """The 'NODECALL} Nodes' echo header must not appear as a hop."""
    text = "W0IA-7} Nodes\rK0RELAY 1\rBPQ>\r"
    from open_packet.node.bpq import parse_nodes_list
    hops = parse_nodes_list(text)
    assert len(hops) == 1
    assert hops[0].callsign == "K0RELAY"
