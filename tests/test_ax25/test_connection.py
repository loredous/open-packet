import pytest
from open_packet.ax25.connection import AX25Connection, LinkState
from open_packet.ax25.frame import (
    encode_ua, encode_dm, encode_disc, encode_i_frame, encode_rr,
    decode_frame, FrameType,
)
from open_packet.ax25.address import decode_address
from open_packet.link.base import ConnectionError as AXConnError
from open_packet.store.models import NodeHop


# --- Mock KISSLink ---

class MockKISS:
    def __init__(self):
        self.sent: list[bytes] = []
        self._rx: list[bytes] = []
        self.connected = False

    def connect(self, callsign, ssid, via_path=None):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def send_frame(self, data: bytes):
        self.sent.append(data)

    def receive_frame(self, timeout=5.0) -> bytes:
        if self._rx:
            return self._rx.pop(0)
        return b""

    def inject(self, raw_ax25: bytes):
        self._rx.append(raw_ax25)

    def last_sent_frame(self):
        return decode_frame(self.sent[-1]) if self.sent else None


MY_CALL, MY_SSID     = "KD9ABC", 0
DEST_CALL, DEST_SSID = "W0BPQ", 1


def make_conn():
    mock = MockKISS()
    conn = AX25Connection(mock, my_callsign=MY_CALL, my_ssid=MY_SSID)
    return conn, mock


def ua_frame():
    return encode_ua(
        dest=MY_CALL, dest_ssid=MY_SSID,
        src=DEST_CALL, src_ssid=DEST_SSID,
        final=True,
    )


def i_frame(payload: bytes, ns: int = 0, nr: int = 0):
    return encode_i_frame(
        dest=MY_CALL, dest_ssid=MY_SSID,
        src=DEST_CALL, src_ssid=DEST_SSID,
        ns=ns, nr=nr, payload=payload,
    )


def rr_frame(nr: int = 0):
    return encode_rr(
        dest=MY_CALL, dest_ssid=MY_SSID,
        src=DEST_CALL, src_ssid=DEST_SSID,
        nr=nr,
    )


# --- Connection setup ---

def test_connect_sends_sabm():
    conn, mock = make_conn()
    mock.inject(ua_frame())
    conn.connect(DEST_CALL, DEST_SSID)
    sent = mock.last_sent_frame()
    assert sent.frame_type == FrameType.SABM
    assert sent.poll_final  # P=1


def test_connect_enters_connected_state():
    conn, mock = make_conn()
    mock.inject(ua_frame())
    conn.connect(DEST_CALL, DEST_SSID)
    assert conn.state == LinkState.CONNECTED


def test_connect_resets_state_vars():
    conn, mock = make_conn()
    mock.inject(ua_frame())
    conn.connect(DEST_CALL, DEST_SSID)
    assert conn.V_S == 0
    assert conn.V_R == 0
    assert conn.V_A == 0


def test_connect_dm_response_raises():
    conn, mock = make_conn()
    dm = encode_dm(
        dest=MY_CALL, dest_ssid=MY_SSID,
        src=DEST_CALL, src_ssid=DEST_SSID,
        final=True,
    )
    mock.inject(dm)
    with pytest.raises(AXConnError):
        conn.connect(DEST_CALL, DEST_SSID)


# --- Sending I-frames ---

def test_send_frame_increments_vs():
    conn, mock = make_conn()
    mock.inject(ua_frame())
    conn.connect(DEST_CALL, DEST_SSID)
    conn.send_frame(b"L\r")
    assert conn.V_S == 1


def test_send_frame_correct_ns():
    conn, mock = make_conn()
    mock.inject(ua_frame())
    conn.connect(DEST_CALL, DEST_SSID)
    conn.send_frame(b"cmd\r")
    i_sent = None
    for raw in mock.sent[1:]:  # skip SABM
        f = decode_frame(raw)
        if f.frame_type == FrameType.I:
            i_sent = f
            break
    assert i_sent is not None
    assert i_sent.ns == 0
    assert i_sent.info == b"cmd\r"


# --- Receiving I-frames ---

def test_receive_frame_returns_payload():
    conn, mock = make_conn()
    mock.inject(ua_frame())
    conn.connect(DEST_CALL, DEST_SSID)
    mock.inject(i_frame(b"BPQ> ", ns=0, nr=0))
    data = conn.receive_frame(timeout=1.0)
    assert data == b"BPQ> "


def test_receive_frame_sends_rr():
    conn, mock = make_conn()
    mock.inject(ua_frame())
    conn.connect(DEST_CALL, DEST_SSID)
    mock.inject(i_frame(b"hello", ns=0))
    conn.receive_frame(timeout=1.0)
    rr_sent = None
    for raw in mock.sent[1:]:
        f = decode_frame(raw)
        if f.frame_type == FrameType.RR:
            rr_sent = f
            break
    assert rr_sent is not None
    assert rr_sent.nr == 1  # V(R) incremented to 1


