from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from open_packet.store.database import Database
from open_packet.store.models import Message, Bulletin


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
                timestamp, read, sent, deleted, queued, synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                msg.operator_id, msg.node_id, msg.bbs_id, msg.from_call,
                msg.to_call, msg.subject, msg.body,
                msg.timestamp.isoformat(),
                int(msg.read), int(msg.sent), int(msg.deleted), int(msg.queued),
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
        query += " ORDER BY timestamp DESC"
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_message(r) for r in rows]

    def list_outbox(self, operator_id: int) -> list[Message | Bulletin]:
        assert self._conn
        msg_rows = self._conn.execute(
            "SELECT * FROM messages WHERE operator_id=? AND queued=1 AND sent=0 AND deleted=0 ORDER BY timestamp ASC",
            (operator_id,),
        ).fetchall()
        bul_rows = self._conn.execute(
            "SELECT * FROM bulletins WHERE operator_id=? AND queued=1 AND sent=0 ORDER BY timestamp ASC",
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
        assert self._conn
        row = self._conn.execute(
            """SELECT
                   COALESCE(SUM(CASE WHEN queued=0 AND sent=0 AND deleted=0            THEN 1 ELSE 0 END), 0) AS inbox_total,
                   COALESCE(SUM(CASE WHEN queued=0 AND sent=0 AND deleted=0 AND read=0 THEN 1 ELSE 0 END), 0) AS inbox_unread,
                   COALESCE(SUM(CASE WHEN sent=1 AND deleted=0                         THEN 1 ELSE 0 END), 0) AS sent_total,
                   COALESCE(SUM(CASE WHEN queued=1 AND sent=0 AND deleted=0            THEN 1 ELSE 0 END), 0) AS msg_outbox
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

    def save_bulletin(self, bul: Bulletin) -> Bulletin:
        assert self._conn
        if not bul.queued:
            existing = self._conn.execute(
                "SELECT id FROM bulletins WHERE bbs_id=? AND node_id=?",
                (bul.bbs_id, bul.node_id),
            ).fetchone()
            if existing:
                return self._get_bulletin(existing["id"])  # type: ignore

        cur = self._conn.execute(
            """INSERT INTO bulletins
               (operator_id, node_id, bbs_id, category, from_call, subject, body,
                timestamp, read, queued, sent, synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                bul.operator_id, bul.node_id, bul.bbs_id, bul.category,
                bul.from_call, bul.subject, bul.body,
                bul.timestamp.isoformat(), int(bul.read),
                int(bul.queued), int(bul.sent),
                None if bul.queued else datetime.now(timezone.utc).isoformat(),
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
        return Message(
            id=row["id"], operator_id=row["operator_id"], node_id=row["node_id"],
            bbs_id=row["bbs_id"], from_call=row["from_call"], to_call=row["to_call"],
            subject=row["subject"], body=row["body"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            read=bool(row["read"]), sent=bool(row["sent"]), deleted=bool(row["deleted"]),
            queued=bool(row["queued"]),
        )

    def _row_to_bulletin(self, row) -> Bulletin:
        return Bulletin(
            id=row["id"], operator_id=row["operator_id"], node_id=row["node_id"],
            bbs_id=row["bbs_id"], category=row["category"], from_call=row["from_call"],
            subject=row["subject"], body=row["body"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            read=bool(row["read"]),
            queued=bool(row["queued"]),
            sent=bool(row["sent"]),
            synced_at=datetime.fromisoformat(row["synced_at"]) if row["synced_at"] else None,
        )
