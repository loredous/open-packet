---
title: "BBS Files"
weight: 4
---

# BBS Files

Many BBS nodes host file directories containing useful documents, software, or resources for amateur radio operators. open-packet lets you browse these directories and download files to your local machine.

## Browsing File Directories

File directories are listed in the folder tree under **Files**, organised by BBS directory name (e.g. `ARES`, `WEATHER`, `SOFTWARE`).

Select a directory to see the files it contains. Each entry shows:
- The filename
- File size (bytes)
- Date (as reported by the BBS)
- A short description

## Downloading Files

File content is retrieved on demand — headers are fetched during sync, and file content is fetched when you request it.

To download a file:

1. Select the file in the list
2. Press **R** to mark it for retrieval

On the next send/receive (**Ctrl+C**), open-packet will fetch the file content and save it to the configured export directory (see [Configuration Reference]({{< relref "/reference/configuration" >}})).

> [!NOTE]
> The export directory defaults to `~/.local/share/open-packet/export`. Files are saved using their original BBS filename.

## Uploading Files

You can upload a local file to the BBS directly from the file browser.

To upload a file:

1. Navigate to the **Files** view using the folder tree
2. Press **U** to open the upload dialog
3. Enter the **local file path** (e.g. `/home/user/documents/ares-form.txt`)
4. Confirm or edit the **BBS filename** — the local filename is pre-filled automatically
5. Enter a short **description** (one line, shown in the BBS `DIR` listing)
6. Press **Upload** to send the file to the BBS

open-packet connects to the BBS, uploads the file, and disconnects automatically. A notification confirms when the upload is complete.

> [!NOTE]
> The maximum file size is 65,535 bytes (64 KB), which is the LinBPQ/BPQ32 default limit.

![BBS files screenshot](../images/screenshot-files.png)
