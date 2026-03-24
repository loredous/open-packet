# Status Bar Identity Display

**Date:** 2026-03-24
**Status:** Approved

## Summary

The TUI status bar should display the active operator, node, and interface so the user always knows which identity and connection are in use. Currently the status bar shows connection state only, and its `callsign` reactive is never set.

## Layout

The status bar is a single-line widget at the top of the screen. It is split into two sections:

```
📻 open-packet  ●  Connected  | Last sync: 12:34        │  W1AW  ·  Home BBS  ·  Home TNC
```

- **Left section** (`#status_left`): app name with emoji, connection status icon, status text, last sync time. Takes all remaining horizontal space (`width: 1fr`).
- **Right section** (`#status_right`): active operator, node label, interface label. Right-aligned (`text-align: right; width: auto`). Prefixed with `│` as a visual separator from the left section.

When no operator/node/interface is configured, the right section is empty and the `│` separator is omitted.

## Formatting Rules

- **Operator:** `{callsign}-{ssid}` if `ssid != 0`, else `{callsign}` (e.g. `W1AW` or `W1AW-1`)
- **Node:** label string as stored in DB
- **Interface:** label string as stored in DB
- Fields separated by `  ·  `

## Widget Architecture

`StatusBar` changes from a leaf `Widget` with `render()` to a container that `compose()`s two `Label` children.

**Reactives removed:** `callsign` (was never set)
**Reactives kept:** `status: ConnectionStatus`, `last_sync: str`
**Reactives added:** `operator: str`, `node: str`, `interface_label: str`

CSS:
```css
StatusBar {
    height: 1;
    background: $primary;
    color: $text;
    padding: 0 1;
    layout: horizontal;
}
#status_left {
    width: 1fr;
}
#status_right {
    width: auto;
    text-align: right;
}
```

When any of `operator`, `node`, or `interface_label` changes, `#status_right` re-renders. The right label text is built as:

```python
fields = [f for f in [self.operator, self.node, self.interface_label] if f]
right = ("│  " + "  ·  ".join(fields)) if fields else ""
```

## `app.py` Changes

Two new instance attributes on `OpenPacketApp`:

```python
self._active_node: Optional[Node] = None
self._active_interface: Optional[Interface] = None
```

Both are set at the end of `_start_engine()` (where `node_record` and `iface` are already available) and cleared in `_restart_engine()` before re-initialising.

A helper `_update_status_bar_identity()` reads `_active_operator`, `_active_node`, and `_active_interface` and updates the three reactives on `StatusBar`. It is called:

1. At the end of `_start_engine()` after setting the new attributes
2. At the start of `_restart_engine()` (with `None` values) to clear the display during restart

## Error / Edge Cases

- **No operator configured** (first run): right section is empty.
- **Operator set but no node/interface** (node_record is None or interface_id is None): operator callsign shows, node and interface fields are empty strings.
- **Engine restart**: identity fields are cleared immediately when `_restart_engine()` begins, before re-init completes.

## Files Changed

| File | Change |
|------|--------|
| `open_packet/ui/tui/widgets/status_bar.py` | Refactor to container with two `Label` children; update reactives and CSS |
| `open_packet/ui/tui/app.py` | Add `_active_node`, `_active_interface` attributes; add `_update_status_bar_identity()`; call it from `_start_engine` and `_restart_engine` |

## Out of Scope

- Clicking/interacting with the identity fields
- Showing SSID when it is 0
- Displaying multiple operators or nodes simultaneously
