from __future__ import annotations

import hashlib
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_GITHUB_API_BASE = "https://api.github.com"
_REPO = "loredous/open-packet"
_BRANCH = "main"
_FORMS_PREFIX = "forms/"
_RAW_BASE = "https://raw.githubusercontent.com"


class FormsUpdateError(Exception):
    pass


@dataclass
class UpdateResult:
    downloaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total_new_or_updated(self) -> int:
        return len(self.downloaded)


def _fetch_json(url: str, timeout: int = 15) -> object:
    """Fetch URL and return parsed JSON."""
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "open-packet/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise FormsUpdateError(f"HTTP {e.code} fetching {url}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise FormsUpdateError(f"Network error fetching {url}: {e.reason}") from e


def _fetch_bytes(url: str, timeout: int = 15) -> bytes:
    """Fetch URL and return raw bytes."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "open-packet/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise FormsUpdateError(f"HTTP {e.code} fetching {url}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise FormsUpdateError(f"Network error fetching {url}: {e.reason}") from e


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256(path.read_bytes())
    return h.hexdigest()


def _sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_blob_sha(data: bytes) -> str:
    """Compute git's SHA-1 blob hash for raw content bytes.

    Matches the SHA values returned by the GitHub tree API so that local files
    can be compared against the remote tree without downloading them first.
    """
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def _list_remote_form_files() -> list[dict]:
    """Return list of {path, sha} dicts for .yaml files under forms/ on main branch."""
    url = f"{_GITHUB_API_BASE}/repos/{_REPO}/git/trees/{_BRANCH}?recursive=1"
    data = _fetch_json(url)
    if not isinstance(data, dict) or "tree" not in data:
        raise FormsUpdateError("Unexpected response from GitHub tree API")
    result = []
    for entry in data["tree"]:
        if (
            entry.get("type") == "blob"
            and entry.get("path", "").startswith(_FORMS_PREFIX)
            and entry["path"].endswith(".yaml")
        ):
            result.append({"path": entry["path"], "sha": entry.get("sha", "")})
    return result


def _raw_url(repo_path: str) -> str:
    """Convert a repo-relative path to a raw.githubusercontent.com URL."""
    import urllib.parse
    encoded = urllib.parse.quote(repo_path)
    return f"{_RAW_BASE}/{_REPO}/{_BRANCH}/{encoded}"


def update_forms(
    forms_dir: Path,
    on_progress: Optional[Callable[[str], None]] = None,
) -> UpdateResult:
    """
    Sync form YAML files from the GitHub repo's main branch into ``forms_dir``.

    Downloads only files that are new or have changed (compared by SHA-256 of
    content).  Preserves any locally-added YAML files that do not exist in the
    remote tree.

    Args:
        forms_dir: Local directory where forms are stored.
        on_progress: Optional callback called with a short status string for
            each file processed.

    Returns:
        An ``UpdateResult`` with lists of downloaded / skipped / errored paths.
    """
    result = UpdateResult()

    try:
        remote_files = _list_remote_form_files()
    except FormsUpdateError as exc:
        result.errors.append(str(exc))
        return result

    for entry in remote_files:
        repo_path = entry["path"]
        # Strip leading "forms/" prefix to get the relative path within forms_dir
        rel_path = repo_path[len(_FORMS_PREFIX):]
        local_path = forms_dir / rel_path
        remote_sha = entry.get("sha", "")

        # Fast path: compare local file's git blob SHA with the remote tree SHA
        # to avoid downloading files that haven't changed.
        if local_path.exists() and remote_sha:
            if _git_blob_sha(local_path.read_bytes()) == remote_sha:
                result.skipped.append(rel_path)
                if on_progress:
                    on_progress(f"Unchanged: {rel_path}")
                continue

        try:
            remote_content = _fetch_bytes(_raw_url(repo_path))
        except FormsUpdateError as exc:
            logger.warning("Failed to fetch %s: %s", repo_path, exc)
            error_message = f"{rel_path}: {exc}"
            result.errors.append(error_message)
            if on_progress:
                on_progress(f"Error: {error_message}")
            continue

        # Write new or updated file
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(remote_content)
        result.downloaded.append(rel_path)
        logger.info("Downloaded form: %s", rel_path)
        if on_progress:
            on_progress(f"Downloaded: {rel_path}")

    return result
