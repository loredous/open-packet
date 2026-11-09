# open_packet/winlink/message.py
"""Winlink message format: standard Winlink/MIME-based message encoding and parsing.

Winlink messages use a MIME-based format with specific required headers.
The message format is documented at https://www.winlink.org/content/winlink_message_format_specification
"""
from __future__ import annotations

import random
import re
import string
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email import message_from_string
from email.utils import format_datetime, parsedate_to_datetime
from typing import Optional


_MID_CHARS = string.ascii_uppercase + string.digits
_WINLINK_DOMAIN = "winlink.org"
_WINLINK_ADDRESS_RE = re.compile(
    r'^[A-Z0-9][-A-Z0-9]{0,5}(-\d{1,2})?(@[A-Z0-9._-]+)?$',
    re.IGNORECASE,
)


def generate_mid() -> str:
    """Generate a Winlink message ID: 12 uppercase alphanumeric characters."""
    return "".join(random.choices(_MID_CHARS, k=12))


def normalize_winlink_address(address: str) -> str:
    """Normalize a Winlink address.

    - Converts to uppercase.
    - Appends '@WINLINK.ORG' if no domain is specified.
    """
    address = address.strip().upper()
    if "@" not in address:
        address = f"{address}@{_WINLINK_DOMAIN.upper()}"
    return address


def validate_winlink_address(address: str) -> bool:
    """Return True if *address* is a valid Winlink address (CALLSIGN[@DOMAIN])."""
    address = address.strip()
    # Strip domain for callsign validation
    if "@" in address:
        callsign, domain = address.rsplit("@", 1)
    else:
        callsign = address
    return bool(_WINLINK_ADDRESS_RE.match(callsign))


@dataclass
class WinlinkMessage:
    """Represents a single Winlink message in MIME format."""
    mid: str                        # 12-char message ID
    date: datetime                  # UTC datetime
    from_addr: str                  # e.g. W1AW@winlink.org
    to_addr: str                    # e.g. K0ABC@winlink.org
    subject: str
    body: str
    # Raw MIME text (set when parsed from wire; generated when formatting)
    mime_str: str = field(default="", repr=False)


def parse_winlink_message(mime_str: str) -> WinlinkMessage:
    """Parse a Winlink MIME message string into a WinlinkMessage.

    Extracts MID from Message-ID header, date from Date header, and
    addresses from From/To headers.
    """
    msg = message_from_string(mime_str)

    # Extract MID from Message-ID header: <MID@winlink.org> → MID
    raw_mid = msg.get("Message-ID", "")
    mid = raw_mid.strip("<>").split("@")[0] if raw_mid else generate_mid()

    # Parse date
    date_str = msg.get("Date", "")
    try:
        date = parsedate_to_datetime(date_str)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
    except Exception:
        date = datetime.now(timezone.utc)

    from_addr = msg.get("From", "").strip()
    to_addr = msg.get("To", "").strip()
    subject = msg.get("Subject", "").strip()

    # Extract body (plain text only for v1)
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
        elif isinstance(msg.get_payload(), str):
            body = msg.get_payload()

    return WinlinkMessage(
        mid=mid,
        date=date,
        from_addr=from_addr,
        to_addr=to_addr,
        subject=subject,
        body=body,
        mime_str=mime_str,
    )


def format_winlink_message(
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    mid: Optional[str] = None,
    date: Optional[datetime] = None,
) -> WinlinkMessage:
    """Create a WinlinkMessage and generate its MIME representation.

    Returns a WinlinkMessage with `mime_str` populated.
    """
    if mid is None:
        mid = generate_mid()
    if date is None:
        date = datetime.now(timezone.utc)

    from_addr = normalize_winlink_address(from_addr)
    to_addr = normalize_winlink_address(to_addr)

    # Build RFC 2822-compliant MIME message
    lines = [
        f"Date: {format_datetime(date)}",
        f"From: {from_addr}",
        f"To: {to_addr}",
        f"Subject: {subject}",
        f"Message-ID: <{mid}@{_WINLINK_DOMAIN}>",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=UTF-8",
        "",
        body,
    ]
    mime_str = "\r\n".join(lines)

    return WinlinkMessage(
        mid=mid,
        date=date,
        from_addr=from_addr,
        to_addr=to_addr,
        subject=subject,
        body=body,
        mime_str=mime_str,
    )
