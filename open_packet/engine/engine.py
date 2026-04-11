# open_packet/engine/engine.py
from __future__ import annotations
import logging
import queue
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from open_packet.engine.commands import (
    Command, CheckMailCommand, ConnectCommand, DisconnectCommand,
    SendMessageCommand, DeleteMessageCommand, PostBulletinCommand,
    GroupSyncCommand,
)
from open_packet.engine.events import (
    ConnectionStatusEvent, ConnectionStatus, MessageReceivedEvent,
    SyncCompleteEvent, ErrorEvent, MessageQueuedEvent, ConsoleEvent,
    NeighborsDiscoveredEvent, GroupSyncCompleteEvent, GroupSyncNodeResult,
)
from open_packet.link.base import ConnectionBase
from open_packet.node.base import NodeBase
from open_packet.store.models import Operator, Node, Message, Bulletin, BBSFile
from open_packet.store.store import Store

logger = logging.getLogger(__name__)

_BBS_DATE_FORMATS_WITH_YEAR = ["%d-%b-%y", "%m/%d/%y", "%d/%m/%y"]
_BBS_DATE_FORMATS_NO_YEAR   = ["%d-%b", "%m/%d"]


def _parse_bbs_date(date_str: str, now: datetime) -> datetime:
    """Parse a BPQ32 date string into a UTC datetime, falling back to *now*."""
    for fmt in _BBS_DATE_FORMATS_WITH_YEAR:
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    for fmt in _BBS_DATE_FORMATS_NO_YEAR:
        try:
            parsed = datetime.strptime(date_str, fmt)
            candidate = parsed.replace(year=now.year, tzinfo=timezone.utc)
            if candidate > now + timedelta(days=1):
                candidate = candidate.replace(year=now.year - 1)
            return candidate
        except ValueError:
            pass
    return now


