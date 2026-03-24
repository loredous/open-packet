from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Operator:
    callsign: str
    ssid: int
    label: str
    is_default: bool = False
    id: Optional[int] = None
    created_at: Optional[datetime] = None


@dataclass
class Node:
    label: str
    callsign: str
    ssid: int
    node_type: str  # e.g. "bpq"
    is_default: bool = False
    id: Optional[int] = None
    created_at: Optional[datetime] = None


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
    id: Optional[int] = None
    synced_at: Optional[datetime] = None
