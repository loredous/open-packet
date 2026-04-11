---
title: "Bulletins"
description: "Browse bulletin boards and retrieve bulletin bodies on demand"
weight: 3
---

# Bulletins

Bulletins are broadcast messages posted to category channels on a BBS. They are available to all stations that connect to the BBS — not addressed to a specific callsign.

## Browsing Bulletins

Bulletins are listed in the folder tree under **Bulletins**, organised by category (e.g. `ARES`, `WEATHER`, `LOCAL`).

Select a bulletin category to see the list of bulletin headers in that category. Each entry shows:
- The posting station's callsign
- The subject line
- The posting date

## Retrieving Bulletin Bodies

Bulletin headers are retrieved automatically during each sync. However, the full body of a bulletin is only fetched if you explicitly request it — this avoids downloading large bulletins you're not interested in.

To queue a bulletin for body retrieval:

1. Select the bulletin in the list
2. Press **R** to mark it for retrieval

On the next send/receive (**Ctrl+C**), open-packet will fetch the full body.

> [!NOTE]
> Bulletins marked for retrieval are shown with a different indicator in the list. The body appears in the message body panel once retrieved.

![Bulletin list screenshot](../images/screenshot-bulletins.png)

## Posting a Bulletin

Press **Ctrl+B** to open the bulletin compose screen.

Fill in:
- **Category** — the bulletin category channel (e.g. `ARES`, `LOCAL`)
- **Subject** — the subject line
- **Body** — the bulletin text

Press **Ctrl+S** to queue the bulletin for posting on the next sync.

> [!WARNING]
> Bulletins are broadcast to all stations on the BBS. Ensure your category and content are appropriate for the intended audience.
