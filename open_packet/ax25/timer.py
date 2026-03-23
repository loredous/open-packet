from __future__ import annotations
import time
from typing import Optional


class Timer:
    def __init__(self) -> None:
        self._deadline: Optional[float] = None

    def start(self, seconds: float) -> None:
        self._deadline = time.monotonic() + seconds

    def stop(self) -> None:
        self._deadline = None

    @property
    def running(self) -> bool:
        return self._deadline is not None

    @property
    def expired(self) -> bool:
        return self._deadline is not None and time.monotonic() >= self._deadline
