from __future__ import annotations
from abc import ABC, abstractmethod


class ConnectionError(Exception):
    pass


class ConnectionBase(ABC):
    @abstractmethod
    def connect(self, callsign: str, ssid: int) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def send_frame(self, data: bytes) -> None: ...

    @abstractmethod
    def receive_frame(self, timeout: float = 5.0) -> bytes: ...
