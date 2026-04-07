from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from open_packet.store.models import NodeHop


class ConnectionError(Exception):
    pass


class ConnectionBase(ABC):
    @abstractmethod
    def connect(self, callsign: str, ssid: int,
                via_path: "list[NodeHop] | None" = None) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def send_frame(self, data: bytes) -> None: ...

    @abstractmethod
    def receive_frame(self, timeout: float = 5.0) -> bytes | None: ...
