# open_packet/ui/tui/app.py
from __future__ import annotations
import logging
import os
import queue
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from textual.app import App
from textual.command import Hit, Hits, Provider
from textual.css.query import NoMatches

from open_packet.engine.commands import (
    CheckMailCommand, DeleteMessageCommand, SendMessageCommand, PostBulletinCommand
)
from open_packet.engine.engine import Engine
from open_packet.engine.events import (
    ConnectionStatusEvent, MessageReceivedEvent, SyncCompleteEvent,
    ErrorEvent, ConnectionStatus, MessageQueuedEvent, ConsoleEvent,
    NeighborsDiscoveredEvent, FrameReceivedEvent,
)
from open_packet.ui.tui.screens.shorter_path_confirm import ShorterPathConfirmScreen
from open_packet.ax25.connection import AX25Connection
from open_packet.link.kiss import KISSLink
from open_packet.link.telnet import TelnetLink
from open_packet.node.bpq import BPQNode
from open_packet.store.database import Database
from open_packet.store.models import Operator, Node, Interface, Message, Bulletin, BBSFile
from open_packet.store.settings import Settings
from open_packet.store.store import Store
from open_packet.transport.tcp import TCPTransport
from open_packet.transport.serial import SerialTransport
from open_packet.terminal.session import TerminalSession, TerminalConnectResult
from open_packet.ui.tui.screens.compose import ComposeScreen
from open_packet.ui.tui.screens.compose_bulletin import ComposeBulletinScreen
from open_packet.ui.tui.screens.connect_terminal import ConnectTerminalScreen
from open_packet.ui.tui.screens.main import MainScreen
from open_packet.ui.tui.screens.settings import SettingsScreen
from open_packet.ui.tui.screens.setup_operator import OperatorSetupScreen
from open_packet.ui.tui.screens.setup_node import NodeSetupScreen

logger = logging.getLogger(__name__)


def _setup_logging(log_path: str) -> None:
    from logging.handlers import RotatingFileHandler
    os.makedirs(os.path.dirname(os.path.expanduser(log_path)) or ".", exist_ok=True)
    handler = RotatingFileHandler(
        os.path.expanduser(log_path), maxBytes=5_000_000, backupCount=5
    )
    logging.basicConfig(
        level=logging.INFO,
        handlers=[handler],
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )


class OpenPacketCommands(Provider):
    """Command palette provider for open-packet application commands."""

    async def search(self, query: str) -> Hits:
        app: OpenPacketApp = self.app  # type: ignore[assignment]
        matcher = self.matcher(query)

        commands: list[tuple[str, str, Any]] = [
            ("New Message", "Compose a new message", app.open_compose),
            ("New Bulletin", "Post a new bulletin", app.open_compose_bulletin),
            ("New Form Message", "Compose a form-based message", app.open_form_compose),
            ("Update Default Forms", "Download latest form definitions from the repository", app.update_default_forms),
            ("Send/Receive", "Check mail and sync with BBS", app.check_mail),
            ("Toggle Console", "Show or hide the console panel", app._toggle_console_from_palette),
            ("Settings", "Open application settings", app.open_settings),
            ("Edit Operators", "Manage operator profiles", app._palette_edit_operators),
            ("Edit Nodes", "Manage node configurations", app._palette_edit_nodes),
            ("Edit Interfaces", "Manage radio interfaces", app._palette_edit_interfaces),
            ("Terminal Connect", "Open a terminal connection", app.open_terminal_connect),
        ]

        for display, help_text, callback in commands:
            score = matcher.match(display)
            if score > 0:
                yield Hit(score, matcher.highlight(display), callback, help=help_text)


