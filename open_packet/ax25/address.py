from __future__ import annotations
from dataclasses import dataclass


@dataclass
class AX25Address:
    callsign: str
    ssid: int
    last: bool


def encode_address(callsign: str, ssid: int, last: bool) -> bytes:
    padded = callsign.upper().ljust(6)[:6]
    encoded = bytes(ord(c) << 1 for c in padded)
    ssid_byte = 0b01100000 | ((ssid & 0x0F) << 1) | (1 if last else 0)
    return encoded + bytes([ssid_byte])


def decode_address(data: bytes) -> AX25Address:
    if len(data) < 7:
        raise ValueError(f"Address field must be 7 bytes, got {len(data)}")
    callsign = "".join(chr(b >> 1) for b in data[:6]).rstrip()
    ssid_byte = data[6]
    ssid = (ssid_byte >> 1) & 0x0F
    last = bool(ssid_byte & 0x01)
    return AX25Address(callsign=callsign, ssid=ssid, last=last)
