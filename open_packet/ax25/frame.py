from __future__ import annotations
from dataclasses import dataclass, field

from open_packet.ax25.address import encode_address, decode_address

# UI frame constants
CONTROL_UI = 0x03
PID_NO_LAYER3 = 0xF0


@dataclass
class AX25Frame:
    destination: str
    destination_ssid: int
    source: str
    source_ssid: int
    info: bytes = field(default=b"")
    control: int = CONTROL_UI
    pid: int = PID_NO_LAYER3


def encode_frame(frame: AX25Frame) -> bytes:
    dest = encode_address(frame.destination, frame.destination_ssid, last=False)
    src = encode_address(frame.source, frame.source_ssid, last=True)
    return dest + src + bytes([frame.control, frame.pid]) + frame.info


def decode_frame(data: bytes) -> AX25Frame:
    if len(data) < 16:
        raise ValueError(f"Frame too short: {len(data)} bytes")
    destination_addr = decode_address(data[0:7])
    source_addr = decode_address(data[7:14])
    control = data[14]
    pid = data[15]
    info = data[16:]
    return AX25Frame(
        destination=destination_addr.callsign,
        destination_ssid=destination_addr.ssid,
        source=source_addr.callsign,
        source_ssid=source_addr.ssid,
        info=info,
        control=control,
        pid=pid,
    )
