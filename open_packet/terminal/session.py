# open_packet/terminal/session.py
from __future__ import annotations
import queue
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from open_packet.link.base import ConnectionBase

if TYPE_CHECKING:
    from open_packet.store.models import Interface


@dataclass
class TerminalConnectResult:
    label: str
    interface: "Interface"
    target_callsign: str
    target_ssid: int


class TerminalSession:
    def __init__(
        self,
        label: str,
        connection: ConnectionBase,
        target_callsign: str = "",
        target_ssid: int = 0,
    ) -> None:
        self.label = label
        self.status: Literal["connecting", "connected", "disconnected", "error"] = "connecting"
        self.has_unread = False
        self._connection = connection
        self._target_callsign = target_callsign
        self._target_ssid = target_ssid
        self._rx_queue: queue.Queue[str] = queue.Queue()
        self._recv_buffer: str = ""
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def send(self, text: str) -> None:
        if self.status != "connected":
            return
        self._connection.send_frame((text + "\r").encode())

    def disconnect(self) -> None:
        self._stop_event.set()
        try:
            self._connection.disconnect()
        except Exception:
            pass
        self._thread.join(timeout=5.0)
        self.status = "disconnected"

    def poll(self) -> list[str]:
        chunks: list[str] = []
        while not self._rx_queue.empty():
            try:
                chunks.append(self._rx_queue.get_nowait())
            except queue.Empty:
                break
        if not chunks:
            return []
        self._recv_buffer += "".join(chunks)
        self._recv_buffer = self._recv_buffer.replace("\r\n", "\r")
        parts = self._recv_buffer.split("\r")
        self._recv_buffer = parts[-1]
        return parts[:-1]

    def _run(self) -> None:
        try:
            self._connection.connect(self._target_callsign, self._target_ssid)
            self.status = "connected"
        except Exception as e:
            self.status = "error"
            self._rx_queue.put(f"[connection error: {e}]\r")
            return
        while not self._stop_event.is_set():
            try:
                data = self._connection.receive_frame(timeout=1.0)
                if data:
                    self._rx_queue.put(data.decode(errors="replace"))
            except Exception as e:
                self.status = "error"
                self._rx_queue.put(f"[error: {e}]\r")
                break
        if self.status not in ("error", "disconnected"):
            self.status = "disconnected"
