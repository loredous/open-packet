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
    archived: bool = False
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
    timestamp: datetime                   # moved before body so Optional body can have a default
    body: Optional[str] = None            # None = header only, not yet retrieved
    read: bool = False
    queued: bool = False
    sent: bool = False
    wants_retrieval: bool = False
    id: Optional[int] = None
    synced_at: Optional[datetime] = None


@dataclass
class NodeGroup:
    name: str
    node_ids: list[int] = field(default_factory=list)  # ordered list of node IDs
    id: Optional[int] = None


@dataclass
class BBSFile:
    id: Optional[int]
    node_id: int
    directory: str          # BBS directory name (e.g. "ARES", "WEATHER")
    filename: str           # unique identifier within the BBS
    size: Optional[int]     # bytes, from DIR listing
    date_str: str           # raw date string from BBS
    description: str        # one-line description from DIR listing
    content: Optional[str] = None   # None = not yet retrieved; "\x00" = header-only sentinel in DB; "\x01" = retrieved (saved to disk)
    wants_retrieval: bool = False
    synced_at: Optional[datetime] = None
