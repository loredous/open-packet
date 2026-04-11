"""Tests for the forms updater module."""
from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from open_packet.forms.updater import (
    FormsUpdateError,
    UpdateResult,
    _git_blob_sha,
    update_forms,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _yaml_bytes(name: str = "Test Form") -> bytes:
    return (
        f"name: {name}\n"
        "category: Test\n"
        "fields:\n"
        "  - name: msg\n"
        "    label: Message\n"
        "    required: true\n"
        "subject_template: 'Subject'\n"
        "body_template: '{{ msg }}'\n"
    ).encode()


_TREE_RESPONSE = {
    "tree": [
        {"type": "blob", "path": "forms/ICS USA Forms/ics213.yaml", "sha": "abc123"},
        {"type": "blob", "path": "forms/General Forms/quick.yaml", "sha": "def456"},
        {"type": "blob", "path": "README.md", "sha": "ghi789"},  # should be ignored
        {"type": "tree", "path": "forms/ICS USA Forms", "sha": "xxx"},  # dir; ignore
    ]
}


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------

def test_git_blob_sha_matches_git_formula():
    data = b"hello"
    header = f"blob {len(data)}\0".encode()
    expected = hashlib.sha1(header + data).hexdigest()
    assert _git_blob_sha(data) == expected


def test_git_blob_sha_empty():
    data = b""
    header = b"blob 0\0"
    expected = hashlib.sha1(header + data).hexdigest()
    assert _git_blob_sha(data) == expected


# ---------------------------------------------------------------------------
# update_forms – happy path
# ---------------------------------------------------------------------------

def test_update_forms_downloads_new_files(tmp_path):
    form1 = _yaml_bytes("Form 1")
    form2 = _yaml_bytes("Form 2")

    tree = {
        "tree": [
            # SHAs won't match any local file (no local files exist yet)
            {"type": "blob", "path": "forms/ICS USA Forms/ics213.yaml", "sha": "abc123"},
            {"type": "blob", "path": "forms/General Forms/quick.yaml", "sha": "def456"},
        ]
    }

    def fake_fetch_bytes(url, timeout=15):
        if "ics213" in url:
            return form1
        return form2

    with (
        patch("open_packet.forms.updater._fetch_json", return_value=tree),
        patch("open_packet.forms.updater._fetch_bytes", side_effect=fake_fetch_bytes),
    ):
        result = update_forms(tmp_path)

    assert result.total_new_or_updated == 2
    assert len(result.skipped) == 0
    assert len(result.errors) == 0

    assert (tmp_path / "ICS USA Forms" / "ics213.yaml").read_bytes() == form1
    assert (tmp_path / "General Forms" / "quick.yaml").read_bytes() == form2


def test_update_forms_skips_unchanged_files(tmp_path):
    form_data = _yaml_bytes("Unchanged Form")
    remote_sha = _git_blob_sha(form_data)  # compute the real git-blob SHA

    # Pre-create local file with the same content
    local_dir = tmp_path / "ICS USA Forms"
    local_dir.mkdir()
    (local_dir / "ics213.yaml").write_bytes(form_data)

    tree = {
        "tree": [
            {"type": "blob", "path": "forms/ICS USA Forms/ics213.yaml", "sha": remote_sha},
        ]
    }

    with (
        patch("open_packet.forms.updater._fetch_json", return_value=tree),
        patch("open_packet.forms.updater._fetch_bytes") as mock_bytes,
    ):
        result = update_forms(tmp_path)

    # File is unchanged — _fetch_bytes must never be called
    mock_bytes.assert_not_called()
    assert result.total_new_or_updated == 0
    assert len(result.skipped) == 1
    assert len(result.errors) == 0


def test_update_forms_updates_changed_files(tmp_path):
    old_content = b"old: content\nname: Old\ncategory: X\nfields:\n  - name: a\n    label: A\nsubject_template: s\nbody_template: b\n"
    new_content = b"new: content\nname: New\ncategory: X\nfields:\n  - name: a\n    label: A\nsubject_template: s\nbody_template: b\n"

    # remote SHA reflects new_content
    remote_sha = _git_blob_sha(new_content)

    local_dir = tmp_path / "ICS USA Forms"
    local_dir.mkdir()
    local_file = local_dir / "ics213.yaml"
    local_file.write_bytes(old_content)

    tree = {
        "tree": [
            {"type": "blob", "path": "forms/ICS USA Forms/ics213.yaml", "sha": remote_sha},
        ]
    }

    with (
        patch("open_packet.forms.updater._fetch_json", return_value=tree),
        patch("open_packet.forms.updater._fetch_bytes", return_value=new_content),
    ):
        result = update_forms(tmp_path)

    assert result.total_new_or_updated == 1
    assert len(result.skipped) == 0
    assert local_file.read_bytes() == new_content


# ---------------------------------------------------------------------------
# update_forms – error handling
# ---------------------------------------------------------------------------

def test_update_forms_network_error_on_tree(tmp_path):
    with patch(
        "open_packet.forms.updater._fetch_json",
        side_effect=FormsUpdateError("Connection refused"),
    ):
        result = update_forms(tmp_path)

    assert result.total_new_or_updated == 0
    assert len(result.errors) == 1
    assert "Connection refused" in result.errors[0]


def test_update_forms_network_error_on_file_download(tmp_path):
    tree = {
        "tree": [
            {"type": "blob", "path": "forms/ICS USA Forms/ics213.yaml", "sha": "abc"},
        ]
    }

    with (
        patch("open_packet.forms.updater._fetch_json", return_value=tree),
        patch(
            "open_packet.forms.updater._fetch_bytes",
            side_effect=FormsUpdateError("Timeout"),
        ),
    ):
        result = update_forms(tmp_path)

    assert result.total_new_or_updated == 0
    assert len(result.errors) == 1
    # Error message now includes both path and reason
    assert "ICS USA Forms/ics213.yaml" in result.errors[0]
    assert "Timeout" in result.errors[0]


def test_update_forms_creates_subdirectories(tmp_path):
    form_data = _yaml_bytes()
    tree = {
        "tree": [
            {
                "type": "blob",
                "path": "forms/Deep/Nested/Dir/form.yaml",
                "sha": "abc",
            }
        ]
    }

    with (
        patch("open_packet.forms.updater._fetch_json", return_value=tree),
        patch("open_packet.forms.updater._fetch_bytes", return_value=form_data),
    ):
        result = update_forms(tmp_path)

    assert result.total_new_or_updated == 1
    assert (tmp_path / "Deep" / "Nested" / "Dir" / "form.yaml").exists()


def test_update_forms_ignores_non_forms_entries(tmp_path):
    """Files outside forms/ prefix and non-.yaml files should be ignored."""
    tree = {
        "tree": [
            {"type": "blob", "path": "README.md", "sha": "a"},
            {"type": "blob", "path": "open_packet/forms/loader.py", "sha": "b"},
            {"type": "blob", "path": "forms/ICS USA Forms/ics213.html", "sha": "c"},
        ]
    }

    with (
        patch("open_packet.forms.updater._fetch_json", return_value=tree),
        patch("open_packet.forms.updater._fetch_bytes", return_value=b""),
    ):
        result = update_forms(tmp_path)

    assert result.total_new_or_updated == 0
    assert len(result.errors) == 0
    assert list(tmp_path.iterdir()) == []


def test_update_forms_progress_callback(tmp_path):
    form_data = _yaml_bytes()
    tree = {
        "tree": [
            {"type": "blob", "path": "forms/ICS USA Forms/ics213.yaml", "sha": "abc"},
        ]
    }

    progress_messages: list[str] = []

    with (
        patch("open_packet.forms.updater._fetch_json", return_value=tree),
        patch("open_packet.forms.updater._fetch_bytes", return_value=form_data),
    ):
        result = update_forms(tmp_path, on_progress=progress_messages.append)

    assert result.total_new_or_updated == 1
    assert any("Downloaded" in m for m in progress_messages)


def test_update_forms_unexpected_tree_response(tmp_path):
    with patch("open_packet.forms.updater._fetch_json", return_value={"bad": "data"}):
        result = update_forms(tmp_path)

    assert len(result.errors) == 1


def test_update_forms_progress_callback_on_skip(tmp_path):
    form_data = _yaml_bytes()
    remote_sha = _git_blob_sha(form_data)

    local_dir = tmp_path / "ICS USA Forms"
    local_dir.mkdir()
    (local_dir / "ics213.yaml").write_bytes(form_data)

    tree = {
        "tree": [
            {"type": "blob", "path": "forms/ICS USA Forms/ics213.yaml", "sha": remote_sha},
        ]
    }

    progress_messages: list[str] = []

    with patch("open_packet.forms.updater._fetch_json", return_value=tree):
        result = update_forms(tmp_path, on_progress=progress_messages.append)

    assert result.total_new_or_updated == 0
    assert any("Unchanged" in m for m in progress_messages)


def test_update_forms_error_message_includes_reason(tmp_path):
    """Per-file error strings must include both the path and the exception message."""
    tree = {
        "tree": [
            {"type": "blob", "path": "forms/ICS USA Forms/ics213.yaml", "sha": "abc"},
        ]
    }

    with (
        patch("open_packet.forms.updater._fetch_json", return_value=tree),
        patch(
            "open_packet.forms.updater._fetch_bytes",
            side_effect=FormsUpdateError("HTTP 403: Forbidden"),
        ),
    ):
        result = update_forms(tmp_path)

    assert len(result.errors) == 1
    assert "ICS USA Forms/ics213.yaml" in result.errors[0]
    assert "HTTP 403: Forbidden" in result.errors[0]


# ---------------------------------------------------------------------------
# UpdateResult dataclass
# ---------------------------------------------------------------------------

def test_update_result_total_new_or_updated():
    r = UpdateResult(downloaded=["a", "b"], skipped=["c"], errors=[])
    assert r.total_new_or_updated == 2


def test_update_result_defaults():
    r = UpdateResult()
    assert r.downloaded == []
    assert r.skipped == []
    assert r.errors == []
    assert r.total_new_or_updated == 0
