from open_packet.ax25.frame import (
    encode_sabm, encode_ua, encode_disc, encode_dm,
    encode_i_frame, encode_rr, encode_rnr, encode_rej,
    decode_frame, FrameType,
    is_i_frame, is_s_frame, is_u_frame, u_frame_type,
    U_SABM, U_UA, U_DISC, U_DM, P_BIT,
)
from open_packet.ax25.address import decode_address


# --- Frame type identification ---

def test_i_frame_identification():
    assert is_i_frame(0x00)   # N(S)=0, N(R)=0, P=0
    assert is_i_frame(0x02)   # N(S)=1
    assert not is_i_frame(0x01)  # S-frame

def test_s_frame_identification():
    assert is_s_frame(0x01)   # RR
    assert is_s_frame(0x05)   # RNR
    assert not is_s_frame(0x00)  # I-frame

def test_u_frame_identification():
    assert is_u_frame(0x03)   # UI
    assert is_u_frame(0x2F)   # SABM
    assert not is_u_frame(0x00)  # I-frame

def test_u_frame_type_masks_pf_bit():
    assert u_frame_type(0x3F) == U_SABM  # SABM with P=1
    assert u_frame_type(0x73) == U_UA    # UA with F=1


# --- SABM ---

def test_encode_sabm_correct_length():
    frame = encode_sabm("W0BPQ", 1, "KD9ABC", 0, poll=True)
    assert len(frame) == 15  # 7 dest + 7 src + 1 ctrl (no PID, no info)

def test_encode_sabm_control_byte():
    frame = encode_sabm("W0BPQ", 1, "KD9ABC", 0, poll=True)
    ctrl = frame[14]
    assert u_frame_type(ctrl) == U_SABM
    assert ctrl & P_BIT  # P bit set

def test_encode_sabm_command_c_bits():
    frame = encode_sabm("W0BPQ", 1, "KD9ABC", 0, poll=True)
    # Destination C bit = 1 (command), source C bit = 0
    assert frame[6] & 0x80   # dest C=1
    assert not (frame[13] & 0x80)  # src C=0


# --- UA ---

def test_encode_ua_correct_length():
    frame = encode_ua("KD9ABC", 0, "W0BPQ", 1, final=True)
    assert len(frame) == 15

def test_encode_ua_control_byte():
    frame = encode_ua("KD9ABC", 0, "W0BPQ", 1, final=True)
    ctrl = frame[14]
    assert u_frame_type(ctrl) == U_UA
    assert ctrl & P_BIT  # F bit set


# --- DISC ---

def test_encode_disc_correct_length():
    frame = encode_disc("W0BPQ", 1, "KD9ABC", 0, poll=True)
    assert len(frame) == 15

def test_encode_disc_is_command():
    frame = encode_disc("W0BPQ", 1, "KD9ABC", 0, poll=True)
    assert frame[6] & 0x80   # dest C=1 (command)


# --- I-frame ---

def test_encode_i_frame_has_pid_and_info():
    frame = encode_i_frame("W0BPQ", 1, "KD9ABC", 0, ns=0, nr=0, payload=b"L\r")
    assert len(frame) == 7 + 7 + 1 + 1 + 2  # addr + ctrl + pid + payload

def test_encode_i_frame_control_byte():
    frame = encode_i_frame("W0BPQ", 1, "KD9ABC", 0, ns=3, nr=5, payload=b"x")
    ctrl = frame[14]
    assert is_i_frame(ctrl)
    ns_decoded = (ctrl >> 1) & 0x07
    nr_decoded = (ctrl >> 5) & 0x07
    assert ns_decoded == 3
    assert nr_decoded == 5

def test_encode_i_frame_payload():
    frame = encode_i_frame("W0BPQ", 1, "KD9ABC", 0, ns=0, nr=0, payload=b"Hello")
    assert frame[16:] == b"Hello"


# --- RR ---

def test_encode_rr_control_byte():
    frame = encode_rr("W0BPQ", 1, "KD9ABC", 0, nr=3, poll=False)
    ctrl = frame[14]
    assert is_s_frame(ctrl)
    assert (ctrl & 0x0F) == 0x01   # RR bits
    assert (ctrl >> 5) & 0x07 == 3  # N(R)=3


# --- decode_frame ---

def test_decode_sabm():
    raw = encode_sabm("W0BPQ", 1, "KD9ABC", 0, poll=True)
    f = decode_frame(raw)
    assert f.frame_type == FrameType.SABM
    assert f.poll_final is True
    assert f.destination == "W0BPQ"
    assert f.source == "KD9ABC"

def test_decode_ua():
    raw = encode_ua("KD9ABC", 0, "W0BPQ", 1, final=True)
    f = decode_frame(raw)
    assert f.frame_type == FrameType.UA
    assert f.poll_final is True

def test_decode_i_frame():
    raw = encode_i_frame("W0BPQ", 1, "KD9ABC", 0, ns=2, nr=4, payload=b"test")
    f = decode_frame(raw)
    assert f.frame_type == FrameType.I
    assert f.ns == 2
    assert f.nr == 4
    assert f.info == b"test"

def test_decode_rr():
    raw = encode_rr("W0BPQ", 1, "KD9ABC", 0, nr=5, poll=True)
    f = decode_frame(raw)
    assert f.frame_type == FrameType.RR
    assert f.nr == 5
    assert f.poll_final is True


# --- VIA address encoding ---

def test_encode_sabm_no_via():
    """Baseline: 14-byte address field, last bit set on source."""
    raw = encode_sabm("W0BPQ", 1, "KD9ABC", 0)
    src = decode_address(raw[7:14])
    assert src.last is True
    assert len(raw) == 15  # 14-byte addr + 1-byte ctrl

def test_encode_sabm_with_via():
    """With one VIA hop: 21-byte address field, source last=False, VIA last=True."""
    raw = encode_sabm("W0BPQ", 1, "KD9ABC", 0, via=[("W0RLY", 1)])
    assert len(raw) == 22  # 21-byte addr + 1 ctrl
    src = decode_address(raw[7:14])
    assert src.last is False
    via = decode_address(raw[14:21])
    assert via.callsign.strip() == "W0RLY"
    assert via.ssid == 1
    assert via.last is True

def test_encode_sabm_with_two_via():
    """Two VIA hops: first VIA last=False, second VIA last=True."""
    raw = encode_sabm("W0BPQ", 1, "KD9ABC", 0, via=[("W0R1", 0), ("W0R2", 0)])
    assert len(raw) == 29  # 28-byte addr + 1 ctrl
    v1 = decode_address(raw[14:21])
    v2 = decode_address(raw[21:28])
    assert v1.last is False
    assert v2.last is True
