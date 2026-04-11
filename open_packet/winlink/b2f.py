# open_packet/winlink/b2f.py
"""B2F (Binary Two-way Forward) protocol session handler for Winlink.

Implements the B2F session protocol used by Winlink RMS gateways.
The B2F protocol is documented at https://www.winlink.org/B2F

This implementation supports:
- Uncompressed message transfer (FW proposals)
- Basic session handshake (greeting / [WLNK-1.0] exchange)

LZH-compressed transfer (FC proposals) from the gateway is received but
logged as unsupported; uncompressed re-request is not currently implemented.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Callable, Optional

from open_packet.winlink.message import WinlinkMessage, parse_winlink_message

if TYPE_CHECKING:
    from open_packet.link.base import ConnectionBase

logger = logging.getLogger(__name__)

# B2F session timeouts
_SESSION_TIMEOUT = 60.0   # max wait for first byte
_IDLE_TIMEOUT = 30.0      # max silence between frames

# B2F version strings
_WL2K_GREETING_PREFIX = "WL2K"
_CLIENT_GREETING = "[WLNK-1.0]"

# B2F control commands
_CMD_FC = "FC"    # Compressed message proposal (incoming from gateway)
_CMD_FW = "FW"    # Uncompressed message proposal
_CMD_FF = "FF"    # No more proposals / end of proposal list
_CMD_FA = "FA"    # Accept proposal
_CMD_FR = "FR"    # Reject / defer proposal
_CMD_FQ = "FQ"    # Quit session
_CMD_FS = "FS"    # Status: total bytes being transferred

# Message size limit (10 MB uncompressed)
_MAX_MESSAGE_SIZE = 10 * 1024 * 1024


class B2FError(Exception):
    """Raised when a B2F session error occurs."""


class B2FSession:
    """Manages a single B2F protocol session over a ConnectionBase.

    Typical usage::

        session = B2FSession(connection, "W1AW", 10)
        session.handshake(is_telnet_cms=True)
        incoming = session.receive_proposals()
        messages = [session.receive_message(mid, size) for mid, size in incoming]
        session.send_proposals(outgoing_messages)
        session.finish()
    """

    def __init__(
        self,
        connection: "ConnectionBase",
        my_callsign: str,
        my_ssid: int,
        on_log: Optional[Callable[[str, str], None]] = None,
    ):
        self._conn = connection
        self._callsign = my_callsign.upper()
        self._ssid = my_ssid
        self._on_log = on_log  # callback(direction, text) for console logging
        self._buffer = ""

    def _log(self, direction: str, text: str) -> None:
        if self._on_log:
            self._on_log(direction, text)
        logger.debug("B2F %s: %s", direction, text)

    def _send(self, text: str) -> None:
        """Send a text line (appends CRLF)."""
        self._log(">", text)
        self._conn.send_frame((text + "\r\n").encode())

    def _recv_line(self, timeout: float = _IDLE_TIMEOUT) -> str:
        """Receive one CRLF-terminated line from the connection."""
        deadline = time.monotonic() + timeout
        while "\n" not in self._buffer and "\r" not in self._buffer:
            if time.monotonic() > deadline:
                raise B2FError(f"Timeout waiting for B2F data after {timeout}s")
            data = self._conn.receive_frame(timeout=1.0)
            if data:
                self._buffer += data.decode(errors="replace")
        # Extract one line
        for sep in ("\r\n", "\n", "\r"):
            idx = self._buffer.find(sep)
            if idx >= 0:
                line = self._buffer[:idx]
                self._buffer = self._buffer[idx + len(sep):]
                self._log("<", line)
                return line.strip()
        return ""

    def _recv_bytes(self, count: int, timeout: float = _SESSION_TIMEOUT) -> bytes:
        """Receive exactly *count* raw bytes from the connection.

        Drains any bytes already in self._buffer (from previous _recv_line calls)
        before reading from the connection, to handle the case where text-phase
        reads have pre-fetched binary data.
        """
        result = b""
        deadline = time.monotonic() + timeout
        # Drain any bytes already in the text buffer (e.g., MIME data
        # accidentally consumed by _recv_line during the FS-line check).
        if self._buffer:
            result += self._buffer.encode(errors="surrogateescape")
            self._buffer = ""
        while len(result) < count:
            if time.monotonic() > deadline:
                raise B2FError(f"Timeout reading {count} bytes (got {len(result)})")
            data = self._conn.receive_frame(timeout=1.0)
            if data:
                result += data
        return result[:count]

    def handshake(self, is_telnet_cms: bool = False) -> None:
        """Perform the B2F session handshake.

        For RF connections (via AX.25), the RMS gateway sends the WL2K
        greeting immediately after AX.25 connect.  For Telnet CMS, the
        server greeting is also sent first.

        After receiving the gateway greeting, the client responds with its
        callsign (Telnet CMS) or with [WLNK-1.0] (both modes).
        """
        # Read gateway greeting (e.g. "WL2K V2.1.5.0 <SID>")
        greeting = self._recv_line(timeout=_SESSION_TIMEOUT)
        if not greeting.startswith(_WL2K_GREETING_PREFIX):
            raise B2FError(f"Expected WL2K greeting, got: {greeting!r}")
        self._log("<", f"Gateway greeting: {greeting}")

        if is_telnet_cms:
            # Identify ourselves to the CMS server
            ident = (f"{self._callsign}-{self._ssid}"
                     if self._ssid != 0 else self._callsign)
            self._send(f"[{ident}]")
            # Read server capability response
            server_caps = self._recv_line()
            self._log("<", f"Server capabilities: {server_caps}")

        # Signal that we support WLNK (B2F) protocol
        self._send(_CLIENT_GREETING)

    def receive_proposals(self) -> list[tuple[str, int, bool]]:
        """Read gateway's message proposals.

        Returns a list of (mid, size, compressed) tuples.  Compressed=True
        means the gateway will send LZH-compressed data (FC proposal).
        Compressed=False means uncompressed (FW proposal).
        """
        proposals: list[tuple[str, int, bool]] = []
        while True:
            line = self._recv_line()
            if not line or line.startswith(_CMD_FF):
                break
            parts = line.split()
            if not parts:
                continue
            cmd = parts[0].upper()
            if cmd in (_CMD_FC, _CMD_FW):
                # FC EM <mid> <size> <uncompressed_size> <crc>
                # FW EM <mid> <size> 0 0
                if len(parts) < 4:
                    logger.warning("Malformed B2F proposal: %r", line)
                    continue
                mid = parts[2]
                try:
                    size = int(parts[3])
                except ValueError:
                    logger.warning("Bad size in B2F proposal: %r", line)
                    continue
                compressed = (cmd == _CMD_FC)
                proposals.append((mid, size, compressed))
            else:
                logger.debug("Unrecognised B2F line during proposal: %r", line)
        return proposals

    def accept_message(self, mid: str) -> None:
        """Send FA to accept a message proposal."""
        self._send(f"{_CMD_FA} EM {mid}")

    def reject_message(self, mid: str) -> None:
        """Send FR to reject/defer a message proposal."""
        self._send(f"{_CMD_FR} EM {mid}")

    def receive_message_data(self, size: int) -> str:
        """Read *size* bytes of uncompressed MIME message data.

        Returns the decoded MIME string.
        """
        raw = self._recv_bytes(size)
        return raw.decode(errors="replace")

    def receive_messages(self) -> list[WinlinkMessage]:
        """Convenience method: receive all messages from gateway proposals.

        Automatically handles uncompressed (FW) proposals and logs a warning
        for compressed (FC) proposals (which are skipped in this implementation).

        Returns list of parsed WinlinkMessage objects.
        """
        proposals = self.receive_proposals()
        messages: list[WinlinkMessage] = []
        for mid, size, compressed in proposals:
            if compressed:
                logger.warning(
                    "B2F: received FC (compressed) proposal for MID %s — "
                    "LZH decompression not yet supported; skipping",
                    mid,
                )
                self.reject_message(mid)
                continue
            if size > _MAX_MESSAGE_SIZE:
                logger.warning("B2F: message %s too large (%d bytes); skipping", mid, size)
                self.reject_message(mid)
                continue
            self.accept_message(mid)
            # Read FS (status) line if present
            status_line = self._recv_line()
            if status_line.startswith(_CMD_FS):
                pass  # FS <total_bytes> — informational only
            else:
                # Not an FS line; put it back in the buffer
                self._buffer = status_line + "\r\n" + self._buffer
            mime_str = self.receive_message_data(size)
            try:
                msg = parse_winlink_message(mime_str)
                messages.append(msg)
            except Exception:
                logger.exception("B2F: failed to parse message MID %s", mid)
        return messages

    def send_proposals(self, messages: list[WinlinkMessage]) -> None:
        """Propose and upload outgoing messages to the gateway.

        Uses FW (uncompressed) proposals for simplicity.
        """
        for msg in messages:
            if not msg.mime_str:
                logger.warning("B2F: message MID %s has no MIME content; skipping", msg.mid)
                continue
            mime_bytes = msg.mime_str.encode()
            size = len(mime_bytes)
            # FW EM <mid> <size> 0 0
            self._send(f"{_CMD_FW} EM {msg.mid} {size} 0 0")
            # Wait for gateway to accept (FA) or reject (FR)
            response = self._recv_line()
            if not response.startswith(_CMD_FA):
                logger.warning(
                    "B2F: gateway did not accept proposal for MID %s (got %r)",
                    msg.mid, response,
                )
                continue
            # Send FS with total byte count
            self._send(f"{_CMD_FS} {size}")
            # Send raw MIME bytes
            self._conn.send_frame(mime_bytes)
            self._log(">", f"[{size} bytes of MIME data for {msg.mid}]")

    def finish(self) -> None:
        """End the B2F session cleanly.

        Sends FF (no more proposals) then FQ (quit), and waits for the
        gateway's QU acknowledgement.
        """
        self._send(_CMD_FF)
        self._send(_CMD_FQ)
        try:
            response = self._recv_line(timeout=15.0)
            self._log("<", f"Session end: {response}")
        except B2FError:
            pass  # Timeout on QU is acceptable
