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
    _sha256_of_bytes,
    _sha256_of_file,
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

def test_sha256_of_bytes():
    data = b"hello"
    expected = hashlib.sha256(data).hexdigest()
    assert _sha256_of_bytes(data) == expected


def test_sha256_of_file(tmp_path):
    f = tmp_path / "test.yaml"
    data = b"content"
    f.write_bytes(data)
    expected = hashlib.sha256(data).hexdigest()
    assert _sha256_of_file(f) == expected


# ---------------------------------------------------------------------------
# update_forms – happy path
# ---------------------------------------------------------------------------

def test_update_forms_downloads_new_files(tmp_path):
    form1 = _yaml_bytes("Form 1")
    form2 = _yaml_bytes("Form 2")

    def fake_fetch_json(url, timeout=15):
        return _TREE_RESPONSE

    def fake_fetch_bytes(url, timeout=15):
        if "ics213" in url:
            return form1
        return form2

    with (
        patch("open_packet.forms.updater._fetch_json", side_effect=fake_fetch_json),
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

    # Pre-create local file with same content
    local_dir = tmp_path / "ICS USA Forms"
    local_dir.mkdir()
    local_file = local_dir / "ics213.yaml"
    local_file.write_bytes(form_data)

    # Use the actual git blob SHA so the fast-path comparison skips the download
    remote_sha = _git_blob_sha(form_data)
    partial_tree = {
        "tree": [
            {"type": "blob", "path": "forms/ICS USA Forms/ics213.yaml", "sha": remote_sha},
        ]
    }

    with (
        patch("open_packet.forms.updater._fetch_json", return_value=partial_tree),
        # _fetch_bytes should NOT be called since git blob SHA matches
        patch("open_packet.forms.updater._fetch_bytes", side_effect=AssertionError("should not download unchanged file")),
    ):
        result = update_forms(tmp_path)

    assert result.total_new_or_updated == 0
    assert len(result.skipped) == 1
    assert len(result.errors) == 0


def test_update_forms_updates_changed_files(tmp_path):
    old_content = b"old: content\nname: Old\ncategory: X\nfields:\n  - name: a\n    label: A\nsubject_template: s\nbody_template: b\n"
    new_content = b"new: content\nname: New\ncategory: X\nfields:\n  - name: a\n    label: A\nsubject_template: s\nbody_template: b\n"

    local_dir = tmp_path / "ICS USA Forms"
    local_dir.mkdir()
    local_file = local_dir / "ics213.yaml"
    local_file.write_bytes(old_content)

    partial_tree = {
        "tree": [
            {"type": "blob", "path": "forms/ICS USA Forms/ics213.yaml", "sha": "new"},
        ]
    }

    with (
        patch("open_packet.forms.updater._fetch_json", return_value=partial_tree),
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
    partial_tree = {
        "tree": [
            {"type": "blob", "path": "forms/ICS USA Forms/ics213.yaml", "sha": "abc"},
        ]
    }

    with (
        patch("open_packet.forms.updater._fetch_json", return_value=partial_tree),
        patch(
            "open_packet.forms.updater._fetch_bytes",
            side_effect=FormsUpdateError("Timeout"),
        ),
    ):
        result = update_forms(tmp_path)

    assert result.total_new_or_updated == 0
    assert len(result.errors) == 1
    assert "ICS USA Forms/ics213.yaml" in result.errors[0]


def test_update_forms_creates_subdirectories(tmp_path):
    form_data = _yaml_bytes()
    partial_tree = {
        "tree": [
            {
                "type": "blob",
                "path": "forms/Deep/Nested/Dir/form.yaml",
                "sha": "abc",
            }
        ]
    }

    with (
        patch("open_packet.forms.updater._fetch_json", return_value=partial_tree),
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
    # No files should have been written
    assert list(tmp_path.iterdir()) == []


def test_update_forms_progress_callback(tmp_path):
    form_data = _yaml_bytes()
    partial_tree = {
        "tree": [
            {"type": "blob", "path": "forms/ICS USA Forms/ics213.yaml", "sha": "abc"},
        ]
    }

    progress_messages: list[str] = []

    with (
        patch("open_packet.forms.updater._fetch_json", return_value=partial_tree),
        patch("open_packet.forms.updater._fetch_bytes", return_value=form_data),
    ):
        result = update_forms(tmp_path, on_progress=progress_messages.append)

    assert result.total_new_or_updated == 1
    assert any("Downloaded" in m for m in progress_messages)


def test_update_forms_unexpected_tree_response(tmp_path):
    with patch("open_packet.forms.updater._fetch_json", return_value={"bad": "data"}):
        result = update_forms(tmp_path)

    assert len(result.errors) == 1


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
