# open_packet/engine/commands.py
from __future__ import annotations
from dataclasses import dataclass


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


@dataclass
class DeleteMessageCommand:
    message_id: int  # local DB id
    bbs_id: str      # BBS message id for the node command


@dataclass
class PostBulletinCommand:
    category: str
    subject: str
    body: str


@dataclass
class UploadFileCommand:
    local_path: str       # absolute path on the local filesystem
    bbs_filename: str     # filename as it will appear on the BBS
    description: str      # one-line description shown in DIR listing


Command = ConnectCommand | DisconnectCommand | CheckMailCommand | SendMessageCommand | DeleteMessageCommand | PostBulletinCommand | UploadFileCommand
