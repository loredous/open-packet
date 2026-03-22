from __future__ import annotations
import socket
from open_packet.transport.base import TransportBase, TransportError


class TCPTransport(TransportBase):
    def __init__(self, host: str, port: int):
        self._host = host
        self._port = port
        self._sock: socket.socket | None = None

    def connect(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        try:
            sock.connect((self._host, self._port))
        except (ConnectionRefusedError, OSError) as e:
            sock.close()
            raise TransportError(f"Failed to connect to {self._host}:{self._port}: {e}") from e
        self._sock = sock

    def disconnect(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def send_bytes(self, data: bytes) -> None:
        if not self._sock:
            raise TransportError("not connected")
        try:
            self._sock.sendall(data)
        except OSError as e:
            raise TransportError(f"Send failed: {e}") from e

    def receive_bytes(self, timeout: float = 5.0) -> bytes:
        if not self._sock:
            raise TransportError("not connected")
        self._sock.settimeout(timeout)
        try:
            data = self._sock.recv(4096)
            if not data:
                raise TransportError("Connection closed by remote")
            return data
        except socket.timeout:
            return b""
        except OSError as e:
            raise TransportError(f"Receive failed: {e}") from e
