# open_packet/link/telnet.py
from __future__ import annotations
import re
import socket
import time

from open_packet.link.base import ConnectionBase, ConnectionError

# IAC stripping regex:
# 2-byte: IAC + single-byte command (NOP=\xf1, GA=\xf9, SE=\xf0, etc., range \xf0-\xfa)
# 3-byte: IAC + WILL/WONT/DO/DONT (\xfb-\xfe) + option byte
_IAC_RE = re.compile(
    b'\xff[\xf0-\xfa]|'   # 2-byte IAC commands
    b'\xff[\xfb-\xfe].'   # 3-byte option negotiations
)

TIMEOUT = 10.0


def _strip_iac(data: bytes) -> bytes:
    return _IAC_RE.sub(b'', data)


class TelnetLink(ConnectionBase):
    def __init__(self, host: str, port: int, username: str, password: str):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sock: socket.socket | None = None

    def connect(self, callsign: str, ssid: int, via_path=None) -> None:
        """Connect to Telnet BPQ node and log in. callsign/ssid/via_path are ignored."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        try:
            sock.connect((self._host, self._port))
            self._sock = sock
            self._read_until(b'user:')
            sock.sendall(self._username.encode() + b'\r\n')
            self._read_until(b'password:')
            sock.sendall(self._password.encode() + b'\r\n')
            self._read_until_prompt()
        except socket.timeout:
            sock.close()
            self._sock = None
            raise ConnectionError('Timed out during Telnet login')
        except ConnectionError:
            sock.close()
            self._sock = None
            raise
        except Exception as e:
            sock.close()
            self._sock = None
            raise ConnectionError(f'Telnet connect failed: {e}') from e

    def _read_until(self, token: bytes, timeout: float = TIMEOUT) -> bytes:
        """Accumulate recv() chunks (IAC-stripped) until token is found."""
        buf = b''
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                chunk = self._sock.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                raise ConnectionError('Connection closed during login')
            buf += _strip_iac(chunk)
            if token in buf:
                return buf
        raise ConnectionError(f'Timed out waiting for {token!r}')

    def _read_until_prompt(self, timeout: float = TIMEOUT) -> bytes:
        """Accumulate recv() chunks until IAC-stripped buffer ends with '>'."""
        buf = b''
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                chunk = self._sock.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                raise ConnectionError('Connection closed waiting for prompt')
            buf += _strip_iac(chunk)
            if buf.rstrip().endswith(b'>'):
                return buf
        raise ConnectionError('Timed out waiting for BPQ node prompt')

    def disconnect(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def send_frame(self, data: bytes) -> None:
        if self._sock is None:
            raise ConnectionError('Not connected')
        self._sock.sendall(data)

    def receive_frame(self, timeout: float = 5.0) -> bytes:
        if self._sock is None:
            return b''
        self._sock.settimeout(timeout)
        try:
            data = self._sock.recv(4096)
            return _strip_iac(data) if data else b''
        except socket.timeout:
            return b''
