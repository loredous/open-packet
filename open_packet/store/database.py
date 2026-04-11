from __future__ import annotations
import json as _json
import sqlite3
from datetime import datetime
from typing import Optional

from open_packet.store.models import Operator, Node, Message, Bulletin, Interface, BBSFile, NodeGroup


_KNOWN_SETTING_KEYS = frozenset({
    "export_path",
    "console_visible",
    "console_buffer",
    "auto_discover",
    "console_log_level",
    "scheduled_sr_enabled",
    "scheduled_sr_interval",
    "notifications_enabled",
})


def _hops_to_json(hops) -> str:
    return _json.dumps([{"callsign": h.callsign, "port": h.port} for h in hops])


def _json_to_hops(s: str):
    from open_packet.store.models import NodeHop
    try:
        return [NodeHop(**d) for d in _json.loads(s or "[]")]
    except Exception:
        return []


class Database:
    def __init__(self, path: str):
        self._path = path
        self._conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._create_schema()
        try:
            self._conn.execute(
                "ALTER TABLE messages ADD COLUMN queued INTEGER NOT NULL DEFAULT 0"
            )
            self._conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

        try:
            self._conn.execute(
                "ALTER TABLE nodes ADD COLUMN interface_id INTEGER REFERENCES interfaces(id)"
            )
            self._conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

        for sql in [
            "ALTER TABLE bulletins ADD COLUMN queued INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE bulletins ADD COLUMN sent INTEGER NOT NULL DEFAULT 0",
        ]:
            try:
                self._conn.execute(sql)
                self._conn.commit()
            except sqlite3.OperationalError:
                pass  # column already exists

        try:
            self._conn.execute(
                "ALTER TABLE bulletins ADD COLUMN wants_retrieval INTEGER NOT NULL DEFAULT 0"
            )
            self._conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

        for sql in [
            "ALTER TABLE nodes ADD COLUMN hop_path TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE nodes ADD COLUMN path_strategy TEXT NOT NULL DEFAULT 'path_route'",
            "ALTER TABLE nodes ADD COLUMN auto_forward INTEGER NOT NULL DEFAULT 0",
        ]:
            try:
                self._conn.execute(sql)
                self._conn.commit()
            except sqlite3.OperationalError:
                pass  # column already exists

        for key, value in [
            ("export_path", "~/.local/share/open-packet/export"),
            ("console_visible", "false"),
            ("console_buffer", "500"),
            ("auto_discover", "true"),
            ("console_log_level", "basic"),
            ("scheduled_sr_enabled", "false"),
            ("scheduled_sr_interval", "30"),
            ("notifications_enabled", "true"),
        ]:
            self._conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        self._conn.commit()

        for table in ("operators", "nodes", "interfaces", "bulletins"):
            try:
                self._conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0"
                )
                self._conn.commit()
            except sqlite3.OperationalError:
                pass  # column already exists

        try:
            self._conn.execute(
                "ALTER TABLE messages ADD COLUMN archived INTEGER NOT NULL DEFAULT 0"
            )
            self._conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def get_setting(self, key: str) -> str:
        assert self._conn
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown setting: {key!r}")
        return row[0]

    def set_setting(self, key: str, value: str) -> None:
        assert self._conn
        if key not in _KNOWN_SETTING_KEYS:
            raise KeyError(f"Unknown setting: {key!r}")
        self._conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._conn.commit()

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

            CREATE TABLE IF NOT EXISTS interfaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                iface_type TEXT NOT NULL,
                host TEXT,
                port INTEGER,
                username TEXT,
                password TEXT,
                device TEXT,
                baud INTEGER
            );

            CREATE TABLE IF NOT EXISTS nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                callsign TEXT NOT NULL,
                ssid INTEGER NOT NULL DEFAULT 0,
                node_type TEXT NOT NULL,
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                interface_id INTEGER REFERENCES interfaces(id)
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
                queued INTEGER NOT NULL DEFAULT 0,
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
                queued INTEGER NOT NULL DEFAULT 0,
                sent INTEGER NOT NULL DEFAULT 0,
                synced_at TEXT
            );

            CREATE TABLE IF NOT EXISTS node_neighbors (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id     INTEGER NOT NULL REFERENCES nodes(id),
                callsign    TEXT NOT NULL,
                port        INTEGER,
                first_seen  TEXT NOT NULL,
                last_seen   TEXT NOT NULL,
                UNIQUE(node_id, callsign)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bbs_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id INTEGER NOT NULL REFERENCES nodes(id),
                directory TEXT NOT NULL DEFAULT '',
                filename TEXT NOT NULL,
                size INTEGER,
                date_str TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT x'00',
                wants_retrieval INTEGER NOT NULL DEFAULT 0,
                synced_at TEXT,
                deleted INTEGER NOT NULL DEFAULT 0,
                UNIQUE(node_id, filename)
            );

            CREATE TABLE IF NOT EXISTS message_target_nodes (
                message_id INTEGER NOT NULL REFERENCES messages(id),
                node_id    INTEGER NOT NULL REFERENCES nodes(id),
                PRIMARY KEY (message_id, node_id)
            );

            CREATE TABLE IF NOT EXISTS node_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                deleted INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS node_group_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL REFERENCES node_groups(id),
                node_id INTEGER NOT NULL REFERENCES nodes(id),
                position INTEGER NOT NULL DEFAULT 0,
                UNIQUE(group_id, node_id)
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
        row = self._conn.execute("SELECT * FROM operators WHERE id=? AND deleted=0", (id,)).fetchone()
        if not row:
            return None
        return Operator(
            id=row["id"], callsign=row["callsign"], ssid=row["ssid"],
            label=row["label"], is_default=bool(row["is_default"]),
        )

    def get_default_operator(self) -> Optional[Operator]:
        assert self._conn
        row = self._conn.execute(
            "SELECT * FROM operators WHERE is_default=1 AND deleted=0 LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return Operator(
            id=row["id"], callsign=row["callsign"], ssid=row["ssid"],
            label=row["label"], is_default=bool(row["is_default"]),
        )

    def _row_to_node(self, row) -> Node:
        keys = row.keys()
        return Node(
            id=row["id"], label=row["label"], callsign=row["callsign"],
            ssid=row["ssid"], node_type=row["node_type"],
            is_default=bool(row["is_default"]),
            interface_id=row["interface_id"],
            hop_path=_json_to_hops(row["hop_path"] if "hop_path" in keys else "[]"),
            path_strategy=row["path_strategy"] if "path_strategy" in keys else "path_route",
            auto_forward=bool(row["auto_forward"]) if "auto_forward" in keys else False,
        )

    def insert_node(self, node: Node) -> Node:
        assert self._conn
        cur = self._conn.execute(
            """INSERT INTO nodes
               (label, callsign, ssid, node_type, is_default, interface_id,
                hop_path, path_strategy, auto_forward)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (node.label, node.callsign, node.ssid, node.node_type,
             int(node.is_default), node.interface_id,
             _hops_to_json(node.hop_path), node.path_strategy, int(node.auto_forward)),
        )
        self._conn.commit()
        return self.get_node(cur.lastrowid)  # type: ignore

    def get_node(self, id: int) -> Optional[Node]:
        assert self._conn
        row = self._conn.execute("SELECT * FROM nodes WHERE id=? AND deleted=0", (id,)).fetchone()
        if not row:
            return None
        return self._row_to_node(row)

    def get_default_node(self) -> Optional[Node]:
        assert self._conn
        row = self._conn.execute(
            "SELECT * FROM nodes WHERE is_default=1 AND deleted=0 LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return self._row_to_node(row)

    def list_operators(self) -> list[Operator]:
        assert self._conn
        rows = self._conn.execute("SELECT * FROM operators WHERE deleted=0 ORDER BY id").fetchall()
        return [
            Operator(id=r["id"], callsign=r["callsign"], ssid=r["ssid"],
                     label=r["label"], is_default=bool(r["is_default"]))
            for r in rows
        ]

    def list_nodes(self) -> list[Node]:
        assert self._conn
        rows = self._conn.execute("SELECT * FROM nodes WHERE deleted=0 ORDER BY id").fetchall()
        return [self._row_to_node(r) for r in rows]

    def update_operator(self, op: Operator) -> None:
        assert self._conn
        assert op.id is not None, "Cannot update operator without id"
        self._conn.execute(
            "UPDATE operators SET callsign=?, ssid=?, label=?, is_default=? WHERE id=?",
            (op.callsign, op.ssid, op.label, int(op.is_default), op.id),
        )
        self._conn.commit()

    def update_node(self, node: Node) -> None:
        assert self._conn
        assert node.id is not None, "Cannot update node without id"
        self._conn.execute(
            """UPDATE nodes SET label=?, callsign=?, ssid=?, node_type=?,
               is_default=?, interface_id=?, hop_path=?, path_strategy=?, auto_forward=?
               WHERE id=?""",
            (node.label, node.callsign, node.ssid, node.node_type,
             int(node.is_default), node.interface_id,
             _hops_to_json(node.hop_path), node.path_strategy, int(node.auto_forward),
             node.id),
        )
        self._conn.commit()

    def insert_interface(self, iface: Interface) -> Interface:
        assert self._conn
        cur = self._conn.execute(
            """INSERT INTO interfaces (label, iface_type, host, port, username, password, device, baud)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (iface.label, iface.iface_type, iface.host, iface.port,
             iface.username, iface.password, iface.device, iface.baud),
        )
        self._conn.commit()
        return self.get_interface(cur.lastrowid)  # type: ignore

    def get_interface(self, id: int) -> Optional[Interface]:
        assert self._conn
        row = self._conn.execute("SELECT * FROM interfaces WHERE id=? AND deleted=0", (id,)).fetchone()
        if not row:
            return None
        return Interface(
            id=row["id"], label=row["label"], iface_type=row["iface_type"],
            host=row["host"], port=row["port"],
            username=row["username"], password=row["password"],
            device=row["device"], baud=row["baud"],
        )

    def list_interfaces(self) -> list[Interface]:
        assert self._conn
        rows = self._conn.execute("SELECT * FROM interfaces WHERE deleted=0 ORDER BY id").fetchall()
        return [
            Interface(
                id=r["id"], label=r["label"], iface_type=r["iface_type"],
                host=r["host"], port=r["port"],
                username=r["username"], password=r["password"],
                device=r["device"], baud=r["baud"],
            )
            for r in rows
        ]

    def update_interface(self, iface: Interface) -> None:
        assert self._conn
        assert iface.id is not None, "Cannot update interface without id"
        self._conn.execute(
            """UPDATE interfaces SET label=?, iface_type=?, host=?, port=?,
               username=?, password=?, device=?, baud=? WHERE id=?""",
            (iface.label, iface.iface_type, iface.host, iface.port,
             iface.username, iface.password, iface.device, iface.baud, iface.id),
        )
        self._conn.commit()

    def delete_interface(self, id: int) -> None:
        assert self._conn
        try:
            self._conn.execute("DELETE FROM interfaces WHERE id=?", (id,))
            self._conn.commit()
        except sqlite3.IntegrityError as e:
            raise ValueError(
                f"Cannot delete interface {id}: it is still referenced by one or more nodes"
            ) from e

    def clear_default_operator(self) -> None:
        assert self._conn
        self._conn.execute("UPDATE operators SET is_default=0 WHERE is_default=1")
        self._conn.commit()

    def clear_default_node(self) -> None:
        assert self._conn
        self._conn.execute("UPDATE nodes SET is_default=0 WHERE is_default=1")
        self._conn.commit()

    def soft_delete_operator(self, op_id: int) -> None:
        assert self._conn
        self._conn.execute(
            "UPDATE operators SET deleted=1, is_default=0 WHERE id=?", (op_id,)
        )
        self._conn.commit()

    def soft_delete_node(self, node_id: int) -> None:
        assert self._conn
        self._conn.execute(
            "UPDATE nodes SET deleted=1, is_default=0 WHERE id=?", (node_id,)
        )
        self._conn.commit()

    def soft_delete_interface(self, iface_id: int) -> None:
        assert self._conn
        count = self._conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE interface_id=? AND deleted=0", (iface_id,)
        ).fetchone()[0]
        if count > 0:
            raise ValueError(
                f"Cannot delete interface {iface_id}: it is referenced by one or more nodes"
            )
        self._conn.execute(
            "UPDATE interfaces SET deleted=1 WHERE id=?", (iface_id,)
        )
        self._conn.commit()

    def count_operator_dependents(self, op_id: int) -> tuple[int, int]:
        assert self._conn
        msg_count = self._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE operator_id=?", (op_id,)
        ).fetchone()[0]
        bul_count = self._conn.execute(
            "SELECT COUNT(*) FROM bulletins WHERE operator_id=?", (op_id,)
        ).fetchone()[0]
        return (msg_count, bul_count)

    def add_message_target_nodes(self, message_id: int, node_ids: list[int]) -> None:
        assert self._conn
        for node_id in node_ids:
            self._conn.execute(
                "INSERT OR IGNORE INTO message_target_nodes (message_id, node_id) VALUES (?, ?)",
                (message_id, node_id),
            )
        self._conn.commit()

    def get_message_target_nodes(self, message_id: int) -> list[int]:
        assert self._conn
        rows = self._conn.execute(
            "SELECT node_id FROM message_target_nodes WHERE message_id=?", (message_id,)
        ).fetchall()
        return [r["node_id"] for r in rows]

    def count_node_dependents(self, node_id: int) -> tuple[int, int]:
        assert self._conn
        msg_count = self._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE node_id=?", (node_id,)
        ).fetchone()[0]
        bul_count = self._conn.execute(
            "SELECT COUNT(*) FROM bulletins WHERE node_id=?", (node_id,)
        ).fetchone()[0]
        return (msg_count, bul_count)

    # --- Node Group CRUD ---

    def insert_node_group(self, group: NodeGroup) -> NodeGroup:
        assert self._conn
        cur = self._conn.execute(
            "INSERT INTO node_groups (name) VALUES (?)", (group.name,)
        )
        group_id = cur.lastrowid
        for position, node_id in enumerate(group.node_ids):
            self._conn.execute(
                "INSERT INTO node_group_members (group_id, node_id, position) VALUES (?, ?, ?)",
                (group_id, node_id, position),
            )
        self._conn.commit()
        return self.get_node_group(group_id)  # type: ignore

    def get_node_group(self, group_id: int) -> Optional[NodeGroup]:
        assert self._conn
        row = self._conn.execute(
            "SELECT * FROM node_groups WHERE id=? AND deleted=0", (group_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_node_group(row)

    def list_node_groups(self) -> list[NodeGroup]:
        assert self._conn
        rows = self._conn.execute(
            "SELECT * FROM node_groups WHERE deleted=0 ORDER BY id"
        ).fetchall()
        return [self._row_to_node_group(r) for r in rows]

    def update_node_group(self, group: NodeGroup) -> None:
        assert self._conn
        assert group.id is not None, "Cannot update node group without id"
        self._conn.execute(
            "UPDATE node_groups SET name=? WHERE id=?", (group.name, group.id)
        )
        self._conn.execute(
            "DELETE FROM node_group_members WHERE group_id=?", (group.id,)
        )
        for position, node_id in enumerate(group.node_ids):
            self._conn.execute(
                "INSERT INTO node_group_members (group_id, node_id, position) VALUES (?, ?, ?)",
                (group.id, node_id, position),
            )
        self._conn.commit()

    def soft_delete_node_group(self, group_id: int) -> None:
        assert self._conn
        self._conn.execute(
            "UPDATE node_groups SET deleted=1 WHERE id=?", (group_id,)
        )
        self._conn.commit()

    def _row_to_node_group(self, row) -> NodeGroup:
        assert self._conn
        member_rows = self._conn.execute(
            "SELECT node_id FROM node_group_members WHERE group_id=? ORDER BY position",
            (row["id"],),
        ).fetchall()
        node_ids = [r["node_id"] for r in member_rows]
        return NodeGroup(id=row["id"], name=row["name"], node_ids=node_ids)
