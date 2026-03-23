# README Design Specification

**Date:** 2026-03-23
**Status:** Approved
**Project:** open-packet — README.md + LICENSE

---

## Overview

Design for the public-facing README.md and MIT LICENSE file, written ahead of the project's first GitHub upload. The README follows a narrative/welcoming structure (Option B) targeting both experienced CLI users and those new to packet radio or TUI tools.

---

## Structure

### 1. Header & Hero

- `# open-packet`
- Tagline: *An open-source packet messaging client for amateur radio operators.*
- Early-stage notice: brief note that this is v0.1 / early development, expect breaking changes
- Screenshot: `images/image.png`

### 2. Quickstart

- **Requirements note:**
  - Linux only (macOS/Windows not currently supported)
  - Python >= 3.11
  - A KISS-capable TNC connected via TCP or serial. Link to [Direwolf](https://github.com/wb2osz/direwolf) for users without hardware.
- Install via `uv tool install git+https://github.com/YOUR_USERNAME/open-packet` (package not yet on PyPI; git install is the primary method for v0.1)
- Create config at `~/.config/open-packet/config.yaml` (snippet showing both `kiss_tcp` and `kiss_serial` examples with inline comments)
- Run with `open-packet`
- Note that operator callsign and BBS node are configured interactively on first launch

### 3. How It Works

Short paragraph:
> open-packet connects to a BBS node over AX.25 packet radio via a KISS TNC, syncing your personal messages and bulletins to a local SQLite database. The core engine is interface-agnostic — the terminal client is the first frontend, with a web client and other interfaces planned.

### 4. Configuration

- Full `config.yaml` with inline comments
- Both TCP and serial connection examples
- Notes on default paths: `~/.config/open-packet/config.yaml` (config), `~/.local/share/open-packet/messages.db` (database)
- Mention that operator and node setup is done interactively on first launch; settings are accessible via `s` in the TUI

### 5. Development

Steps:
1. Clone and `uv sync`
2. `uv run open-packet`
3. `uv run pytest`
4. `uv run textual run --dev open_packet/ui/tui/app.py` for live reload + DOM inspector (launches `OpenPacketApp` directly, bypassing the `main()` entry point — config will be loaded from the default path)

### 6. Contributing

- Fork the repo, create a feature branch
- Write tests for new functionality
- Run `uv run pytest` before opening a PR
- Open a PR with a clear description
- No code of conduct at this time

### 7. License

- MIT — link to `LICENSE` file
- LICENSE file to be created with copyright: `Jeremy Banker - K0JLB`

---

## Files to Create/Modify

| File | Action |
|------|--------|
| `README.md` | Rewrite with new structure |
| `LICENSE` | Create with MIT license text, copyright Jeremy Banker - K0JLB, 2026 |

---

## Out of Scope

- Badges (no CI, package registry, or coverage set up yet)
- Full keybindings reference table (v0.1, subject to change)
- Roadmap section (exists in design spec; not needed in README at this stage)
- Code of conduct
