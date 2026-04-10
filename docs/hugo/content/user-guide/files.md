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

{{< hint info >}}
The export directory defaults to `~/.local/share/open-packet/export`. Files are saved using their original BBS filename.
{{< /hint >}}

![BBS files screenshot](../images/screenshot-files.png)
