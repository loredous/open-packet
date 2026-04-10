from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from open_packet.store.database import Database
from open_packet.store.models import Message, Bulletin, BBSFile


class Store:
    def __init__(self, db: Database):
        self._db = db

    @property
    def _conn(self):
        return self._db._conn

    def save_message(self, msg: Message) -> Message:
        assert self._conn
        # Avoid duplicates by bbs_id + node_id
        # NOTE: messages with bbs_id="" (outbound queue) will all match each other
        # for the same node_id — known PoC limitation.
        if not msg.queued:
            existing = self._conn.execute(
                "SELECT id FROM messages WHERE bbs_id=? AND node_id=?",
                (msg.bbs_id, msg.node_id),
            ).fetchone()
            if existing:
                return self.get_message(existing["id"])  # type: ignore

        cur = self._conn.execute(
            """INSERT INTO messages
               (operator_id, node_id, bbs_id, from_call, to_call, subject, body,
                timestamp, read, sent, deleted, queued, archived, synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                msg.operator_id, msg.node_id, msg.bbs_id, msg.from_call,
                msg.to_call, msg.subject, msg.body,
                msg.timestamp.isoformat(),
                int(msg.read), int(msg.sent), int(msg.deleted), int(msg.queued),
                int(msg.archived),
                None if msg.queued else datetime.now(timezone.utc).isoformat(),
                # synced_at=NULL for queued (composed) messages; they were never retrieved from a BBS.
            ),
        )
        self._conn.commit()
        return self.get_message(cur.lastrowid)  # type: ignore

    def get_message(self, id: int) -> Optional[Message]:
        assert self._conn
        row = self._conn.execute("SELECT * FROM messages WHERE id=?", (id,)).fetchone()
        if not row:
            return None
        return self._row_to_message(row)

    def list_messages(self, operator_id: int, include_deleted: bool = False) -> list[Message]:
        assert self._conn
        query = "SELECT * FROM messages WHERE operator_id=?"
        params: list = [operator_id]
        if not include_deleted:
            query += " AND deleted=0"
        query += " AND archived=0"
        query += " ORDER BY timestamp DESC"
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_message(r) for r in rows]

    def list_archived_messages(self, operator_id: int) -> list[Message]:
        assert self._conn
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE operator_id=? AND archived=1 AND deleted=0 ORDER BY timestamp DESC",
            (operator_id,),
        ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def list_outbox(self, operator_id: int) -> list[Message | Bulletin]:
        assert self._conn
        msg_rows = self._conn.execute(
            "SELECT * FROM messages WHERE operator_id=? AND queued=1 AND sent=0 AND deleted=0",
            (operator_id,),
        ).fetchall()
        bul_rows = self._conn.execute(
            "SELECT * FROM bulletins WHERE operator_id=? AND queued=1 AND sent=0",
            (operator_id,),
        ).fetchall()
        messages = [self._row_to_message(r) for r in msg_rows]
        bulletins = [self._row_to_bulletin(r) for r in bul_rows]
        combined: list[Message | Bulletin] = messages + bulletins
        combined.sort(key=lambda x: x.timestamp)
        return combined

    def list_outbox_messages(self, operator_id: int) -> list[Message]:
        assert self._conn
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE operator_id=? AND queued=1 AND sent=0 AND deleted=0 ORDER BY timestamp ASC",
            (operator_id,),
        ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def list_outbox_bulletins(self, operator_id: int) -> list[Bulletin]:
        assert self._conn
        rows = self._conn.execute(
            "SELECT * FROM bulletins WHERE operator_id=? AND queued=1 AND sent=0 ORDER BY timestamp ASC",
            (operator_id,),
        ).fetchall()
        return [self._row_to_bulletin(r) for r in rows]

    def count_folder_stats(self, operator_id: int) -> dict[str, tuple | dict]:
        # Return shape:
        #   "Inbox":     (total: int, unread: int)
        #   "Sent":      (total: int,)
        #   "Outbox":    (total: int,)  — messages + bulletins combined
        #   "Bulletins": dict[category: str, (total: int, unread: int)]
        assert self._conn
        row = self._conn.execute(
            """SELECT
                   COALESCE(SUM(CASE WHEN queued=0 AND sent=0 AND deleted=0 AND archived=0            THEN 1 ELSE 0 END), 0) AS inbox_total,
                   COALESCE(SUM(CASE WHEN queued=0 AND sent=0 AND deleted=0 AND archived=0 AND read=0 THEN 1 ELSE 0 END), 0) AS inbox_unread,
                   COALESCE(SUM(CASE WHEN sent=1 AND deleted=0                                        THEN 1 ELSE 0 END), 0) AS sent_total,
                   COALESCE(SUM(CASE WHEN queued=1 AND sent=0 AND deleted=0                           THEN 1 ELSE 0 END), 0) AS msg_outbox,
                   COALESCE(SUM(CASE WHEN archived=1 AND deleted=0                                    THEN 1 ELSE 0 END), 0) AS archive_total,
                   COALESCE(SUM(CASE WHEN archived=1 AND deleted=0 AND read=0                         THEN 1 ELSE 0 END), 0) AS archive_unread
               FROM messages WHERE operator_id=?""",
            (operator_id,),
        ).fetchone()
        bul_outbox_row = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM bulletins WHERE operator_id=? AND queued=1 AND sent=0",
            (operator_id,),
        ).fetchone()
        outbox_count = row["msg_outbox"] + bul_outbox_row["cnt"]

        bul_rows = self._conn.execute(
            """SELECT category,
                      COUNT(*) AS total,
                      SUM(CASE WHEN read=0 THEN 1 ELSE 0 END) AS unread
               FROM bulletins WHERE operator_id=? AND queued=0
               GROUP BY category""",
            (operator_id,),
        ).fetchall()
        bulletins_stats: dict[str, tuple[int, int]] = {
            r["category"]: (r["total"], r["unread"]) for r in bul_rows
        }

        return {
            "Inbox":     (row["inbox_total"], row["inbox_unread"]),
            "Sent":      (row["sent_total"],),
            "Outbox":    (outbox_count,),
            "Archive":   (row["archive_total"], row["archive_unread"]),
            "Bulletins": bulletins_stats,
        }

    def mark_message_read(self, id: int) -> None:
        assert self._conn
        self._conn.execute("UPDATE messages SET read=1 WHERE id=?", (id,))
        self._conn.commit()

    def mark_message_sent(self, id: int) -> None:
        assert self._conn
        self._conn.execute("UPDATE messages SET sent=1 WHERE id=?", (id,))
        self._conn.commit()

    def delete_message(self, id: int) -> None:
        assert self._conn
        self._conn.execute("UPDATE messages SET deleted=1 WHERE id=?", (id,))
        self._conn.commit()

    def archive_message(self, id: int) -> None:
        assert self._conn
        self._conn.execute("UPDATE messages SET archived=1 WHERE id=?", (id,))
        self._conn.commit()

    def unarchive_message(self, id: int) -> None:
        assert self._conn
        self._conn.execute("UPDATE messages SET archived=0 WHERE id=?", (id,))
        self._conn.commit()

    def save_bulletin(self, bul: Bulletin) -> Bulletin:
        assert self._conn
        if not bul.queued:
            existing = self._conn.execute(
                "SELECT id FROM bulletins WHERE bbs_id=? AND node_id=?",
                (bul.bbs_id, bul.node_id),
            ).fetchone()
            if existing:
                return self._get_bulletin(existing["id"])  # type: ignore

        body_val = bul.body if bul.body is not None else "\x00"   # NUL byte = header-only sentinel
        # synced_at = when we retrieved the full body (not when we listed the header)
        # For queued (outgoing) bulletins, synced_at stays None.
        # For received bulletins, synced_at is None if header-only; set by update_bulletin_body().
        synced_at = None

        cur = self._conn.execute(
            """INSERT INTO bulletins
               (operator_id, node_id, bbs_id, category, from_call, subject, body,
                timestamp, read, queued, sent, wants_retrieval, synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                bul.operator_id, bul.node_id, bul.bbs_id, bul.category,
                bul.from_call, bul.subject, body_val,
                bul.timestamp.isoformat(), int(bul.read),
                int(bul.queued), int(bul.sent),
                int(bul.wants_retrieval),
                synced_at,
            ),
        )
        self._conn.commit()
        return self._get_bulletin(cur.lastrowid)  # type: ignore

    def list_bulletins(self, operator_id: int, category: Optional[str] = None) -> list[Bulletin]:
        assert self._conn
        query = "SELECT * FROM bulletins WHERE operator_id=? AND queued=0"
        params: list = [operator_id]
        if category:
            query += " AND category=?"
            params.append(category)
        query += " ORDER BY timestamp DESC"
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_bulletin(r) for r in rows]

    def _get_bulletin(self, id: int) -> Optional[Bulletin]:
        assert self._conn
        row = self._conn.execute("SELECT * FROM bulletins WHERE id=?", (id,)).fetchone()
        if not row:
            return None
        return self._row_to_bulletin(row)

    def _row_to_message(self, row) -> Message:
        keys = row.keys()
        return Message(
            id=row["id"], operator_id=row["operator_id"], node_id=row["node_id"],
            bbs_id=row["bbs_id"], from_call=row["from_call"], to_call=row["to_call"],
            subject=row["subject"], body=row["body"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            read=bool(row["read"]), sent=bool(row["sent"]), deleted=bool(row["deleted"]),
            queued=bool(row["queued"]),
            archived=bool(row["archived"]) if "archived" in keys else False,
            synced_at=datetime.fromisoformat(row["synced_at"]) if row["synced_at"] else None,
        )

    def _row_to_bulletin(self, row) -> Bulletin:
        return Bulletin(
            id=row["id"], operator_id=row["operator_id"], node_id=row["node_id"],
            bbs_id=row["bbs_id"], category=row["category"], from_call=row["from_call"],
            subject=row["subject"],
            body=row["body"] if row["body"] != "\x00" else None,   # NUL sentinel → None
            timestamp=datetime.fromisoformat(row["timestamp"]),
            read=bool(row["read"]),
            queued=bool(row["queued"]),
            sent=bool(row["sent"]),
            wants_retrieval=bool(row["wants_retrieval"]),
            synced_at=datetime.fromisoformat(row["synced_at"]) if row["synced_at"] else None,
        )

    def delete_bulletin(self, id: int) -> None:
        assert self._conn
        self._conn.execute("DELETE FROM bulletins WHERE id=?", (id,))
        self._conn.commit()

    def mark_bulletin_read(self, id: int) -> None:
        assert self._conn
        self._conn.execute("UPDATE bulletins SET read=1 WHERE id=?", (id,))
        self._conn.commit()

    def mark_bulletin_sent(self, id: int) -> None:
        assert self._conn
        self._conn.execute("UPDATE bulletins SET sent=1 WHERE id=?", (id,))
        self._conn.commit()

    def mark_bulletin_wants_retrieval(self, id: int) -> None:
        assert self._conn
        self._conn.execute("UPDATE bulletins SET wants_retrieval=1 WHERE id=?", (id,))
        self._conn.commit()

    def toggle_bulletin_wants_retrieval(self, id: int) -> None:
        assert self._conn
        self._conn.execute(
            "UPDATE bulletins SET wants_retrieval = NOT wants_retrieval WHERE id=?", (id,)
        )
        self._conn.commit()

    def list_bulletins_pending_retrieval(self, node_id: int) -> list[Bulletin]:
        """Bulletins marked for retrieval whose body has not yet been fetched."""
        assert self._conn
        rows = self._conn.execute(
            "SELECT * FROM bulletins WHERE node_id=? AND wants_retrieval=1 AND body=?",
            (node_id, "\x00"),
        ).fetchall()
        return [self._row_to_bulletin(r) for r in rows]

    def update_bulletin_body(self, id: int, body: str) -> None:
        assert self._conn
        self._conn.execute(
            "UPDATE bulletins SET body=?, synced_at=? WHERE id=?",
            (body, datetime.now(timezone.utc).isoformat(), id),
        )
        self._conn.commit()

    def bulletin_exists(self, bbs_id: str, node_id: int) -> bool:
        assert self._conn
        row = self._conn.execute(
            "SELECT id FROM bulletins WHERE bbs_id=? AND node_id=?",
            (bbs_id, node_id),
        ).fetchone()
        return row is not None

    def list_nodes(self) -> list:
        return self._db.list_nodes()

    def upsert_node_neighbor(self, node_id: int, callsign: str, port: int | None) -> None:
        assert self._conn
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO node_neighbors (node_id, callsign, port, first_seen, last_seen)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(node_id, callsign) DO UPDATE SET last_seen=excluded.last_seen""",
            (node_id, callsign, port, now, now),
        )
        self._conn.commit()

    def get_node_neighbors(self, node_id: int) -> list:
        assert self._conn
        from open_packet.store.models import NodeHop
        rows = self._conn.execute(
            "SELECT callsign, port FROM node_neighbors WHERE node_id=? ORDER BY callsign",
            (node_id,),
        ).fetchall()
        return [NodeHop(callsign=r["callsign"], port=r["port"]) for r in rows]

    def save_file_header(self, f: BBSFile) -> None:
        self._db._conn.execute(
            """INSERT OR IGNORE INTO bbs_files
               (node_id, directory, filename, size, date_str, description, content, wants_retrieval)
               VALUES (?, ?, ?, ?, ?, ?, x'00', 0)""",
            (f.node_id, f.directory, f.filename, f.size, f.date_str, f.description),
        )
        self._db._conn.commit()

    def mark_file_wants_retrieval(self, file_id: int) -> None:
        self._db._conn.execute(
            "UPDATE bbs_files SET wants_retrieval=1 WHERE id=?", (file_id,)
        )
        self._db._conn.commit()

    def list_files_pending_retrieval(self, node_id: int) -> list:
        rows = self._db._conn.execute(
            "SELECT * FROM bbs_files WHERE node_id=? AND wants_retrieval=1 AND content=x'00' AND deleted=0",
            (node_id,),
        ).fetchall()
        return [self._row_to_bbs_file(r) for r in rows]

    def update_file_content(self, file_id: int) -> None:
        self._db._conn.execute(
            "UPDATE bbs_files SET content=x'01', wants_retrieval=0, synced_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), file_id),
        )
        self._db._conn.commit()

    def list_files(self, node_id: int, directory: str = "") -> list:
        if directory:
            rows = self._db._conn.execute(
                "SELECT * FROM bbs_files WHERE node_id=? AND directory=? AND deleted=0 ORDER BY filename",
                (node_id, directory),
            ).fetchall()
        else:
            rows = self._db._conn.execute(
                "SELECT * FROM bbs_files WHERE node_id=? AND deleted=0 ORDER BY directory, filename",
                (node_id,),
            ).fetchall()
        return [self._row_to_bbs_file(r) for r in rows]

    def count_file_stats(self, node_id: int) -> dict:
        rows = self._db._conn.execute(
            "SELECT directory, COUNT(*) as cnt FROM bbs_files WHERE node_id=? AND deleted=0 GROUP BY directory",
            (node_id,),
        ).fetchall()
        return {r["directory"]: r["cnt"] for r in rows}

    def _row_to_bbs_file(self, row) -> BBSFile:
        content_bytes = row["content"]
        if isinstance(content_bytes, bytes):
            content = content_bytes.decode("latin-1")
        else:
            content = content_bytes
        return BBSFile(
            id=row["id"],
            node_id=row["node_id"],
            directory=row["directory"],
            filename=row["filename"],
            size=row["size"],
            date_str=row["date_str"] or "",
            description=row["description"] or "",
            content=content,
            wants_retrieval=bool(row["wants_retrieval"]),
            synced_at=row["synced_at"],
        )