def test_receive_frame_increments_vr():
    conn, mock = make_conn()
    mock.inject(ua_frame())
    conn.connect(DEST_CALL, DEST_SSID)
    mock.inject(i_frame(b"x", ns=0))
    conn.receive_frame(timeout=1.0)
    assert conn.V_R == 1


def test_receive_rr_updates_va():
    conn, mock = make_conn()
    mock.inject(ua_frame())
    conn.connect(DEST_CALL, DEST_SSID)
    conn.send_frame(b"L\r")  # V_S → 1
    mock.inject(rr_frame(nr=1))  # acknowledge frame 0
    conn.receive_frame(timeout=1.0)
    assert conn.V_A == 1


# --- Disconnection ---

def test_disconnect_sends_disc():
    conn, mock = make_conn()
    mock.inject(ua_frame())
    conn.connect(DEST_CALL, DEST_SSID)
    mock.inject(encode_ua(
        dest=MY_CALL, dest_ssid=MY_SSID,
        src=DEST_CALL, src_ssid=DEST_SSID,
        final=True,
    ))
    conn.disconnect()
    disc_sent = None
    for raw in mock.sent:
        f = decode_frame(raw)
        if f.frame_type == FrameType.DISC:
            disc_sent = f
            break
    assert disc_sent is not None


def test_disconnect_enters_disconnected_state():
    conn, mock = make_conn()
    mock.inject(ua_frame())
    conn.connect(DEST_CALL, DEST_SSID)
    mock.inject(encode_ua(
        dest=MY_CALL, dest_ssid=MY_SSID,
        src=DEST_CALL, src_ssid=DEST_SSID,
        final=True,
    ))
    conn.disconnect()
    assert conn.state == LinkState.DISCONNECTED


# --- VIA path encoding ---

def test_connect_with_via_path_encodes_via_in_sabm():
    kiss = MockKISS()
    conn = AX25Connection(kiss=kiss, my_callsign=MY_CALL, my_ssid=MY_SSID)
    # Inject UA to satisfy the handshake
    ua = encode_ua(MY_CALL, MY_SSID, DEST_CALL, DEST_SSID, final=True)
    kiss.inject(ua)
    via = [NodeHop(callsign="W0RLY-1")]
    conn.connect(DEST_CALL, DEST_SSID, via_path=via)
    sabm_raw = kiss.sent[0]
    # Address field should be 21 bytes (dest 7 + src 7 + via 7)
    src_addr = decode_address(sabm_raw[7:14])
    assert src_addr.last is False  # source not last when via present
    via_addr = decode_address(sabm_raw[14:21])
    assert via_addr.callsign.strip() == "W0RLY"
    assert via_addr.ssid == 1
    assert via_addr.last is True


# --- Frame filtering (relay scenario) ---

def _foreign_sabm():
    """A SABM from a relay's outbound callsign to a third party — not for us."""
    from open_packet.ax25.frame import encode_sabm
    return encode_sabm(
        dest="K0ARK", dest_ssid=7,
        src="K0JLB", src_ssid=14,   # relay using our base callsign with different SSID
        poll=True,
    )


def _foreign_i_frame():
    """An I-frame between two third-party stations — not for us."""
    return encode_i_frame(
        dest="K0JLB", dest_ssid=14,
        src="K0ARK", src_ssid=7,
        ns=0, nr=0, payload=b"hello",
    )


def test_foreign_sabm_does_not_disrupt_connected_session():
    """Relay traffic with our base callsign must not trigger _handle_sabm_reset."""
    conn, mock = make_conn()
    mock.inject(ua_frame())
    conn.connect(DEST_CALL, DEST_SSID)
    assert conn.state == LinkState.CONNECTED

    # Simulate normal exchange that advances sequence numbers
    mock.inject(i_frame(b"data", ns=0, nr=0))
    conn.receive_frame(timeout=0.1)
    assert conn.V_R == 1

    # Inject a foreign SABM (relay traffic not addressed to us)
    mock.inject(_foreign_sabm())
    conn.receive_frame(timeout=0.1)

    # State and sequence numbers must be undisturbed
    assert conn.state == LinkState.CONNECTED
    assert conn.V_R == 1
    # Must NOT have sent a UA in response to the foreign SABM
    ua_responses = [f for f in mock.sent if decode_frame(f).frame_type == FrameType.UA]
    assert len(ua_responses) == 0


def test_foreign_i_frame_does_not_affect_sequence_numbers():
    """I-frames for third-party stations must be silently ignored."""
    conn, mock = make_conn()
    mock.inject(ua_frame())
    conn.connect(DEST_CALL, DEST_SSID)

    # Inject foreign I-frame (K0ARK→K0JLB-14, not for K0JLB-0)
    mock.inject(_foreign_i_frame())
    result = conn.receive_frame(timeout=0.1)

    assert result == b""
    assert conn.V_R == 0  # unchanged
    # Must not have sent any supervisory response to it
    assert len(mock.sent) == 1  # only the original SABM
