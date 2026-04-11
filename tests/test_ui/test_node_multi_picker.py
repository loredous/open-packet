"""Tests for NodeMultiPickerScreen (issue #14)."""
import pytest
from textual.app import App
from open_packet.store.models import Node
from open_packet.ui.tui.screens.node_multi_picker import NodeMultiPickerScreen


_SENTINEL = object()


def _make_node(id_: int, label: str, callsign: str) -> Node:
    n = Node(label=label, callsign=callsign, ssid=0, node_type="bpq")
    n.id = id_
    return n


class _PickerApp(App):
    def __init__(self, nodes, **kwargs):
        super().__init__(**kwargs)
        self._picker_nodes = nodes
        self.dismiss_result = _SENTINEL

    def on_mount(self) -> None:
        self.push_screen(
            NodeMultiPickerScreen(nodes=self._picker_nodes),
            callback=lambda r: setattr(self, "dismiss_result", r),
        )


@pytest.mark.asyncio
async def test_cancel_dismisses_with_none():
    nodes = [_make_node(1, "Home BBS", "W0AAA"), _make_node(2, "Work BBS", "W0BBB")]
    app = _PickerApp(nodes)
    async with app.run_test() as pilot:
        await pilot.click("#cancel_btn")
        await pilot.pause()
    assert app.dismiss_result is None


@pytest.mark.asyncio
async def test_confirm_without_selection_shows_error():
    nodes = [_make_node(1, "Home BBS", "W0AAA"), _make_node(2, "Work BBS", "W0BBB")]
    app = _PickerApp(nodes)
    async with app.run_test() as pilot:
        await pilot.click("#confirm_btn")
        await pilot.pause()
    # Should not have dismissed yet (no selection)
    assert app.dismiss_result is _SENTINEL


@pytest.mark.asyncio
async def test_select_single_node_returns_list():
    nodes = [_make_node(1, "Home BBS", "W0AAA"), _make_node(2, "Work BBS", "W0BBB")]
    app = _PickerApp(nodes)
    async with app.run_test() as pilot:
        await pilot.click("#node_1")   # check node 1
        await pilot.click("#confirm_btn")
        await pilot.pause()
    assert app.dismiss_result == [1]


@pytest.mark.asyncio
async def test_select_multiple_nodes_returns_list():
    nodes = [_make_node(1, "Home BBS", "W0AAA"), _make_node(2, "Work BBS", "W0BBB")]
    app = _PickerApp(nodes)
    async with app.run_test() as pilot:
        await pilot.click("#node_1")
        await pilot.click("#node_2")
        await pilot.click("#confirm_btn")
        await pilot.pause()
    assert set(app.dismiss_result) == {1, 2}


@pytest.mark.asyncio
async def test_escape_dismisses_with_none():
    nodes = [_make_node(1, "Home BBS", "W0AAA")]
    app = _PickerApp(nodes)
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
    assert app.dismiss_result is None
