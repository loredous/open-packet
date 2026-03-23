from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from open_packet.ax25.address import encode_address, decode_address

# --- U-frame control byte bases (bit 4 = P/F = 0) ---
U_SABM  = 0x2F   # Set Async Balanced Mode
U_SABME = 0x6F   # SABM Extended (mod-128)
U_DISC  = 0x43   # Disconnect
U_UA    = 0x63   # Unnumbered Acknowledge
U_DM    = 0x0F   # Disconnected Mode
U_UI    = 0x03   # Unnumbered Information
U_MASK  = 0xEF   # Mask to remove P/F bit for type identification

P_BIT   = 0x10   # Poll/Final bit position in control byte

# --- S-frame type bits (low nibble) ---
S_RR    = 0x01   # Receive Ready
S_RNR   = 0x05   # Receive Not Ready
S_REJ   = 0x09   # Reject

PID_NO_LAYER3 = 0xF0


class FrameType(Enum):
    I       = "I"
    RR      = "RR"
    RNR     = "RNR"
    REJ     = "REJ"
    SABM    = "SABM"
    SABME   = "SABME"
    DISC    = "DISC"
    UA      = "UA"
    DM      = "DM"
    UI      = "UI"
    UNKNOWN = "UNKNOWN"


@dataclass
class AX25Frame:
    frame_type: FrameType = field(default=FrameType.UNKNOWN)
    destination: str = ""
    destination_ssid: int = 0
    source: str = ""
    source_ssid: int = 0
    ns: int = 0
    nr: int = 0
    poll_final: bool = False
    info: bytes = field(default=b"")
    control: int = 0
    pid: int = PID_NO_LAYER3


# --- Helpers ---

def is_i_frame(ctrl: int) -> bool:
    return (ctrl & 0x01) == 0

def is_s_frame(ctrl: int) -> bool:
    return (ctrl & 0x03) == 0x01

def is_u_frame(ctrl: int) -> bool:
    return (ctrl & 0x03) == 0x03

def u_frame_type(ctrl: int) -> int:
    """Return U-frame base type with P/F bit cleared."""
    return ctrl & U_MASK


# --- Address field builder ---

def _addr_field(dest: str, dest_ssid: int, src: str, src_ssid: int,
                command: bool) -> bytes:
    """Build 14-byte address field with correct C bits (§6.1.2)."""
    return (
        encode_address(dest, dest_ssid, last=False, c_bit=command)
        + encode_address(src, src_ssid, last=True, c_bit=not command)
    )


# --- Encoders ---

def encode_sabm(dest: str, dest_ssid: int, src: str, src_ssid: int,
                poll: bool = True) -> bytes:
    ctrl = U_SABM | (P_BIT if poll else 0)
    return _addr_field(dest, dest_ssid, src, src_ssid, command=True) + bytes([ctrl])


def encode_sabme(dest: str, dest_ssid: int, src: str, src_ssid: int,
                 poll: bool = True) -> bytes:
    ctrl = U_SABME | (P_BIT if poll else 0)
    return _addr_field(dest, dest_ssid, src, src_ssid, command=True) + bytes([ctrl])


def encode_disc(dest: str, dest_ssid: int, src: str, src_ssid: int,
                poll: bool = True) -> bytes:
    ctrl = U_DISC | (P_BIT if poll else 0)
    return _addr_field(dest, dest_ssid, src, src_ssid, command=True) + bytes([ctrl])


def encode_ua(dest: str, dest_ssid: int, src: str, src_ssid: int,
              final: bool = True) -> bytes:
    ctrl = U_UA | (P_BIT if final else 0)
    return _addr_field(dest, dest_ssid, src, src_ssid, command=False) + bytes([ctrl])


def encode_dm(dest: str, dest_ssid: int, src: str, src_ssid: int,
              final: bool = True) -> bytes:
    ctrl = U_DM | (P_BIT if final else 0)
    return _addr_field(dest, dest_ssid, src, src_ssid, command=False) + bytes([ctrl])


def encode_i_frame(dest: str, dest_ssid: int, src: str, src_ssid: int,
                   ns: int, nr: int, payload: bytes,
                   poll: bool = False, pid: int = PID_NO_LAYER3) -> bytes:
    ctrl = (nr << 5) | (P_BIT if poll else 0) | (ns << 1)
    return (
        _addr_field(dest, dest_ssid, src, src_ssid, command=True)
        + bytes([ctrl, pid])
        + payload
    )


def _encode_s_frame(dest: str, dest_ssid: int, src: str, src_ssid: int,
                    s_bits: int, nr: int, poll_final: bool,
                    command: bool) -> bytes:
    ctrl = (nr << 5) | (P_BIT if poll_final else 0) | s_bits
    return _addr_field(dest, dest_ssid, src, src_ssid, command=command) + bytes([ctrl])


def encode_rr(dest: str, dest_ssid: int, src: str, src_ssid: int,
              nr: int, poll: bool = False, command: bool = True) -> bytes:
    return _encode_s_frame(dest, dest_ssid, src, src_ssid, S_RR, nr, poll, command)


def encode_rnr(dest: str, dest_ssid: int, src: str, src_ssid: int,
               nr: int, poll: bool = False, command: bool = True) -> bytes:
    return _encode_s_frame(dest, dest_ssid, src, src_ssid, S_RNR, nr, poll, command)


def encode_rej(dest: str, dest_ssid: int, src: str, src_ssid: int,
               nr: int, poll: bool = False, command: bool = True) -> bytes:
    return _encode_s_frame(dest, dest_ssid, src, src_ssid, S_REJ, nr, poll, command)


# --- Decoder ---

def decode_frame(data: bytes) -> AX25Frame:
    if len(data) < 15:
        raise ValueError(f"Frame too short: {len(data)} bytes")

    dest_addr = decode_address(data[0:7])
    src_addr  = decode_address(data[7:14])
    ctrl      = data[14]

    base = AX25Frame(
        frame_type=FrameType.UNKNOWN,
        destination=dest_addr.callsign,
        destination_ssid=dest_addr.ssid,
        source=src_addr.callsign,
        source_ssid=src_addr.ssid,
        control=ctrl,
    )

    if is_i_frame(ctrl):
        base.frame_type = FrameType.I
        base.ns = (ctrl >> 1) & 0x07
        base.nr = (ctrl >> 5) & 0x07
        base.poll_final = bool(ctrl & P_BIT)
        base.info = data[16:] if len(data) > 16 else b""
        return base

    if is_s_frame(ctrl):
        base.nr = (ctrl >> 5) & 0x07
        base.poll_final = bool(ctrl & P_BIT)
        typ = ctrl & 0x0F
        if typ == S_RR:
            base.frame_type = FrameType.RR
        elif typ == S_RNR:
            base.frame_type = FrameType.RNR
        elif typ == S_REJ:
            base.frame_type = FrameType.REJ
        return base

    # U-frame
    base.poll_final = bool(ctrl & P_BIT)
    typ = u_frame_type(ctrl)
    if typ == U_SABM:
        base.frame_type = FrameType.SABM
    elif typ == U_SABME:
        base.frame_type = FrameType.SABME
    elif typ == U_DISC:
        base.frame_type = FrameType.DISC
    elif typ == U_UA:
        base.frame_type = FrameType.UA
    elif typ == U_DM:
        base.frame_type = FrameType.DM
    elif typ == U_UI:
        base.frame_type = FrameType.UI
        base.info = data[16:] if len(data) > 16 else b""
    return base

