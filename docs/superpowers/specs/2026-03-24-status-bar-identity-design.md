# Status Bar Identity Display

**Date:** 2026-03-24
**Status:** Approved

## Summary

The TUI status bar should display the active operator, node, and interface so the user always knows which identity and connection are in use. Currently the status bar shows connection state only, and its `callsign` reactive is never set (displays `---` as a placeholder).

Three changes are made to the left section as part of this work: the unused `callsign` reactive and its `---` placeholder are removed from the rendered text; a 📻 emoji is prepended to the `open-packet` app name; and the left section is migrated from a `render()` method to a `Label` widget updated by reactive watchers.

## Layout

The status bar is a single-line widget at the top of the screen. It is split into two sections:

```
📻 open-packet  ●  Connected  | Last sync: 12:34        │  W1AW  :  Home BBS  :  Home TNC
```

- **Left section** (`#status_left`): `📻 open-packet` (emoji new), connection status icon, status text, `| Last sync: {last_sync}`. Takes all remaining horizontal space (`width: 1fr`).
- **Right section** (`#status_right`): active operator, node label, interface label. Right-aligned. Prefixed with `│` (box-drawing character) as a visual separator. The `|` in the left section and the `│` in the right section are independent — one is part of the left label's text, the other is prepended to the right label's content.

When no operator/node/interface is configured, the right section is empty and its `│` prefix is omitted.

## Formatting Rules

- **Operator:** `{callsign}-{ssid}` if `ssid != 0`, else `{callsign}` (e.g. `W1AW` or `W1AW-1`)
- **Node:** label string as stored in DB
- **Interface:** label string as stored in DB
- Fields separated by `  :  `

## Widget Architecture

`StatusBar` changes from a leaf `Widget` with `render()` to a container that `compose()`s two `Label` children: `#status_left` and `#status_right`.

**Reactives removed:** `callsign` (was never set by the app; its `---` placeholder is currently visible to users and will be removed from the rendered output as part of this change)
**Reactives kept:** `status: ConnectionStatus`, `last_sync: str`
**Reactives added:** `operator: str`, `node: str`, `interface_label: str`

CSS (replaces existing `DEFAULT_CSS`):
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
}
```

Right-alignment of the right section is achieved by `#status_left` consuming all remaining space (`1fr`), pushing `#status_right` to the far right. A `text-align` rule on `#status_right` would be a no-op since the widget is sized to exactly fit its content (`width: auto`).

**Left label rendering:** Define `watch_status` and `watch_last_sync` methods, each calling a shared `_render_left()` helper:

```python
def _render_left(self) -> None:
    icon = {
        ConnectionStatus.DISCONNECTED: "○",
        ConnectionStatus.CONNECTING: "◎",
        ConnectionStatus.CONNECTED: "●",
        ConnectionStatus.SYNCING: "⟳",
        ConnectionStatus.ERROR: "✗",
    }.get(self.status, "?")
    text = f"📻 open-packet  {icon}  {self.status.value.title()}  | Last sync: {self.last_sync}"
    self.query_one("#status_left", Label).update(text)
```

**Right label rendering:** Define `watch_operator`, `watch_node`, and `watch_interface_label` methods, each calling a shared `_render_right()` helper:

```python
def _render_right(self) -> None:
    fields = [f for f in [self.operator, self.node, self.interface_label] if f]
    right = ("│  " + "  :  ".join(fields)) if fields else ""
    self.query_one("#status_right", Label).update(right)
```

**Guard against pre-compose calls:** Both `_render_left()` and `_render_right()` must guard against being called before `compose()` has run, because reactive watchers can fire during `__init__` before the DOM exists. Wrap the `query_one` call in each helper with `try/except Exception: return`. This guard is load-bearing only in the reactive watcher paths; when called from `on_mount()` the DOM is already available.

