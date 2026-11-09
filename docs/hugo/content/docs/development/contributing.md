---
title: "Contributing"
description: "How to contribute to open-packet"
weight: 2
---

# Contributing

Contributions are welcome. This page describes how to set up a development environment and the conventions used in this project.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/loredous/open-packet.git
cd open-packet

# Install dependencies (including dev dependencies)
uv sync

# Run the application
uv run open-packet

# Run the full test suite
uv run pytest

# Run a specific test file
uv run pytest tests/test_store/test_store.py

# Run a single test
uv run pytest tests/test_store/test_store.py::test_list_outbox_excludes_sent_and_deleted

# Run with Textual's live-reload and DOM inspector
uv run textual run --dev open_packet/ui/tui/app.py
```

## Project Conventions

- **No global state** — each layer communicates only with its immediate neighbours via well-defined interfaces
- **Tests for new code** — all new functionality should have test coverage in `tests/`
- **Migration pattern** — SQLite schema migrations use `ALTER TABLE ... ADD COLUMN` with `except sqlite3.OperationalError: pass`; never use `executescript()`
- **Async tests** — `asyncio_mode = "auto"` is set in `pyproject.toml`; async tests do not need `@pytest.mark.asyncio`

## Submitting Changes

1. Fork the repository and create a feature branch
2. Write tests for new functionality
3. Run `uv run pytest` — all tests must pass
4. Open a pull request with a clear description of the change

## Updating Documentation

When making changes to the application, update the relevant documentation pages in `docs/hugo/content/`:

| Change type | Documentation to update |
|-------------|------------------------|
| New feature | Add or update page in `user-guide/` |
| New keyboard shortcut | Update `reference/keyboard-shortcuts.md` |
| Config file change | Update `reference/configuration.md` |
| Architecture change | Update `development/architecture.md` |
| New command or event | Update `development/architecture.md` |

To preview the documentation locally:

```bash
# Install Hugo (see https://gohugo.io/installation/)
# Then, from the repo root:
cd docs/hugo
git submodule update --init --recursive
hugo server
```

Open `http://localhost:1313` in your browser.
