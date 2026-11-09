---
title: "Keyboard Shortcuts"
description: "All keyboard shortcuts available in the TUI"
weight: 1
---

# Keyboard Shortcuts

All keyboard shortcuts available in the main open-packet TUI are listed below.

## Main Screen

| Shortcut | Action | Description |
|----------|--------|-------------|
| **Ctrl+C** | Send/Receive | Connect to the BBS and synchronise messages |
| **Ctrl+N** | New... | Open the New Item picker (message, bulletin, or form message — see below) |
| **Ctrl+T** | Terminal Connect | Open the node picker for a terminal session |
| **Ctrl+F** | Search | Open the search modal to find messages and bulletins |
| **Ctrl+R** | Reply | Reply to the selected message |
| **Ctrl+X** | Delete | Delete the selected message (with confirmation) |
| **Ctrl+A** | Archive / Unarchive | Move selected message to/from Archive |
| **Ctrl+U** | Queue Retrieval | Mark (or unmark) the selected bulletin for body retrieval |
| **Ctrl+S** | Settings | Open the Settings screen |
| **Ctrl+D** | Disconnect | Disconnect the current terminal session |
| **`` ` ``** | Console | Toggle the AX.25 frame console panel |
| **Ctrl+Q** | Quit | Exit open-packet |

## New Item Picker

Opened with **Ctrl+N** from the main screen.

| Shortcut | Action |
|----------|--------|
| **M** | New personal message |
| **B** | New bulletin |
| **F** | New form message (opens the form picker) |
| **Escape** | Cancel |

## Message Body Panel

| Shortcut | Action |
|----------|--------|
| **W** | Toggle word wrap |

## Files List

| Shortcut | Action |
|----------|--------|
| **R** | Mark the selected file for download on the next sync |
| **U** | Open the upload dialog to send a local file to the BBS |

## Compose Screens (Message and Bulletin)

| Shortcut | Action |
|----------|--------|
| **Tab** | Move to next field |
| **Shift+Tab** | Move to previous field |
| **Ctrl+S** | Queue the message / bulletin (same as **Send** / **Post**) |
| **Escape** | Cancel and discard |

## Form Fill Screen

| Shortcut | Action |
|----------|--------|
| **Tab** | Move to next field |
| **Shift+Tab** | Move to previous field |
| **Ctrl+S** | Submit the form (same as **Submit**; does nothing while validation errors remain) |
| **Escape** | Cancel |

To submit a form that fails validation, use the **Submit Anyway** button.

## Settings Screen

| Shortcut | Action |
|----------|--------|
| **Escape** | Close settings |

## Search Screen

| Shortcut | Action |
|----------|--------|
| **Enter** | Run the search |
| **Escape** | Close search |

> [!NOTE]
> Main-screen shortcuts use the form **Ctrl+\<key\>** except the console toggle (`` ` ``). Single-letter shortcuts apply only inside the picker or panel they are listed under.
