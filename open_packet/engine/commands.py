# open_packet/engine/commands.py
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ConnectCommand:
    pass


@dataclass
class DisconnectCommand:
    pass


@dataclass
class CheckMailCommand:
    pass


@dataclass
class SendMessageCommand:
    to_call: str
    subject: str
    body: str
    node_ids: list[int] = field(default_factory=list)


@dataclass
class DeleteMessageCommand:
    message_id: int  # local DB id
    bbs_id: str      # BBS message id for the node command


@dataclass
class PostBulletinCommand:
    category: str
    subject: str
    body: str
    node_ids: list[int] = field(default_factory=list)


Command = ConnectCommand | DisconnectCommand | CheckMailCommand | SendMessageCommand | DeleteMessageCommand | PostBulletinCommand
