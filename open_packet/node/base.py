# open_packet/node/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


class NodeError(Exception):
    pass


@dataclass
class MessageHeader:
    bbs_id: str
    to_call: str
    from_call: str
    subject: str
    date_str: str = ""


@dataclass
class Message:
    header: MessageHeader
    body: str
    timestamp: Optional[datetime] = None


class NodeBase(ABC):
    @abstractmethod
    def connect_node(self) -> None: ...

    @abstractmethod
    def list_messages(self) -> list[MessageHeader]: ...

    @abstractmethod
    def read_message(self, bbs_id: str) -> Message: ...

    @abstractmethod
    def send_message(self, to_call: str, subject: str, body: str) -> None: ...

    @abstractmethod
    def delete_message(self, bbs_id: str) -> None: ...

    @abstractmethod
    def list_bulletins(self, category: str = "") -> list[MessageHeader]: ...

    @abstractmethod
    def read_bulletin(self, bbs_id: str) -> Message: ...
