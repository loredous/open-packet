from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Interface:
    id: Optional[int] = None
    label: str = ""
    iface_type: str = ""          # "telnet" | "kiss_tcp" | "kiss_serial"
    host: Optional[str] = None    # telnet + kiss_tcp
    port: Optional[int] = None    # telnet + kiss_tcp
    username: Optional[str] = None  # telnet only
    password: Optional[str] = None  # telnet only
    device: Optional[str] = None  # kiss_serial only
    baud: Optional[int] = None    # kiss_serial only


@dataclass
class Operator:
    callsign: str
    ssid: int
    label: str
    is_default: bool = False
    id: Optional[int] = None
    created_at: Optional[datetime] = None


@dataclass
class NodeHop:
    callsign: str
    port: int | None = None


@dataclass
class Node:
    label: str
    callsign: str
    ssid: int
    node_type: str  # e.g. "bpq"
    is_default: bool = False
    interface_id: Optional[int] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    hop_path: list["NodeHop"] = field(default_factory=list)
    path_strategy: str = "path_route"
    auto_forward: bool = False


@dataclass
class Message:
    operator_id: int
    node_id: int
    bbs_id: str
    from_call: str
    to_call: str
    subject: str
    body: str
    timestamp: datetime
    read: bool = False
    sent: bool = False
    deleted: bool = False
    queued: bool = False
    id: Optional[int] = None
    synced_at: Optional[datetime] = None


@dataclass
class Bulletin:
    operator_id: int
    node_id: int
    bbs_id: str
    category: str
    from_call: str
    subject: str
    body: str
    timestamp: datetime
    read: bool = False
    queued: bool = False
    sent: bool = False
    id: Optional[int] = None
    synced_at: Optional[datetime] = None
