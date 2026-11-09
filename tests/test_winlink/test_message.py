# tests/test_winlink/test_message.py
"""Tests for the Winlink message format module."""
from datetime import datetime, timezone

import pytest

from open_packet.winlink.message import (
    format_winlink_message,
    generate_mid,
    normalize_winlink_address,
    parse_winlink_message,
    validate_winlink_address,
)


class TestGenerateMid:
    def test_length(self):
        mid = generate_mid()
        assert len(mid) == 12

    def test_uppercase_alphanumeric(self):
        mid = generate_mid()
        assert mid.isalnum()
        assert mid == mid.upper()

    def test_unique(self):
        mids = {generate_mid() for _ in range(100)}
        # Statistically, all 100 should be unique
        assert len(mids) == 100


class TestValidateWinlinkAddress:
    def test_bare_callsign(self):
        assert validate_winlink_address("W1AW") is True

    def test_callsign_with_ssid(self):
        assert validate_winlink_address("W1AW-10") is True

    def test_callsign_at_domain(self):
        assert validate_winlink_address("W1AW@winlink.org") is True

    def test_callsign_ssid_at_domain(self):
        assert validate_winlink_address("K0ABC-5@winlink.org") is True

    def test_invalid_empty(self):
        assert validate_winlink_address("") is False

    def test_invalid_spaces(self):
        assert validate_winlink_address("W1 AW") is False

    def test_lowercase_accepted(self):
        assert validate_winlink_address("w1aw") is True


class TestNormalizeWinlinkAddress:
    def test_appends_winlink_org(self):
        result = normalize_winlink_address("W1AW")
        assert result == "W1AW@WINLINK.ORG"

    def test_preserves_existing_domain(self):
        result = normalize_winlink_address("W1AW@winlink.org")
        assert "@" in result
        assert result.startswith("W1AW@")

    def test_uppercase(self):
        result = normalize_winlink_address("k0abc")
        assert result.startswith("K0ABC@")

    def test_strips_whitespace(self):
        result = normalize_winlink_address("  W1AW  ")
        assert result.startswith("W1AW@")

    def test_ssid_preserved(self):
        result = normalize_winlink_address("W1AW-10")
        assert result.startswith("W1AW-10@")


class TestFormatWinlinkMessage:
    def test_basic(self):
        msg = format_winlink_message(
            from_addr="W1AW",
            to_addr="K0ABC",
            subject="Test",
            body="Hello",
        )
        assert msg.subject == "Test"
        assert msg.body == "Hello"
        assert "@" in msg.from_addr
        assert "@" in msg.to_addr
        assert len(msg.mid) == 12
        assert msg.mime_str != ""

    def test_mime_contains_headers(self):
        msg = format_winlink_message(
            from_addr="W1AW@winlink.org",
            to_addr="K0ABC@winlink.org",
            subject="Testing",
            body="Body text",
        )
        assert "From:" in msg.mime_str
        assert "To:" in msg.mime_str
        assert "Subject: Testing" in msg.mime_str
        assert "Message-ID:" in msg.mime_str
        assert "Body text" in msg.mime_str

    def test_custom_mid(self):
        msg = format_winlink_message("W1AW", "K0ABC", "S", "B", mid="TESTMID00001")
        assert msg.mid == "TESTMID00001"
        assert "TESTMID00001" in msg.mime_str

    def test_custom_date(self):
        dt = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
        msg = format_winlink_message("W1AW", "K0ABC", "S", "B", date=dt)
        assert msg.date == dt


class TestParseWinlinkMessage:
    def test_round_trip(self):
        original = format_winlink_message(
            from_addr="W1AW",
            to_addr="K0ABC",
            subject="Round Trip Test",
            body="This is the body.",
        )
        parsed = parse_winlink_message(original.mime_str)
        assert parsed.subject == "Round Trip Test"
        assert "This is the body." in parsed.body
        assert parsed.mid == original.mid

    def test_from_and_to_fields(self):
        original = format_winlink_message(
            from_addr="W1AW@winlink.org",
            to_addr="K0ABC@winlink.org",
            subject="Test",
            body="Body",
        )
        parsed = parse_winlink_message(original.mime_str)
        assert "W1AW" in parsed.from_addr
        assert "K0ABC" in parsed.to_addr

    def test_missing_date_uses_now(self):
        bare_mime = "From: W1AW@winlink.org\r\nTo: K0ABC@winlink.org\r\nSubject: No Date\r\n\r\nBody"
        parsed = parse_winlink_message(bare_mime)
        # Should not raise; date should be recent
        assert isinstance(parsed.date, datetime)

    def test_empty_mid_generates_one(self):
        bare_mime = "From: W1AW@winlink.org\r\nTo: K0ABC@winlink.org\r\nSubject: S\r\n\r\nB"
        parsed = parse_winlink_message(bare_mime)
        assert len(parsed.mid) == 12