class OpenPacketApp(App):
    SCREENS = {"compose": ComposeScreen}
    TITLE = "open-packet"
    COMMANDS = {OpenPacketCommands}

    def __init__(self, db_path: str, console_log: Optional[str] = None,
                 forms_dir: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self._db_path = db_path
        self._console_log = console_log
        self._forms_dir: Optional[str] = forms_dir
        self._cmd_queue: queue.Queue = queue.Queue()
        self._evt_queue: queue.Queue = queue.Queue()
        self._engine: Optional[Engine] = None
        self._selected_message = None
        self._store: Optional[Store] = None
        self._settings: Optional[Settings] = None
        self._active_operator: Optional[Operator] = None
        self._active_node: Optional[Node] = None
        self._active_interface: Optional[Interface] = None
        self._active_folder = "Inbox"
        self._active_category = ""
        self._db: Optional[Database] = None
        self._pending_neighbor_prompts: list = []
        self._terminal_sessions: list[TerminalSession] = []
        self._active_session_idx: Optional[int] = None
        self._scheduled_sr_timer = None

    @property
    def forms_dir(self) -> Path:
        if self._forms_dir:
            return Path(self._forms_dir)
        env = os.environ.get("OPEN_PACKET_FORMS_DIR")
        if env:
            return Path(env)
        return Path.home() / ".config/open-packet/forms"

    def get_default_screen(self) -> MainScreen:
        return MainScreen()

    def on_mount(self) -> None:
        self._init_engine()
        if self._console_log:
            try:
                self.query_one("ConsolePanel").set_log_file(self._console_log)
            except Exception:
                pass
        self.set_interval(0.1, self._poll_events)
        self.call_after_refresh(self._refresh_message_list)
        self.call_after_refresh(self._update_status_bar_identity)
        self._update_scheduled_sr()

    def _init_engine(self) -> None:
        db_path = os.path.expanduser(self._db_path)
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        db = Database(db_path)
        db.initialize()
        self._settings = Settings(db)
        # Assign self._db BEFORE any early return so _restart_engine can close it.
        self._db = db

        operator = db.get_default_operator()
        node_record = db.get_default_node()

        if not operator:
            self._update_status_bar_identity()
            self.call_after_refresh(
                lambda: self.push_screen(OperatorSetupScreen(), callback=self._on_operator_setup_result)
            )
            return
        elif not node_record:
            self._update_status_bar_identity()
            self.call_after_refresh(
                lambda: self.push_screen(NodeSetupScreen(interfaces=self._db.list_interfaces(), db=self._db), callback=self._on_node_setup_result)
            )
            return

        self._start_engine(db, operator, node_record)

    def _make_frame_logger(self):
        from open_packet.engine.events import ConsoleEvent as _CE, FrameReceivedEvent as _FRE
        evt_queue = self._evt_queue
        def _log(direction: str, summary: str) -> None:
            evt_queue.put(_CE(direction, summary, level="debug"))
            if direction == "<":
                evt_queue.put(_FRE())
        return _log

    def _build_connection(self, iface: Interface, op: Operator, on_frame=None):
        match iface.iface_type:
            case "telnet":
                return TelnetLink(
                    host=iface.host, port=iface.port,
                    username=iface.username, password=iface.password,
                    on_frame=on_frame,
                )
            case "kiss_tcp":
                transport = TCPTransport(host=iface.host, port=iface.port)
                return AX25Connection(
                    kiss=KISSLink(transport=transport),
                    my_callsign=op.callsign,
                    my_ssid=op.ssid,
                    on_frame=on_frame,
                )
            case "kiss_serial":
                transport = SerialTransport(device=iface.device, baud=iface.baud)
                return AX25Connection(
                    kiss=KISSLink(transport=transport),
                    my_callsign=op.callsign,
                    my_ssid=op.ssid,
                    on_frame=on_frame,
                )
            case _:
                return None

    def _start_engine(self, db: Database, operator: Operator, node_record: Node) -> None:
        store = Store(db)
        self._store = store
        self._active_operator = operator

        if node_record.interface_id is None:
            self._active_node = None
            self._active_interface = None
            self._update_status_bar_identity()
            return  # no interface configured; engine stays dormant

        iface = db.get_interface(node_record.interface_id)
        if iface is None:
            self._active_node = None
            self._active_interface = None
            self._update_status_bar_identity()
            return

        connection = self._build_connection(iface, operator, on_frame=self._make_frame_logger())
        if connection is None:
            raise ValueError(f"Unknown interface type: {iface.iface_type!r}")

        node = BPQNode(
            connection=connection,
            node_callsign=node_record.callsign,
            node_ssid=node_record.ssid,
            my_callsign=operator.callsign,
            my_ssid=operator.ssid,
            hop_path=node_record.hop_path,
            path_strategy=node_record.path_strategy,
        )

        export_path = (
            os.path.expanduser(self._settings.export_path)
            if self._settings and self._settings.export_path else None
        )

        self._engine = Engine(
            command_queue=self._cmd_queue,
            event_queue=self._evt_queue,
            store=store,
            operator=operator,
            node_record=node_record,
            connection=connection,
            node=node,
            export_path=export_path,
            auto_discover=self._settings.auto_discover if self._settings else True,
        )
        self._active_node = node_record
        self._active_interface = iface
        self._engine.start()
        self._update_status_bar_identity()

    def _restart_engine(self) -> None:
        if self._engine is not None:
            self._engine.stop()
        if self._db is not None:
            self._db.close()
        self._engine = None
        self._store = None
        self._active_operator = None
        self._active_node = None
        self._active_interface = None
        self._db = None
        self._update_status_bar_identity()
        self._init_engine()

    def _do_scheduled_sr(self) -> None:
        if self._engine is not None:
            self._cmd_queue.put(CheckMailCommand())

    def _update_scheduled_sr(self) -> None:
        if self._scheduled_sr_timer is not None:
            self._scheduled_sr_timer.stop()
            self._scheduled_sr_timer = None
        if self._settings and self._settings.scheduled_sr_enabled:
            interval_seconds = max(self._settings.scheduled_sr_interval * 60, 300)
            self._scheduled_sr_timer = self.set_interval(interval_seconds, self._do_scheduled_sr)

    def _update_status_bar_identity(self) -> None:
        op = self._active_operator
        node = self._active_node
        iface = self._active_interface
        try:
            sb = self.query_one("StatusBar")
        except NoMatches:
            return
        if op:
            sb.operator = f"{op.callsign}-{op.ssid}" if op.ssid != 0 else op.callsign
        else:
            sb.operator = ""
        sb.node = node.label if node else ""
        sb.interface_label = iface.label if iface else ""

    def _save_operator(self, op: Operator) -> None:
        assert self._db is not None
        if op.is_default:
            self._db.clear_default_operator()
        self._db.insert_operator(op)

    def _save_node(self, node: Node) -> None:
        assert self._db is not None
        if node.is_default:
            self._db.clear_default_node()
        self._db.insert_node(node)

    # --- Dismiss callbacks ---

    def _on_operator_setup_result(self, result) -> None:
        if result is None:
            return
        self._save_operator(result)
        assert self._db is not None
        # Check DB state to determine next step (works for both first-run and settings flow)
        if self._db.get_default_node() is None:
            self.push_screen(NodeSetupScreen(interfaces=self._db.list_interfaces(), db=self._db), callback=self._on_node_setup_result)
        else:
            self._restart_engine()

    def _on_node_setup_result(self, result) -> None:
        if result is None:
            return
        self._save_node(result)
        self._restart_engine()

    def _on_settings_result(self, result) -> None:
        if result == "general":
            if self._settings:
                from open_packet.ui.tui.screens.general_settings import GeneralSettingsScreen
                self.push_screen(
                    GeneralSettingsScreen(self._settings),
                    callback=self._on_manage_result,
                )
            return
        elif result == "operator":
            if self._db:
                from open_packet.ui.tui.screens.manage_operators import OperatorManageScreen
                self.push_screen(OperatorManageScreen(self._db),
                                 callback=self._on_manage_result)
            else:
                self.push_screen(OperatorSetupScreen(), callback=self._on_operator_setup_result)
        elif result == "node":
            if self._db:
                from open_packet.ui.tui.screens.manage_nodes import NodeManageScreen
                self.push_screen(NodeManageScreen(self._db),
                                 callback=self._on_manage_result)
            else:
                self.push_screen(NodeSetupScreen(interfaces=[], db=None), callback=self._on_node_setup_result)
        elif result == "interfaces":
            if self._db:
                from open_packet.ui.tui.screens.manage_interfaces import InterfaceManageScreen
                self.push_screen(InterfaceManageScreen(self._db),
                                 callback=self._on_manage_result)

    def _on_manage_result(self, needs_restart) -> None:
        if needs_restart:
            self._restart_engine()
        self._update_scheduled_sr()

    # --- Event polling ---

    def _poll_events(self) -> None:
        while not self._evt_queue.empty():
            try:
                event = self._evt_queue.get_nowait()
                self._handle_event(event)
            except queue.Empty:
                break

        if not self._terminal_sessions:
            return

        needs_sidebar_refresh = False
        for i, session in enumerate(self._terminal_sessions):
            lines = session.poll()
            if lines:
                if i == self._active_session_idx:
                    try:
                        tv = self.query_one("TerminalView")
                        for line in lines:
                            tv.append_line(line)
                    except Exception:
                        pass
                else:
                    session.has_unread = True
                    needs_sidebar_refresh = True

        if needs_sidebar_refresh:
            self._refresh_sessions()

    def _handle_event(self, event) -> None:
        if isinstance(event, MessageQueuedEvent):
            self._refresh_message_list()
            return
        if isinstance(event, ConsoleEvent):
            if getattr(event, "level", "basic") == "debug":
                if not self._settings or self._settings.console_log_level != "debug":
                    return
            try:
                self.query_one("ConsolePanel").log_frame(event.direction, event.text)
            except Exception:
                pass
            return
        try:
            status_bar = self.query_one("StatusBar")
        except Exception:
            return

        if isinstance(event, FrameReceivedEvent):
            from datetime import datetime
            status_bar.last_frame = datetime.now().strftime("%H:%M:%S")
            return
        if isinstance(event, ConnectionStatusEvent):
            status_bar.status = event.status
            status_bar.sync_detail = event.detail if event.status == ConnectionStatus.SYNCING else ""
            if event.status == ConnectionStatus.ERROR:
                self.notify(f"Error: {event.detail}", severity="error")
        elif isinstance(event, SyncCompleteEvent):
            from datetime import datetime
            status_bar.last_sync = datetime.now().strftime("%H:%M")
            parts = [
                f"{event.messages_retrieved} new",
                f"{event.bulletins_retrieved} bulletins",
                f"{event.messages_sent} sent",
            ]
            if getattr(event, "files_retrieved", 0) > 0:
                export_path = self._settings.export_path if self._settings else "~/.local/share/open-packet/export"
                parts.append(f"{event.files_retrieved} file(s) saved to {export_path}/files/")
            self.notify(f"Sync complete: {', '.join(parts)}")
            self._refresh_message_list()
        elif isinstance(event, ErrorEvent):
            self.notify(f"Error: {event.message}", severity="error")
        elif isinstance(event, NeighborsDiscoveredEvent):
            self._queue_neighbor_prompts(event)

    def _queue_neighbor_prompts(self, event: NeighborsDiscoveredEvent) -> None:
        """Build a sequential queue of prompts and start showing them."""
        if not self._store or not self._active_node:
            return
        prompts = []
        for hop in event.new_neighbors:
            prompts.append(("new", hop, None))
        for existing_node, new_path in event.shorter_path_candidates:
            prompts.append(("shorter", None, (existing_node, new_path)))
        self._pending_neighbor_prompts = prompts
        self._show_next_neighbor_prompt()

    def _show_next_neighbor_prompt(self) -> None:
        if not self._pending_neighbor_prompts:
            return
        kind, hop, extra = self._pending_neighbor_prompts.pop(0)
        if kind == "new":
            node_rec = self._active_node
            pre_hop_path = list(node_rec.hop_path) + [hop]
            from open_packet.store.models import Node
            stub = Node(
                label=hop.callsign,
                callsign=hop.callsign,
                ssid=0,
                node_type="bpq",
                hop_path=pre_hop_path,
                path_strategy=node_rec.path_strategy,
                interface_id=node_rec.interface_id,
            )
            self.push_screen(
                NodeSetupScreen(
                    node=stub,
                    interfaces=self._db.list_interfaces() if self._db else [],
                    db=self._db,
                ),
                callback=self._on_new_neighbor_result,
            )
        else:
            existing_node, new_path = extra
            summary = " → ".join(
                f"{h.callsign}:{h.port}" if h.port else h.callsign for h in new_path
            )
            self.push_screen(
                ShorterPathConfirmScreen(
                    node_label=existing_node.label,
                    current_len=len(existing_node.hop_path),
                    new_path_summary=summary,
                ),
                callback=lambda accepted, n=existing_node, p=new_path:
                    self._on_shorter_path_result(accepted, n, p),
            )

    def _on_new_neighbor_result(self, result) -> None:
        if result is not None and self._db:
            self._save_node(result)
        self._show_next_neighbor_prompt()

    def _on_shorter_path_result(self, accepted: bool, node, new_path) -> None:
        if accepted and self._db:
            node.hop_path = new_path
            self._db.update_node(node)
        self._show_next_neighbor_prompt()

    def _refresh_message_list(self) -> None:
        if not self._store or not self._active_operator:
            return
        try:
            folder = self._active_folder
            category = self._active_category
            operator_id = self._active_operator.id

            if folder == "Files":
                if self._active_node:
                    files = self._store.list_files(self._active_node.id, category or "")
                    try:
                        self.query_one("FileList").load_files(files)
                    except Exception:
                        pass
                stats = self._store.count_folder_stats(operator_id)
                self.query_one("FolderTree").update_counts(stats)
                return

            msg_list = self.query_one("MessageList")

            if folder == "Inbox":
                messages = [
                    m for m in self._store.list_messages(operator_id=operator_id)
                    if not m.sent and not m.queued
                ]
            elif folder == "Sent":
                messages = [
                    m for m in self._store.list_messages(operator_id=operator_id)
                    if m.sent
                ]
            elif folder == "Archive":
                messages = self._store.list_archived_messages(operator_id=operator_id)
            elif folder == "Bulletins":
                messages = self._store.list_bulletins(
                    operator_id=operator_id,
                    category=category or None,
                )
            elif folder == "Outbox":
                messages = self._store.list_outbox(operator_id=operator_id)
            else:
                messages = []

            msg_list.load_messages(messages)
            stats = self._store.count_folder_stats(operator_id)
            self.query_one("FolderTree").update_counts(stats)
        except Exception:
            logger.exception("Failed to refresh message list")

    def _refresh_folder_counts(self) -> None:
        if not self._store or not self._active_operator:
            return
        try:
            stats = self._store.count_folder_stats(self._active_operator.id)
            self.query_one("FolderTree").update_counts(stats)
        except Exception:
            logger.exception("Failed to refresh folder counts")

    def check_mail(self) -> None:
        if self._engine:
            self._cmd_queue.put(CheckMailCommand())

    def delete_selected_message(self) -> None:
        msg = self._selected_message
        if msg is None or msg.id is None:
            return
        if isinstance(msg, Bulletin):
            if self._store:
                self._store.delete_bulletin(msg.id)
                self._selected_message = None
                self._refresh_message_list()
        elif isinstance(msg, Message):
            if self._engine:
                self._cmd_queue.put(DeleteMessageCommand(
                    message_id=msg.id,
                    bbs_id=msg.bbs_id,
                ))

    def archive_selected_message(self) -> None:
        msg = self._selected_message
        if msg is None or msg.id is None or not isinstance(msg, Message):
            return
        if not self._store:
            return
        if self._active_folder == "Archive":
            self._store.unarchive_message(msg.id)
        else:
            self._store.archive_message(msg.id)
        self._selected_message = None
        self._refresh_message_list()

    def queue_bulletin_retrieval(self) -> None:
        msg = self._selected_message
        if not isinstance(msg, Bulletin) or msg.id is None or msg.body is not None or not self._store:
            return
        self._store.toggle_bulletin_wants_retrieval(msg.id)
        self._refresh_message_list()
        self._refresh_folder_counts()

    def open_new_item(self) -> None:
        """Open the 'New Item' modal to choose what to create."""
        from open_packet.ui.tui.screens.new_item import NewItemScreen
        self.push_screen(NewItemScreen(), callback=self._on_new_item_result)

    def _on_new_item_result(self, result: str | None) -> None:
        if result == "message":
            self.open_compose()
        elif result == "bulletin":
            self.open_compose_bulletin()
        elif result == "form":
            self.open_form_compose()

    def _toggle_console_from_palette(self) -> None:
        """Toggle console panel visibility (used by command palette)."""
        try:
            panel = self.query_one("ConsolePanel")
            panel.display = not panel.display
        except NoMatches:
            pass

    def _palette_edit_operators(self) -> None:
        """Open operator management from the command palette."""
        if self._db:
            from open_packet.ui.tui.screens.manage_operators import OperatorManageScreen
            self.push_screen(OperatorManageScreen(self._db), callback=self._on_manage_result)

    def _palette_edit_nodes(self) -> None:
        """Open node management from the command palette."""
        if self._db:
            from open_packet.ui.tui.screens.manage_nodes import NodeManageScreen
            self.push_screen(NodeManageScreen(self._db), callback=self._on_manage_result)

    def _palette_edit_interfaces(self) -> None:
        """Open interface management from the command palette."""
        if self._db:
            from open_packet.ui.tui.screens.manage_interfaces import InterfaceManageScreen
            self.push_screen(InterfaceManageScreen(self._db), callback=self._on_manage_result)

    def open_compose(self, to_call: str = "", subject: str = "", body: str = "") -> None:
        self.push_screen(
            ComposeScreen(to_call=to_call, subject=subject, body=body),
            callback=self._on_compose_result,
        )

    def open_form_compose(self) -> None:
        from open_packet.forms.loader import discover_forms
        from open_packet.ui.tui.screens.form_picker import FormPickerScreen
        forms = discover_forms(self.forms_dir)
        self.push_screen(FormPickerScreen(forms), callback=self._on_form_picker_result)

    def _on_form_picker_result(self, form_def) -> None:
        if form_def is None:
            return
        from open_packet.ui.tui.screens.form_fill import FormFillScreen
        self.push_screen(FormFillScreen(form_def), callback=self._on_form_fill_result)

    def _on_form_fill_result(self, result) -> None:
        if result is None:
            return
        subject, body = result
        self.open_compose(subject=subject, body=body)

    def update_default_forms(self) -> None:
        """Download new/updated form definitions from the repository."""
        import threading
        from open_packet.forms.updater import update_forms

        self.notify("Checking for form updates…")
        forms_dir = self.forms_dir

        def _run() -> None:
            try:
                result = update_forms(
                    forms_dir=forms_dir,
                    on_progress=None,
                )
                if result.errors:
                    msg = f"Forms update finished with errors: {', '.join(result.errors[:3])}"
                    self.call_from_thread(self.notify, msg, severity="error")
                elif result.total_new_or_updated == 0:
                    self.call_from_thread(self.notify, "Forms are already up to date.")
                else:
                    msg = (
                        f"Forms updated: {result.total_new_or_updated} new/updated "
                        f"({len(result.skipped)} unchanged)."
                    )
                    self.call_from_thread(self.notify, msg)
            except Exception as exc:
                logger.exception("Unexpected error while updating default forms")
                self.call_from_thread(
                    self.notify,
                    f"Forms update failed: {exc}",
                    severity="error",
                )

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def open_compose_bulletin(self) -> None:
        self.push_screen(ComposeBulletinScreen(), callback=self._on_compose_bulletin_result)

    def _on_compose_bulletin_result(self, result) -> None:
        if result and isinstance(result, PostBulletinCommand):
            self._cmd_queue.put(result)

    def open_terminal_connect(self) -> None:
        if self._db is None:
            return
        self.push_screen(
            ConnectTerminalScreen(db=self._db),
            callback=self._on_connect_terminal_result,
        )

    def _on_connect_terminal_result(self, result: Optional[TerminalConnectResult]) -> None:
        if result is None:
            return
        iface = result.interface
        op = self._active_operator
        if op is None:
            return

        connection = self._build_connection(iface, op, on_frame=self._make_frame_logger())
        if connection is None:
            return

        session = TerminalSession(
            label=result.label,
            connection=connection,
            target_callsign=result.target_callsign,
            target_ssid=result.target_ssid,
        )
        session.start()
        self._terminal_sessions.append(session)
        self._active_session_idx = len(self._terminal_sessions) - 1
        self._refresh_sessions()
        if isinstance(self.screen, MainScreen):
            tv = self.screen.query_one("TerminalView")
            tv.clear()
            tv.set_header(f"{session.label} — {session.status}")
            self.screen.show_terminal()

    def disconnect_session(self) -> None:
        idx = self._active_session_idx
        if idx is None or idx >= len(self._terminal_sessions):
            return
        self._terminal_sessions[idx].disconnect()
        self._terminal_sessions.pop(idx)
        self._active_session_idx = None
        self._refresh_sessions()
        if isinstance(self.screen, MainScreen):
            self.screen.show_messages()

    def _refresh_sessions(self) -> None:
        try:
            self.query_one("FolderTree").update_sessions(self._terminal_sessions)
        except Exception:
            pass

    def on_status_bar_identity_clicked(self, event) -> None:
        if self._db is None:
            return
        if event.kind == "operator":
            from open_packet.ui.tui.screens.operator_picker import OperatorPickerScreen
            self.push_screen(OperatorPickerScreen(self._db), callback=self._on_manage_result)
        elif event.kind == "node":
            from open_packet.ui.tui.screens.node_picker import NodePickerScreen
            self.push_screen(NodePickerScreen(self._db), callback=self._on_manage_result)
        elif event.kind == "interface":
            if self._active_node:
                from open_packet.ui.tui.screens.interface_picker import InterfacePickerScreen
                self.push_screen(
                    InterfacePickerScreen(self._db, self._active_node),
                    callback=self._on_manage_result,
                )

    def open_settings(self) -> None:
        self.push_screen(SettingsScreen(), callback=self._on_settings_result)

    def reply_to_selected(self) -> None:
        msg = self._selected_message
        if not msg or not isinstance(msg, Message):
            return
        subject = msg.subject if msg.subject.startswith("Re: ") else f"Re: {msg.subject}"
        self.open_compose(to_call=msg.from_call, subject=subject)

    def _on_compose_result(self, result) -> None:
        if result and isinstance(result, SendMessageCommand):
            self._cmd_queue.put(result)

    def on_message_list_message_selected(self, event) -> None:
        self._selected_message = event.message
        try:
            node_label = ""
            if isinstance(event.message, Bulletin) and event.message.body is None and self._store:
                nodes = {n.id: n.label for n in self._store.list_nodes()}
                node_label = nodes.get(event.message.node_id, f"node #{event.message.node_id}")
            self.query_one("MessageBody").show_message(event.message, node_label=node_label)
        except Exception:
            pass
        if self._store and event.message.id is not None and not event.message.read:
            if isinstance(event.message, Message):
                self._store.mark_message_read(event.message.id)
            elif isinstance(event.message, Bulletin):
                self._store.mark_bulletin_read(event.message.id)
            event.message.read = True
            self._refresh_folder_counts()
            try:
                self.query_one("MessageList").mark_row_read(event.row_index)
            except Exception:
                pass

    def on_folder_tree_folder_selected(self, event) -> None:
        self._active_folder = event.folder
        self._active_category = getattr(event, "category", "")
        if event.folder == "Files":
            if isinstance(self.screen, MainScreen):
                self.screen.show_files()
        else:
            if isinstance(self.screen, MainScreen):
                self.screen.show_messages()
        self._refresh_message_list()

    def on_file_list_retrieval_toggled(self, event) -> None:
        if self._store:
            self._store.mark_file_wants_retrieval(event.file.id)
            self._refresh_message_list()

    def on_folder_tree_session_selected(self, event) -> None:
        idx = event.session_idx
        if idx < 0 or idx >= len(self._terminal_sessions):
            return
        self._active_session_idx = idx
        session = self._terminal_sessions[idx]
        session.has_unread = False
        self._refresh_sessions()
        if isinstance(self.screen, MainScreen):
            tv = self.screen.query_one("TerminalView")
            tv.clear()
            tv.set_header(f"{session.label} — {session.status}")
            self.screen.show_terminal()

    def on_terminal_view_line_submitted(self, event) -> None:
        idx = self._active_session_idx
        if idx is None or idx >= len(self._terminal_sessions):
            return
        session = self._terminal_sessions[idx]
        session.send(event.text)
        try:
            self.query_one("TerminalView").append_line(f"> {event.text}")
        except Exception:
            pass

def serve() -> None:
    from textual_serve.server import Server
    server = Server("open-packet")
    server.serve()

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(prog="open-packet")
    parser.add_argument("--db-path", default=None, help="Path to SQLite database")
    parser.add_argument("--log-path", default=None, help="Path to log file")
    parser.add_argument("--console-log", default=None, help="Path to console frame log")
    parser.add_argument("--forms-dir", default=None, help="Path to forms directory")
    args = parser.parse_args()

    db_path = (
        args.db_path
        or os.environ.get("OPEN_PACKET_DB_PATH")
        or "~/.local/share/open-packet/messages.db"
    )
    log_path = (
        args.log_path
        or os.environ.get("OPEN_PACKET_LOG_PATH")
        or "~/.local/share/open-packet/open-packet.log"
    )
    console_log = args.console_log or os.environ.get("OPEN_PACKET_CONSOLE_LOG")
    forms_dir = args.forms_dir or os.environ.get("OPEN_PACKET_FORMS_DIR")

    _setup_logging(log_path)
    app = OpenPacketApp(db_path=db_path, console_log=console_log, forms_dir=forms_dir)
    app.run()
