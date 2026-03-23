import pytest
from open_packet.link.kiss import kiss_encode, kiss_decode, KISSLink
from open_packet.transport.base import TransportBase, TransportError


# --- KISS encode/decode unit tests ---

def test_kiss_encode_simple():
    data = b"\x01\x02\x03"
    encoded = kiss_encode(data)
    assert encoded == b"\xc0\x00\x01\x02\x03\xc0"


def test_kiss_encode_escapes_fend():
    data = b"\xc0"
    encoded = kiss_encode(data)
    assert encoded == b"\xc0\x00\xdb\xdc\xc0"


def test_kiss_encode_escapes_fesc():
    data = b"\xdb"
    encoded = kiss_encode(data)
    assert encoded == b"\xc0\x00\xdb\xdd\xc0"


def test_kiss_decode_simple():
    packet = b"\xc0\x00\x01\x02\x03\xc0"
    decoded = kiss_decode(packet)
    assert decoded == b"\x01\x02\x03"


def test_kiss_decode_unescapes_fend():
    packet = b"\xc0\x00\xdb\xdc\xc0"
    decoded = kiss_decode(packet)
    assert decoded == b"\xc0"


def test_kiss_decode_unescapes_fesc():
    packet = b"\xc0\x00\xdb\xdd\xc0"
    decoded = kiss_decode(packet)
    assert decoded == b"\xdb"


def test_kiss_round_trip():
    original = b"Hello\xc0World\xdb!"
    assert kiss_decode(kiss_encode(original)) == original


# --- KISSLink integration using a mock transport ---

class MockTransport(TransportBase):
    def __init__(self, responses: list[bytes]):
        self._responses = list(responses)
        self.sent: list[bytes] = []
        self._connected = False

    def connect(self): self._connected = True
    def disconnect(self): self._connected = False

    def send_bytes(self, data: bytes):
        self.sent.append(data)

    def receive_bytes(self, timeout: float = 5.0) -> bytes:
        if self._responses:
            return self._responses.pop(0)
        return b""


def test_kisslink_send_frame():
    transport = MockTransport(responses=[])
    link = KISSLink(transport=transport)
    link.connect(callsign="W0BPQ", ssid=1)

    raw = b"\xae`\x84\xa0\xa2@\x62\x96\x88r\x82\x84\x86\x61\x00\xf0L\r"
    link.send_frame(raw)
    assert len(transport.sent) == 1
    assert transport.sent[0].startswith(b"\xc0")
    assert transport.sent[0].endswith(b"\xc0")


def test_kisslink_receive_frame():
    raw = b"\xae`\x84\xa0\xa2@\x62\x96\x88r\x82\x84\x86\x61\x03\xf0BPQ> "
    kiss_packet = kiss_encode(raw)
    transport = MockTransport(responses=[kiss_packet])
    link = KISSLink(transport=transport)
    link.connect(callsign="W0BPQ", ssid=1)

    received = link.receive_frame(timeout=1.0)
    assert received == raw
