from __future__ import annotations

from open_packet.link.base import ConnectionBase, ConnectionError
from open_packet.transport.base import TransportBase, TransportError

FEND = 0xC0
FESC = 0xDB
TFEND = 0xDC
TFESC = 0xDD
CMD_DATA = 0x00


def kiss_encode(data: bytes) -> bytes:
    escaped = bytearray()
    for byte in data:
        if byte == FEND:
            escaped += bytes([FESC, TFEND])
        elif byte == FESC:
            escaped += bytes([FESC, TFESC])
        else:
            escaped.append(byte)
    return bytes([FEND, CMD_DATA]) + bytes(escaped) + bytes([FEND])


def kiss_decode(packet: bytes) -> bytes:
    inner = packet.strip(bytes([FEND]))
    if not inner:
        return b""
    inner = inner[1:]   # skip command byte
    result = bytearray()
    i = 0
    while i < len(inner):
        if inner[i] == FESC:
            i += 1
            if i < len(inner):
                if inner[i] == TFEND:
                    result.append(FEND)
                elif inner[i] == TFESC:
                    result.append(FESC)
        else:
            result.append(inner[i])
        i += 1
    return bytes(result)


class KISSLink(ConnectionBase):
    """Pure KISS framing layer. No AX.25 logic — use AX25Connection for that."""

    def __init__(self, transport: TransportBase) -> None:
        self._transport = transport
        self._buffer = b""

    def connect(self, callsign: str, ssid: int, via_path=None) -> None:
        try:
            self._transport.connect()
        except TransportError as e:
            raise ConnectionError(f"Transport connect failed: {e}") from e

    def disconnect(self) -> None:
        self._transport.disconnect()

    def send_frame(self, data: bytes) -> None:
        try:
            self._transport.send_bytes(kiss_encode(data))
        except TransportError as e:
            raise ConnectionError(f"Send failed: {e}") from e

    def receive_frame(self, timeout: float = 5.0) -> bytes:
        try:
            chunk = self._transport.receive_bytes(timeout=timeout)
        except TransportError as e:
            raise ConnectionError(f"Receive failed: {e}") from e

        self._buffer += chunk
        start = self._buffer.find(bytes([FEND]))
        if start == -1:
            return b""
        end = self._buffer.find(bytes([FEND]), start + 1)
        if end == -1:
            return b""
        frame = self._buffer[start:end + 1]
        self._buffer = self._buffer[end + 1:]
        return kiss_decode(frame)
