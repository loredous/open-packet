# open_packet/engine/events.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from open_packet.store.models import Node, NodeHop


class ConnectionStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    SYNCING = "syncing"
    ERROR = "error"


@dataclass
class ConnectionStatusEvent:
    status: ConnectionStatus
    detail: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MessageReceivedEvent:
    message_id: int
    from_call: str
    subject: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SyncCompleteEvent:
    messages_retrieved: int
    messages_sent: int
    bulletins_retrieved: int = 0
    files_retrieved: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ErrorEvent:
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MessageQueuedEvent:
    pass


@dataclass
class ConsoleEvent:
    direction: str  # ">" sent, "<" received, "!" error/info
    text: str
    level: str = "basic"


@dataclass
class NeighborsDiscoveredEvent:
    node_id: int
    new_neighbors: list  # list[NodeHop]
    shorter_path_candidates: list  # list[tuple[Node, list[NodeHop]]]


@dataclass
class GroupSyncNodeResult:
    """Result for a single node's sync within a group sync operation."""
    node_label: str
    skipped: bool
    skip_reason: str = ""
    messages_retrieved: int = 0
    messages_sent: int = 0
    bulletins_retrieved: int = 0
    files_retrieved: int = 0


@dataclass
class GroupSyncCompleteEvent:
    """Emitted when a group sync operation finishes (all nodes attempted)."""
    group_name: str
    results: list  # list[GroupSyncNodeResult]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


Event = ConnectionStatusEvent | MessageReceivedEvent | SyncCompleteEvent | ErrorEvent | MessageQueuedEvent | ConsoleEvent | NeighborsDiscoveredEvent | GroupSyncCompleteEvent
