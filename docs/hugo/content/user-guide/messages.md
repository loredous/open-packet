---
title: "Messages"
weight: 2
---

# Messages

Personal packet messages are stored locally in a SQLite database. open-packet synchronises with the BBS on demand when you trigger a send/receive.

## Folders

Messages are organised into folders shown in the left-hand folder tree:

| Folder | Contents |
|--------|----------|
| **Inbox** | Messages received from other stations |
| **Outbox** | Messages queued to send on the next sync |
| **Sent** | Messages that have been transmitted |
| **Archive** | Messages moved out of the inbox for long-term storage |

## Reading Messages

1. Select a folder in the folder tree (click or use arrow keys)
2. Select a message in the message list
3. The full message body appears in the lower panel

Unread messages are shown in bold. Opening a message marks it as read automatically.

![Message inbox screenshot](../images/screenshot-inbox.png)

## Composing a New Message

Press **Ctrl+N** to open the compose screen.

Fill in:
- **To** — the destination callsign (e.g. `W1AW` or `W1AW-1`)
- **Subject** — a short description of the message
- **Body** — the message text

Press **Ctrl+S** to queue the message for sending, or **Escape** to cancel.

The message will appear in your **Outbox** until the next send/receive (**Ctrl+C**).

![Compose message screenshot](../images/screenshot-compose.png)

## Replying to a Message

Select a message and press **Ctrl+R**. The compose screen opens pre-filled with:
- The sender's callsign in the **To** field
- `Re: <original subject>` in the **Subject** field

Edit the body and press **Ctrl+S** to queue.

## Archiving Messages

Select a message in the **Inbox** and press **A** to move it to the **Archive** folder.

To move a message back to the inbox, navigate to **Archive**, select the message, and press **A** again.

## Deleting Messages

Select a message and press **Ctrl+X**. A confirmation dialog will appear. Confirm to delete the message.

> [!WARNING]
> Deleting a message removes it from both the local database and the BBS (via a kill command sent on the next sync). This action cannot be undone.

## Searching Messages and Bulletins

Press **Ctrl+F** from anywhere in the main screen to open the search modal.

Type a keyword (callsign, subject text, or any word from the body) and press **Enter** or click **Search**. Results from all folders (Inbox, Sent, Archive) and all bulletin categories are shown together, with the source folder or bulletin category displayed for each result.

Selecting a result opens the message body in the main view and marks the item as read.

## Folder Statistics

The folder tree shows unread message counts next to each folder name. These update automatically after each send/receive.
