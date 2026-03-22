from __future__ import annotations
import sqlite3
from datetime import datetime
from typing import Optional

from open_packet.store.models import Operator, Node, Message, Bulletin


class Database:
    def __init__(self, path: str):
        self._path = path
        self._conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def table_names(self) -> list[str]:
        assert self._conn
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return [r["name"] for r in rows]

    def _create_schema(self) -> None:
        assert self._conn
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS operators (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                callsign TEXT NOT NULL,
                ssid INTEGER NOT NULL,
                label TEXT NOT NULL,
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                callsign TEXT NOT NULL,
                ssid INTEGER NOT NULL DEFAULT 0,
                node_type TEXT NOT NULL,
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operator_id INTEGER NOT NULL REFERENCES operators(id),
                node_id INTEGER NOT NULL REFERENCES nodes(id),
                bbs_id TEXT NOT NULL,
                from_call TEXT NOT NULL,
                to_call TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                read INTEGER NOT NULL DEFAULT 0,
                sent INTEGER NOT NULL DEFAULT 0,
                deleted INTEGER NOT NULL DEFAULT 0,
                synced_at TEXT
            );

            CREATE TABLE IF NOT EXISTS bulletins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operator_id INTEGER NOT NULL REFERENCES operators(id),
                node_id INTEGER NOT NULL REFERENCES nodes(id),
                bbs_id TEXT NOT NULL,
                category TEXT NOT NULL,
                from_call TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                read INTEGER NOT NULL DEFAULT 0,
                synced_at TEXT
            );
        """)
        self._conn.commit()

    def insert_operator(self, op: Operator) -> Operator:
        assert self._conn
        cur = self._conn.execute(
            "INSERT INTO operators (callsign, ssid, label, is_default) VALUES (?, ?, ?, ?)",
            (op.callsign, op.ssid, op.label, int(op.is_default)),
        )
        self._conn.commit()
        return self.get_operator(cur.lastrowid)  # type: ignore

    def get_operator(self, id: int) -> Optional[Operator]:
        assert self._conn
        row = self._conn.execute("SELECT * FROM operators WHERE id=?", (id,)).fetchone()
        if not row:
            return None
        return Operator(
            id=row["id"], callsign=row["callsign"], ssid=row["ssid"],
            label=row["label"], is_default=bool(row["is_default"]),
        )

    def get_default_operator(self) -> Optional[Operator]:
        assert self._conn
        row = self._conn.execute(
            "SELECT * FROM operators WHERE is_default=1 LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return Operator(
            id=row["id"], callsign=row["callsign"], ssid=row["ssid"],
            label=row["label"], is_default=bool(row["is_default"]),
        )

    def insert_node(self, node: Node) -> Node:
        assert self._conn
        cur = self._conn.execute(
            "INSERT INTO nodes (label, callsign, ssid, node_type, is_default) VALUES (?, ?, ?, ?, ?)",
            (node.label, node.callsign, node.ssid, node.node_type, int(node.is_default)),
        )
        self._conn.commit()
        return self.get_node(cur.lastrowid)  # type: ignore

    def get_node(self, id: int) -> Optional[Node]:
        assert self._conn
        row = self._conn.execute("SELECT * FROM nodes WHERE id=?", (id,)).fetchone()
        if not row:
            return None
        return Node(
            id=row["id"], label=row["label"], callsign=row["callsign"],
            ssid=row["ssid"], node_type=row["node_type"],
            is_default=bool(row["is_default"]),
        )

    def get_default_node(self) -> Optional[Node]:
        assert self._conn
        row = self._conn.execute(
            "SELECT * FROM nodes WHERE is_default=1 LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return Node(
            id=row["id"], label=row["label"], callsign=row["callsign"],
            ssid=row["ssid"], node_type=row["node_type"],
            is_default=bool(row["is_default"]),
        )
