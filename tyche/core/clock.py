import time
from typing import Protocol


class Clock(Protocol):
    def now_ns(self) -> int: ...


class LiveClock:
    """Wall-clock time in nanoseconds since Unix epoch."""

    def now_ns(self) -> int:
        return time.time_ns()


class SimClock:
    """Deterministic clock for backtesting; advance manually."""

    def __init__(self, start_ns: int = 0):
        self._ns = start_ns

    def now_ns(self) -> int:
        return self._ns

    def advance(self, delta_ns: int) -> None:
        self._ns += delta_ns
