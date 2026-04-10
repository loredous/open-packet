---
title: "Terminal Connect"
weight: 6
---

# Terminal Connect

The Terminal Connect feature lets you open a raw interactive session to any AX.25 node — not just your configured BBS. This is useful for connecting to nodes that use non-standard protocols, exploring the network, or running manual commands on a BBS.

## Opening Terminal Connect

Press **Ctrl+T** to open the node picker. Select the node you want to connect to.

If you want to connect to a node that is not pre-configured, you can also type a callsign directly.

![Terminal node picker screenshot](/images/screenshot-terminal-picker.png)

## Using the Terminal

Once connected, the terminal view opens and shows the raw session output. Type commands directly and press **Enter** to send them.

The terminal passes all input and output through without interpretation — you are interacting directly with the remote node.

![Terminal session screenshot](/images/screenshot-terminal.png)

## Disconnecting

Press **Ctrl+D** to disconnect the current terminal session and return to the message view.

{{< hint warning >}}
Closing open-packet while a terminal session is active will disconnect the session. Ensure you have sent a proper disconnect command (`BYE`, `D`, etc.) before exiting.
{{< /hint >}}
