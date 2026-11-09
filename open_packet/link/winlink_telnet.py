# open_packet/link/winlink_telnet.py
"""WinlinkTelnetLink: ConnectionBase for direct TCP connections to a Winlink CMS server.

Provides a raw byte channel to a Winlink CMS server (e.g. cms.winlink.org:8772)
without any KISS framing or AX.25 encapsulation.  The B2F protocol runs
directly over this connection.

Unlike TelnetLink (which is designed for BPQ32 text-mode BBS access with
IAC option negotiation stripping), WinlinkTelnetLink is a simple TCP wrapper
intended for Winlink-protocol connections.
"""
from __future__ import annotations

import socket
import time
from typing import Optional, Callable

from open_packet.link.base import ConnectionBase

_DEFAULT_TIMEOUT = 30.0   # seconds
_RECV_BUFSIZE = 4096


class WinlinkTelnetLink(ConnectionBase):
    """Direct TCP connection to a Winlink CMS server.

    :param host: Hostname or IP of the CMS server (e.g. 'cms.winlink.org').
    :param port: TCP port (default Winlink telnet port is 8772).
    :param on_frame: Optional callback(direction, summary) for debug logging.
    """

    def __init__(
        self,
        host: str,
        port: int = 8772,
        on_frame: Optional[Callable[[str, str], None]] = None,
    ):
        self._host = host
        self._port = port
        self._on_frame = on_frame
        self._sock: Optional[socket.socket] = None
        self._recv_buffer = b""

    def connect(
        self,
        callsign: str,
        ssid: int,
        via_path=None,
    ) -> None:
        """Open a TCP connection to the CMS server.

        *callsign* and *ssid* are stored for reference but the Winlink CMS
        authentication is handled at the B2F session layer (WinlinkNode /
        B2FSession.handshake()), not here.
        """
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(_DEFAULT_TIMEOUT)
        try:
            self._sock.connect((self._host, self._port))
        except OSError as exc:
            self._sock = None
            raise ConnectionError(
                f"Cannot connect to Winlink CMS {self._host}:{self._port}: {exc}"
            ) from exc
        self._recv_buffer = b""
        if self._on_frame:
            self._on_frame(">", f"TCP connected to {self._host}:{self._port}")

    def disconnect(self) -> None:
        """Close the TCP connection."""
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            finally:
                self._sock = None
        self._recv_buffer = b""

    def send_frame(self, data: bytes) -> None:
        """Send raw bytes to the CMS server."""
        if not self._sock:
            raise ConnectionError("WinlinkTelnetLink not connected")
        if self._on_frame:
            self._on_frame(">", data.decode(errors="replace").strip())
        self._sock.sendall(data)

    def receive_frame(self, timeout: float = 5.0) -> Optional[bytes]:
        """Receive available bytes from the CMS server.

        Returns bytes if data is available, None on timeout.
        """
        if not self._sock:
            return None
        self._sock.settimeout(timeout)
        try:
            data = self._sock.recv(_RECV_BUFSIZE)
            if data and self._on_frame:
                self._on_frame("<", data.decode(errors="replace").strip())
            return data if data else None
        except socket.timeout:
            return None
        except OSError:
            return None
