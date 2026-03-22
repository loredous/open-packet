from open_packet.ax25.address import encode_address, decode_address, AX25Address


def test_encode_callsign_no_ssid():
    # "KD9ABC" with SSID 0, not last address
    encoded = encode_address("KD9ABC", ssid=0, last=False)
    assert len(encoded) == 7
    # Each char shifted left by 1
    assert encoded[0] == ord("K") << 1
    assert encoded[1] == ord("D") << 1
    assert encoded[2] == ord("9") << 1
    assert encoded[3] == ord("A") << 1
    assert encoded[4] == ord("B") << 1
    assert encoded[5] == ord("C") << 1
    # SSID byte: 0b01100000 | (0 << 1) | 0 = 0x60
    assert encoded[6] == 0x60


def test_encode_callsign_with_ssid():
    encoded = encode_address("KD9ABC", ssid=1, last=True)
    # SSID byte: 0b01100000 | (1 << 1) | 1 = 0x63
    assert encoded[6] == 0x63


def test_encode_short_callsign_padded():
    # Callsigns shorter than 6 chars must be space-padded
    encoded = encode_address("W0BPQ", ssid=0, last=False)
    assert len(encoded) == 7
    assert encoded[4] == ord("Q") << 1
    assert encoded[5] == ord(" ") << 1  # padded


def test_decode_address():
    encoded = encode_address("KD9ABC", ssid=1, last=True)
    addr = decode_address(encoded)
    assert addr.callsign == "KD9ABC"
    assert addr.ssid == 1
    assert addr.last is True


def test_decode_short_callsign():
    encoded = encode_address("W0BPQ", ssid=0, last=False)
    addr = decode_address(encoded)
    assert addr.callsign == "W0BPQ"
    assert addr.ssid == 0
    assert addr.last is False
