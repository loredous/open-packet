# open_packet/node/winlink.py
"""WinlinkNode: NodeBase implementation for Winlink RMS gateways using B2F protocol.

Supports two connection modes:
  - RF via AX.25: The underlying connection is an AX25Connection/KISSLink.
    After AX.25 connect the RMS gateway immediately starts B2F handshake.
  - Telnet CMS: The underlying connection is a WinlinkTelnetLink (direct TCP
    to cms.winlink.org or another Winlink CMS server).

Features not applicable to Winlink (bulletins, files, linked nodes) return
empty results rather than raising errors.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional

from open_packet.node.base import (
    FileHeader, Message, MessageHeader, NodeBase, NodeError,
)
from open_packet.winlink.b2f import B2FSession
from open_packet.winlink.message import (
    WinlinkMessage, format_winlink_message, normalize_winlink_address,
)

if TYPE_CHECKING:
    from open_packet.link.base import ConnectionBase

logger = logging.getLogger(__name__)


class WinlinkNode(NodeBase):
    """NodeBase implementation for Winlink RMS gateways.

    Communicates with a Winlink gateway using the B2F protocol.

    :param connection: An established ConnectionBase (AX25Connection for RF,
        or WinlinkTelnetLink for internet CMS).
    :param my_callsign: Operator's callsign (without SSID).
    :param my_ssid: Operator's SSID (0–15).
    :param winlink_password: Operator's Winlink password (currently stored
        for future use in challenge-response authentication).
    :param is_telnet_cms: True if connecting to an internet CMS server
        (affects handshake flow).
    :param on_log: Optional callback(direction, text) for console logging.
    """

    def __init__(
        self,
        connection: "ConnectionBase",
        my_callsign: str,
        my_ssid: int,
        winlink_password: str = "",
        is_telnet_cms: bool = False,
        on_log: Optional[Callable[[str, str], None]] = None,
    ):
        self._conn = connection
        self._callsign = my_callsign.upper()
        self._ssid = my_ssid
        self._password = winlink_password
        self._is_telnet_cms = is_telnet_cms
        self._on_log = on_log

        # Messages received during the last sync; keyed by mid
        self._inbox: dict[str, WinlinkMessage] = {}
        self._session: Optional[B2FSession] = None

    def _make_session(self) -> B2FSession:
        return B2FSession(
            connection=self._conn,
            my_callsign=self._callsign,
            my_ssid=self._ssid,
            on_log=self._on_log,
        )

    # --- NodeBase interface ---

    def connect_node(self) -> None:
        """Perform B2F session handshake with the gateway."""
        self._session = self._make_session()
        try:
            self._session.handshake(is_telnet_cms=self._is_telnet_cms)
        except Exception as exc:
            raise NodeError(f"Winlink B2F handshake failed: {exc}") from exc

    def wait_for_prompt(self) -> None:
        """No-op for Winlink: the gateway does not send a BBS-style prompt."""

    def list_linked_nodes(self) -> list:
        """Winlink gateways do not expose neighboring nodes; always returns []."""
        return []

    def list_messages(self) -> list[MessageHeader]:
        """Download all pending Winlink messages from the gateway.

        Returns MessageHeader objects for each received message and caches
        the full WinlinkMessage for subsequent read_message() calls.
        """
        if self._session is None:
            raise NodeError("Winlink session not started; call connect_node() first")
        self._inbox.clear()
        try:
            wl_messages = self._session.receive_messages()
        except Exception as exc:
            raise NodeError(f"Failed to receive Winlink messages: {exc}") from exc

        headers = []
        for wl_msg in wl_messages:
            self._inbox[wl_msg.mid] = wl_msg
            headers.append(MessageHeader(
                bbs_id=wl_msg.mid,
                to_call=wl_msg.to_addr,
                from_call=wl_msg.from_addr,
                subject=wl_msg.subject,
                date_str=wl_msg.date.isoformat(),
            ))
        return headers

    def read_message(self, bbs_id: str) -> Message:
        """Return a previously downloaded message by its MID.

        Messages are cached by list_messages(); this just retrieves the cache.
        """
        wl_msg = self._inbox.get(bbs_id)
        if wl_msg is None:
            raise NodeError(f"Message MID {bbs_id!r} not found in Winlink inbox cache")
        header = MessageHeader(
            bbs_id=wl_msg.mid,
            to_call=wl_msg.to_addr,
            from_call=wl_msg.from_addr,
            subject=wl_msg.subject,
            date_str=wl_msg.date.isoformat(),
        )
        return Message(header=header, body=wl_msg.body, timestamp=wl_msg.date)

    def send_message(self, to_call: str, subject: str, body: str) -> None:
        """Send a single Winlink message to the gateway.

        *to_call* may be a bare callsign (e.g. "K0ABC") or a full Winlink
        address (e.g. "K0ABC@winlink.org").  Bare callsigns are automatically
        suffixed with @winlink.org.
        """
        if self._session is None:
            raise NodeError("Winlink session not started; call connect_node() first")
        from_addr = normalize_winlink_address(
            f"{self._callsign}-{self._ssid}" if self._ssid else self._callsign
        )
        to_addr = normalize_winlink_address(to_call)
        wl_msg = format_winlink_message(
            from_addr=from_addr,
            to_addr=to_addr,
            subject=subject,
            body=body,
        )
        try:
            self._session.send_proposals([wl_msg])
        except Exception as exc:
            raise NodeError(f"Failed to send Winlink message: {exc}") from exc

    def delete_message(self, bbs_id: str) -> None:
        """Winlink messages are managed by the network; deletion is a no-op."""
        logger.debug("WinlinkNode.delete_message: not supported, ignoring MID %s", bbs_id)

    def list_bulletins(self, category: str = "") -> list[MessageHeader]:
        """Winlink gateways do not support BBS bulletins; always returns []."""
        return []

    def read_bulletin(self, bbs_id: str) -> Message:
        """Not supported on Winlink."""
        raise NodeError("Bulletins are not supported by Winlink gateways")

    def post_bulletin(self, category: str, subject: str, body: str) -> None:
        """Not supported on Winlink."""
        raise NodeError("Bulletins are not supported by Winlink gateways")

    def list_files(self, directory: str = "") -> list[FileHeader]:
        """Winlink gateways do not support file directories; always returns []."""
        return []

    def read_file(self, filename: str) -> str:
        """Not supported on Winlink."""
        raise NodeError("File downloads are not supported by Winlink gateways")

    def finish_session(self) -> None:
        """Cleanly terminate the B2F session.

        Call this before disconnecting the underlying connection.
        """
        if self._session is not None:
            try:
                self._session.finish()
            except Exception:
                logger.debug("Error finishing B2F session", exc_info=True)
            finally:
                self._session = None
