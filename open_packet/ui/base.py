# open_packet/ui/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from open_packet.engine.commands import Command
from open_packet.engine.events import Event


class UIBase(ABC):
    @abstractmethod
    def send_command(self, cmd: Command) -> None: ...

    @abstractmethod
    def on_event(self, event: Event) -> None: ...