class Engine:
    def __init__(
        self,
        command_queue: queue.Queue,
        event_queue: queue.Queue,
        store: Store,
        operator: Operator,
        node_record: Node,
        connection: ConnectionBase,
        node: NodeBase,
        export_path: Optional[str] = None,
        auto_discover: bool = True,
    ):
        self._cmd_queue = command_queue
        self._evt_queue = event_queue
        self._store = store
        self._operator = operator
        self._node_record = node_record
        self._connection = connection
        self._node = node
        self._export_path = export_path
        self._auto_discover = auto_discover

        # In-memory state
        self._status = ConnectionStatus.DISCONNECTED
        self._last_sync: Optional[datetime] = None
        self._messages_last_sync = 0

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=5.0)

    @property
    def last_sync(self) -> Optional[datetime]:
        return self._last_sync

    @property
    def status(self) -> ConnectionStatus:
        return self._status

    def _emit(self, event) -> None:
        self._evt_queue.put(event)

    def _set_status(self, status: ConnectionStatus, detail: str = "") -> None:
        self._status = status
        self._emit(ConnectionStatusEvent(status=status, detail=detail))

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                cmd = self._cmd_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self._handle(cmd)
            except Exception as e:
                logger.exception("Engine error handling %s", type(cmd).__name__)
                self._emit(ConsoleEvent("!", str(e), level="basic"))
                self._emit(ErrorEvent(message=str(e)))
                self._set_status(ConnectionStatus.ERROR, str(e))

    def _handle(self, cmd: Command) -> None:
        if isinstance(cmd, CheckMailCommand):
            self._do_check_mail()
        elif isinstance(cmd, GroupSyncCommand):
            self._do_group_sync(cmd)
        elif isinstance(cmd, SendMessageCommand):
            self._do_send_message(cmd)
        elif isinstance(cmd, DeleteMessageCommand):
            self._do_delete_message(cmd)
        elif isinstance(cmd, PostBulletinCommand):
            self._do_post_bulletin(cmd)
        elif isinstance(cmd, ConnectCommand):
            self._do_connect()
        elif isinstance(cmd, DisconnectCommand):
            self._do_disconnect()

    @staticmethod
    def _base_call(callsign: str) -> str:
        return callsign.split("-")[0].upper()

    def _discover_neighbors(self) -> tuple[list, list]:
        """Returns (new_neighbors, shorter_path_candidates).
        Calls node.list_linked_nodes(), upserts all, classifies results.
        Must be called while at the node prompt (before BBS).
        Comparisons use base callsign (no SSID) so W0IA-1, W0IA-7, W0IA-10
        are all treated as the same physical station."""
        hops = self._node.list_linked_nodes()
        new_neighbors = []
        shorter_path_candidates = []
        existing_in_db = {
            self._base_call(n.callsign): n
            for n in self._store.list_nodes()
            if n.interface_id == self._node_record.interface_id and n.id != self._node_record.id
        }
        known_bases = {
            self._base_call(h.callsign)
            for h in self._store.get_node_neighbors(self._node_record.id)
        }
        for hop in hops:
            self._store.upsert_node_neighbor(self._node_record.id, hop.callsign, hop.port)
            base = self._base_call(hop.callsign)
            if base not in known_bases:
                new_neighbors.append(hop)
            if base in existing_in_db:
                existing = existing_in_db[base]
                derived_len = len(self._node_record.hop_path) + 1
                if derived_len < len(existing.hop_path):
                    derived_path = self._node_record.hop_path + [hop]
                    shorter_path_candidates.append((existing, derived_path))
        return new_neighbors, shorter_path_candidates

    def _do_connect(self) -> None:
        self._set_status(ConnectionStatus.CONNECTING)
        self._connection.connect(
            callsign=self._node_record.callsign,
            ssid=self._node_record.ssid,
        )
        self._node.connect_node()
        self._set_status(ConnectionStatus.CONNECTED)

    def _do_disconnect(self) -> None:
        self._connection.disconnect()
        self._set_status(ConnectionStatus.DISCONNECTED)

    def _run_sync_phases(self, node, node_id: Optional[int] = None) -> tuple[int, int, int, int]:
        """Run the sync phases. Returns (retrieved, sent, bulletins_retrieved, files_retrieved).
        Does NOT emit SyncCompleteEvent — caller is responsible for that.
        node_id filters outbound messages/bulletins to those targeted at this node."""
        sync_node_id = node_id if node_id is not None else self._node_record.id

        # Phase 1: Retrieve new messages
        retrieved = 0
        self._set_status(ConnectionStatus.SYNCING, "Listing messages…")
        self._emit(ConsoleEvent("!", "Listing messages…", level="basic"))
        headers = node.list_messages()
        self._emit(ConsoleEvent(">", f"Listing messages ({len(headers)} found)"))
        total_msgs = len(headers)
        for i, header in enumerate(headers, 1):
            self._set_status(ConnectionStatus.SYNCING, f"Reading message {i} of {total_msgs}")
            self._emit(ConsoleEvent("!", f"Reading message {i} of {total_msgs}", level="basic"))
            msg = node.read_message(header.bbs_id)
            now = datetime.now(timezone.utc)
            saved = self._store.save_message(Message(
                operator_id=self._operator.id,
                node_id=sync_node_id,
                bbs_id=header.bbs_id,
                from_call=header.from_call,
                to_call=header.to_call,
                subject=header.subject,
                body=msg.body,
                timestamp=_parse_bbs_date(header.date_str, now),
            ))
            if saved:
                retrieved += 1
                self._emit(ConsoleEvent("<", f"[{header.bbs_id}] {header.subject} from {header.from_call}"))
                self._emit(MessageReceivedEvent(
                    message_id=saved.id,
                    from_call=header.from_call,
                    subject=header.subject,
                ))

        # Phase 2: Send queued outbound messages targeted at this node
        sent = 0
        outbound = self._store.list_outbox_messages(self._operator.id, node_id=sync_node_id)
        for i, m in enumerate(outbound, 1):
            self._set_status(ConnectionStatus.SYNCING, f"Sending message {i} of {len(outbound)}")
            self._emit(ConsoleEvent("!", f"Sending message {i} of {len(outbound)}", level="basic"))
            self._emit(ConsoleEvent(">", f"Sending to {m.to_call}: {m.subject}"))
            try:
                node.send_message(m.to_call, m.subject, m.body)
                self._store.mark_message_sent(m.id)
                sent += 1
            except Exception as e:
                logger.exception("Failed to send message %s via node %s", m.id, sync_node_id)
                self._emit(ConsoleEvent("!", f"Failed to send to {m.to_call}: {e}"))

        # Phase 3: Send queued bulletins targeted at this node
        pending_bulletins = self._store.list_outbox_bulletins(self._operator.id, node_id=sync_node_id)
        for i, bul in enumerate(pending_bulletins, 1):
            self._set_status(ConnectionStatus.SYNCING, f"Posting bulletin {i} of {len(pending_bulletins)}")
            self._emit(ConsoleEvent("!", f"Posting bulletin {i} of {len(pending_bulletins)}", level="basic"))
            self._emit(ConsoleEvent(">", f"Posting bulletin to {bul.category}: {bul.subject}"))
            node.post_bulletin(bul.category, bul.subject, bul.body)
            self._store.mark_bulletin_sent(bul.id)

        # Phase 4: Save bulletin headers (body not retrieved yet)
        self._set_status(ConnectionStatus.SYNCING, "Listing bulletins…")
        self._emit(ConsoleEvent("!", "Listing bulletins…", level="basic"))
        bulletin_headers = node.list_bulletins()
        self._emit(ConsoleEvent(">", f"Listing bulletins ({len(bulletin_headers)} available)"))
        bulletin_now = datetime.now(timezone.utc)
        for header in bulletin_headers:
            self._store.save_bulletin(Bulletin(
                operator_id=self._operator.id,
                node_id=self._node_record.id,
                bbs_id=header.bbs_id,
                category=header.to_call,
                from_call=header.from_call,
                subject=header.subject,
                timestamp=_parse_bbs_date(header.date_str, bulletin_now),
            ))

        # Phase 5: Retrieve bodies for bulletins queued by the user
        pending = self._store.list_bulletins_pending_retrieval(self._node_record.id)
        bulletins_retrieved = 0
        total_pending = len(pending)
        for i, bul in enumerate(pending, 1):
            self._set_status(ConnectionStatus.SYNCING, f"Retrieving bulletin {i} of {total_pending}")
            self._emit(ConsoleEvent("!", f"Retrieving bulletin {i} of {total_pending}", level="basic"))
            try:
                raw = node.read_bulletin(bul.bbs_id)
            except Exception:
                logger.exception("Failed to retrieve bulletin %s", bul.bbs_id)
                self._emit(ConsoleEvent("!", f"Failed to retrieve bulletin {bul.bbs_id}"))
                continue
            self._store.update_bulletin_body(bul.id, raw.body)
            bulletins_retrieved += 1
            self._emit(ConsoleEvent("<", f"[{bul.bbs_id}] {bul.subject} from {bul.from_call}"))

        # Phase 6: Save file headers (content not retrieved yet)
        self._set_status(ConnectionStatus.SYNCING, "Listing files…")
        self._emit(ConsoleEvent("!", "Listing files…", level="basic"))
        try:
            file_headers = node.list_files()
            self._emit(ConsoleEvent(">", f"Listing files ({len(file_headers)} available)"))
            for header in file_headers:
                self._store.save_file_header(BBSFile(
                    id=None,
                    node_id=self._node_record.id,
                    directory=header.directory,
                    filename=header.filename,
                    size=header.size,
                    date_str=header.date_str,
                    description=header.description,
                    content=None,
                ))
        except Exception:
            logger.exception("Failed to list files")
            self._emit(ConsoleEvent("!", "Failed to list files"))

        # Phase 7: Retrieve files queued by the user
        pending_files = self._store.list_files_pending_retrieval(self._node_record.id)
        files_retrieved = 0
        total_files = len(pending_files)
        for i, f in enumerate(pending_files, 1):
            self._set_status(ConnectionStatus.SYNCING, f"Retrieving file {i} of {total_files}")
            self._emit(ConsoleEvent("!", f"Retrieving file {i} of {total_files}", level="basic"))
            try:
                raw = node.read_file(f.filename)
            except Exception:
                logger.exception("Failed to retrieve file %s", f.filename)
                self._emit(ConsoleEvent("!", f"Failed to retrieve file {f.filename}"))
                continue
            export_dir = Path(self._export_path or ".")
            path = export_dir / "files" / f.directory / f.filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw)
            self._store.update_file_content(f.id)
            files_retrieved += 1

        return retrieved, sent, bulletins_retrieved, files_retrieved

    def _do_auto_forward(self) -> None:
        neighbors = self._store.get_node_neighbors(self._node_record.id)
        for hop in neighbors:
            derived_path = self._node_record.hop_path + [hop]
            try:
                from open_packet.ax25.connection import _split_callsign
                from open_packet.node.bpq import BPQNode
                if self._node_record.path_strategy == "path_route":
                    call, ax25_ssid = _split_callsign(derived_path[0].callsign)
                    self._connection.connect(call, ax25_ssid)
                    temp_node = BPQNode(
                        connection=self._connection,
                        node_callsign=self._node_record.callsign,
                        node_ssid=self._node_record.ssid,
                        my_callsign=self._operator.callsign,
                        my_ssid=self._operator.ssid,
                        hop_path=derived_path,
                        path_strategy="path_route",
                    )
                else:  # digipeat
                    call, ax25_ssid = _split_callsign(hop.callsign)
                    via = self._node_record.hop_path or None
                    self._connection.connect(call, ax25_ssid, via_path=via)
                    temp_node = BPQNode(
                        connection=self._connection,
                        node_callsign=self._node_record.callsign,
                        node_ssid=self._node_record.ssid,
                        my_callsign=self._operator.callsign,
                        my_ssid=self._operator.ssid,
                        hop_path=[],
                        path_strategy="digipeat",
                    )
                self._emit(ConsoleEvent(">", f"Auto-forwarding via {hop.callsign}"))
                temp_node.connect_node()
                self._run_sync_phases(temp_node, node_id=self._node_record.id)
            except Exception as e:
                logger.exception("Auto-forward to %s failed", hop.callsign)
                self._emit(ConsoleEvent("!", f"Auto-forward to {hop.callsign} failed: {e}"))
            finally:
                try:
                    self._connection.disconnect()
                except Exception:
                    pass

    def _do_check_mail(self) -> None:
        node_addr = f"{self._node_record.callsign}-{self._node_record.ssid}"
        self._set_status(ConnectionStatus.CONNECTING)
        self._emit(ConsoleEvent(">", f"Connecting to {node_addr}..."))
        new_neighbors: list = []
        shorter_path_candidates: list = []
        try:
            if (self._node_record.path_strategy == "path_route"
                    and self._node_record.hop_path):
                first = self._node_record.hop_path[0]
                from open_packet.ax25.connection import _split_callsign
                call, ssid = _split_callsign(first.callsign)
                self._connection.connect(call, ssid)
            else:
                via = self._node_record.hop_path if self._node_record.path_strategy == "digipeat" else None
                if via:
                    self._connection.connect(
                        self._node_record.callsign,
                        self._node_record.ssid,
                        via_path=via,
                    )
                else:
                    self._connection.connect(
                        self._node_record.callsign,
                        self._node_record.ssid,
                    )
            self._node.wait_for_prompt()
            if self._auto_discover:
                new_neighbors, shorter_path_candidates = self._discover_neighbors()
            self._node.connect_node()
            self._emit(ConsoleEvent("<", f"Connected to {node_addr}"))
            self._set_status(ConnectionStatus.SYNCING)

            retrieved, sent, bulletins_retrieved, files_retrieved = self._run_sync_phases(
                self._node, node_id=self._node_record.id
            )

            self._last_sync = datetime.now(timezone.utc)
            self._messages_last_sync = retrieved
            parts = [f"{retrieved} new", f"{bulletins_retrieved} bulletins", f"{sent} sent"]
            if files_retrieved:
                parts.append(f"{files_retrieved} files")
            self._emit(ConsoleEvent("<", f"Sync complete: {', '.join(parts)}", level="basic"))
            self._emit(SyncCompleteEvent(
                messages_retrieved=retrieved,
                messages_sent=sent,
                bulletins_retrieved=bulletins_retrieved,
                files_retrieved=files_retrieved,
            ))
        finally:
            self._connection.disconnect()
            self._emit(ConsoleEvent("<", "Disconnected"))
            self._set_status(ConnectionStatus.DISCONNECTED)
            if new_neighbors or shorter_path_candidates:
                self._emit(NeighborsDiscoveredEvent(
                    node_id=self._node_record.id,
                    new_neighbors=new_neighbors,
                    shorter_path_candidates=shorter_path_candidates,
                ))

        # Phase 5: Auto-forward via discovered neighbors
        if self._node_record.auto_forward:
            self._do_auto_forward()

    def _do_group_sync(self, cmd: GroupSyncCommand) -> None:
        """Sync each node in a group in order, skipping unreachable nodes."""
        self._emit(ConsoleEvent("!", f"Starting group sync: {cmd.group_name}", level="basic"))
        results: list[GroupSyncNodeResult] = []

        for target in cmd.targets:
            node_label = target.node_record.label
            node_addr = f"{target.node_record.callsign}-{target.node_record.ssid}"
            self._emit(ConsoleEvent(">", f"[Group {cmd.group_name}] Connecting to {node_addr}…"))
            try:
                node_record = target.node_record
                connection = target.connection
                bpq_node = target.bpq_node

                if node_record.path_strategy == "path_route" and node_record.hop_path:
                    first = node_record.hop_path[0]
                    from open_packet.ax25.connection import _split_callsign
                    call, ssid = _split_callsign(first.callsign)
                    connection.connect(call, ssid)
                else:
                    via = node_record.hop_path if node_record.path_strategy == "digipeat" else None
                    if via:
                        connection.connect(node_record.callsign, node_record.ssid, via_path=via)
                    else:
                        connection.connect(node_record.callsign, node_record.ssid)

                bpq_node.wait_for_prompt()
                bpq_node.connect_node()
                self._emit(ConsoleEvent("<", f"[Group {cmd.group_name}] Connected to {node_addr}"))

                retrieved, sent, bulletins_retrieved, files_retrieved = self._run_sync_phases(bpq_node)
                results.append(GroupSyncNodeResult(
                    node_label=node_label,
                    skipped=False,
                    messages_retrieved=retrieved,
                    messages_sent=sent,
                    bulletins_retrieved=bulletins_retrieved,
                    files_retrieved=files_retrieved,
                ))
                self._emit(ConsoleEvent(
                    "<",
                    f"[Group {cmd.group_name}] {node_label}: {retrieved} msgs, {bulletins_retrieved} bulletins",
                    level="basic",
                ))
            except Exception as e:
                logger.warning("Group sync: skipping %s due to error: %s", node_label, e)
                results.append(GroupSyncNodeResult(
                    node_label=node_label,
                    skipped=True,
                    skip_reason=str(e),
                ))
                self._emit(ConsoleEvent(
                    "!",
                    f"[Group {cmd.group_name}] {node_label}: skipped ({e})",
                    level="basic",
                ))
            finally:
                try:
                    target.connection.disconnect()
                except Exception:
                    pass

        skipped = [r for r in results if r.skipped]
        synced = [r for r in results if not r.skipped]
        total_msgs = sum(r.messages_retrieved for r in synced)
        total_bulletins = sum(r.bulletins_retrieved for r in synced)
        skip_names = ", ".join(r.node_label for r in skipped)
        summary_parts = [f"{len(synced)} node(s) synced"]
        if skipped:
            summary_parts.append(f"{len(skipped)} skipped ({skip_names})")
        summary_parts.append(f"{total_msgs} new msgs")
        summary_parts.append(f"{total_bulletins} bulletins")
        self._emit(ConsoleEvent("!", f"Group sync complete: {', '.join(summary_parts)}", level="basic"))
        self._emit(GroupSyncCompleteEvent(group_name=cmd.group_name, results=results))

    def _do_send_message(self, cmd: SendMessageCommand) -> None:
        now = datetime.now(timezone.utc)
        node_ids = cmd.node_ids if cmd.node_ids else [self._node_record.id]
        saved = self._store.save_message(Message(
            operator_id=self._operator.id,
            node_id=node_ids[0],
            bbs_id="",
            from_call=f"{self._operator.callsign}-{self._operator.ssid}",
            to_call=cmd.to_call,
            subject=cmd.subject,
            body=cmd.body,
            timestamp=now,
            queued=True,
        ))
        if saved and saved.id is not None:
            self._store.add_message_target_nodes(saved.id, node_ids)
        self._emit(MessageQueuedEvent())

    def _do_delete_message(self, cmd: DeleteMessageCommand) -> None:
        self._store.delete_message(cmd.message_id)
        self._emit(MessageQueuedEvent())

    def _do_post_bulletin(self, cmd: PostBulletinCommand) -> None:
        from uuid import uuid4
        node_ids = cmd.node_ids if cmd.node_ids else [self._node_record.id]
        now = datetime.now(timezone.utc)
        for node_id in node_ids:
            bulletin = Bulletin(
                operator_id=self._operator.id,
                node_id=node_id,
                bbs_id=f"OUT-{uuid4().hex[:8]}",
                category=cmd.category,
                from_call=self._operator.callsign,
                subject=cmd.subject,
                body=cmd.body,
                timestamp=now,
                queued=True,
                sent=False,
            )
            self._store.save_bulletin(bulletin)
        self._emit(MessageQueuedEvent())
