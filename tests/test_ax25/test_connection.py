import pytest
from open_packet.ax25.connection import AX25Connection, LinkState
from open_packet.ax25.frame import (
    encode_ua, encode_dm, encode_disc, encode_i_frame, encode_rr,
    decode_frame, FrameType,
)
from open_packet.link.base import ConnectionError as AXConnError


# --- Mock KISSLink ---

class MockKISS:
    def __init__(self):
        self.sent: list[bytes] = []
        self._rx: list[bytes] = []
        self.connected = False

    def connect(self, callsign, ssid):
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
