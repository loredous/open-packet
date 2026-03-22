from __future__ import annotations
from abc import ABC, abstractmethod


class TransportError(Exception):
    pass


class TransportBase(ABC):
    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def send_bytes(self, data: bytes) -> None: ...

    @abstractmethod
    def receive_bytes(self, timeout: float = 5.0) -> bytes: ...