**Initial render:** Override `on_mount()` to call both `_render_left()` and `_render_right()` once. `on_mount()` fires after `compose()`, so the `#status_left` and `#status_right` labels are guaranteed to exist at this point. This populates the labels with their initial values, since the reactive defaults may not have triggered watchers yet.

## `app.py` Changes

Two new instance attributes on `OpenPacketApp` (note: `Interface` is already imported at line 24):

```python
self._active_node: Optional[Node] = None
self._active_interface: Optional[Interface] = None
```

**Success path assignment in `_start_engine()`:** After `iface` is obtained and `node_record` is available (both are present in the normal path, before `self._engine.start()`), assign:

```python
self._active_node = node_record
self._active_interface = iface
```

Note: `node_record` is the `Node` model dataclass (not the `BPQNode` instance named `node`). This assignment must occur in the normal (success) path only — the two early returns (`interface_id is None`, `iface is None`) leave these attributes as `None`, which is correct.

A helper `_update_status_bar_identity()` reads the three attributes and updates `StatusBar`:

```python
def _update_status_bar_identity(self) -> None:
    op = self._active_operator
    node = self._active_node
    iface = self._active_interface
    try:
        sb = self.query_one("StatusBar")
    except Exception:
        return
    if op:
        sb.operator = f"{op.callsign}-{op.ssid}" if op.ssid != 0 else op.callsign
    else:
        sb.operator = ""
    sb.node = node.label if node else ""
    sb.interface_label = iface.label if iface else ""
```

**`_update_status_bar_identity()` call sites:** The helper must be called at every point where identity state becomes stable:

In `_start_engine()`:
- Before the `interface_id is None` early return (operator set, node/iface `None`). `_active_node` and `_active_interface` are guaranteed `None` here because `_restart_engine()` clears them before entering this path, and on first run they default to `None`.
- Before the `iface is None` early return (operator set, node/iface `None`). Same guarantee applies.
- At the end of the success path (after `self._active_node` and `self._active_interface` are assigned and `self._engine.start()` is called)

In `_init_engine()`:
- Before the early return when no operator exists (all three attributes `None` — guaranteed because `_restart_engine()` clears `_active_operator` before calling `_init_engine()`, and on first run all are `None` by default)
- Before the early return when no node record exists (same guarantee)

In `_restart_engine()`:
- After clearing all three attributes to `None` and before calling `_init_engine()`

**`_restart_engine()` call site:** After the engine stop and db close operations (alongside the existing `_active_operator = None`, `_store = None`, `_engine = None`, `_db = None` clears), also clear `_active_node = None` and `_active_interface = None`, then call `_update_status_bar_identity()` immediately — before `_init_engine()`. When `_init_engine()` eventually calls `_start_engine()`, which calls `_update_status_bar_identity()` again with the new values, this double-call is intentional and harmless: the first call blanks the display during restart, the second populates it once the new engine is ready.

## Error / Edge Cases

- **No operator configured** (first run, `_start_engine` not reached): right section is empty.
- **Operator set, no node/interface** (`interface_id is None` or `iface is None`): operator callsign shows, node and interface fields are empty.
- **Engine restart**: all three fields go blank immediately at the start of `_restart_engine()`, then repopulate once `_start_engine()` completes.

## Files Changed

| File | Change |
|------|--------|
| `open_packet/ui/tui/widgets/status_bar.py` | Refactor to container with two `Label` children; remove `callsign` reactive; add `operator`, `node`, `interface_label` reactives; add `_render_left()`, `_render_right()`, `on_mount()`; update CSS |
| `open_packet/ui/tui/app.py` | Add `_active_node`, `_active_interface` attributes; assign them in success path of `_start_engine()`; add `_update_status_bar_identity()`; call it at all exit points of `_start_engine`, at early-return paths of `_init_engine`, and after clearing attrs in `_restart_engine` |

## Out of Scope

- Clicking/interacting with the identity fields
- Displaying multiple operators or nodes simultaneously
