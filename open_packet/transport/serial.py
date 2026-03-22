from __future__ import annotations
import serial
from open_packet.transport.base import TransportBase, TransportError


class SerialTransport(TransportBase):
    def __init__(self, device: str, baud: int = 9600):
        self._device = device
        self._baud = baud
        self._port: serial.Serial | None = None

    def connect(self) -> None:
        try:
            self._port = serial.Serial(
                port=self._device,
                baudrate=self._baud,
                timeout=5.0,
            )
        except serial.SerialException as e:
            raise TransportError(f"Failed to open {self._device}: {e}") from e

    def disconnect(self) -> None:
        if self._port and self._port.is_open:
            try:
                self._port.close()
            except serial.SerialException:
                pass
        self._port = None

    def send_bytes(self, data: bytes) -> None:
        if not self._port or not self._port.is_open:
            raise TransportError("not connected")
        try:
            self._port.write(data)
        except serial.SerialException as e:
            raise TransportError(f"Send failed: {e}") from e

    def receive_bytes(self, timeout: float = 5.0) -> bytes:
        if not self._port or not self._port.is_open:
            raise TransportError("not connected")
        self._port.timeout = timeout
        try:
            return self._port.read(4096)
        except serial.SerialException as e:
            raise TransportError(f"Receive failed: {e}") from e
