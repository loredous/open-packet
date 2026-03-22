from open_packet.ax25.frame import AX25Frame, encode_frame, decode_frame


def test_encode_ui_frame():
    frame = AX25Frame(
        destination="W0BPQ",
        destination_ssid=1,
        source="KD9ABC",
        source_ssid=0,
        info=b"Hello",
    )
    data = encode_frame(frame)
    assert isinstance(data, bytes)
    # Destination is first 7 bytes
    assert len(data) >= 16  # 7 + 7 + 1 + 1 + 5


def test_round_trip():
    original = AX25Frame(
        destination="W0BPQ",
        destination_ssid=1,
        source="KD9ABC",
        source_ssid=0,
        info=b"Test message",
    )
    data = encode_frame(original)
    decoded = decode_frame(data)
    assert decoded.destination == "W0BPQ"
    assert decoded.destination_ssid == 1
    assert decoded.source == "KD9ABC"
    assert decoded.source_ssid == 0
    assert decoded.info == b"Test message"


def test_empty_info():
    frame = AX25Frame(
        destination="W0BPQ",
        destination_ssid=0,
        source="KD9ABC",
        source_ssid=1,
        info=b"",
    )
    data = encode_frame(frame)
    decoded = decode_frame(data)
    assert decoded.info == b""


def test_decode_sets_last_flags_correctly():
    frame = AX25Frame(
        destination="W0BPQ",
        destination_ssid=0,
        source="KD9ABC",
        source_ssid=0,
        info=b"x",
    )
    data = encode_frame(frame)
    # Source address last bit must be set (end of address field)
    # Destination last bit must NOT be set
    assert data[6] & 0x01 == 0   # destination not last
    assert data[13] & 0x01 == 1  # source is last
