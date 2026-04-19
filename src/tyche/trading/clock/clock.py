"""Clock implementations for live trading and backtesting.

The clock broadcasts system.clock events so all modules share a consistent
view of time. In live mode this is wall-clock time; in backtest mode it is
simulated time driven by data replay.
"""

import logging
import threading
import time
from typing import Any, Dict, Optional

from tyche.module import TycheModule
from tyche.trading import events
from tyche.types import Endpoint

logger = logging.getLogger(__name__)


class LiveClockModule(TycheModule):
    """Broadcasts wall-clock time at a configurable interval.

    Used in live trading to provide consistent timestamps across modules.
    """

    def __init__(
        self,
        engine_endpoint: Endpoint,
        interval: float = 1.0,
        module_id: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(engine_endpoint, module_id=module_id, **kwargs)
        self._interval = interval
        self._clock_thread: Optional[threading.Thread] = None

    def start_nonblocking(self) -> None:
        """Start the module and clock broadcasting thread."""
        super().start_nonblocking()
        self._clock_thread = threading.Thread(
            target=self._clock_loop, daemon=True, name="live-clock"
        )
        self._clock_thread.start()

    def _clock_loop(self) -> None:
        """Periodically broadcast current time."""
        while self._running:
            now = time.time()
            self.send_event(
                events.SYSTEM_CLOCK,
                {"timestamp": now, "mode": "live"},
            )
            self._stop_event.wait(self._interval)

    @staticmethod
    def now() -> float:
        """Get current wall-clock time."""
        return time.time()


class SimulatedClock:
    """Simulated clock for backtesting - driven by replay events.

    Not a TycheModule itself; instead used by the ReplayModule to
    advance time deterministically.
    """

    def __init__(self, start_time: float = 0.0):
        self._current_time = start_time
        self._speed_multiplier = 1.0

    @property
    def current_time(self) -> float:
        """Get current simulated time."""
        return self._current_time

    def advance_to(self, timestamp: float) -> None:
        """Advance clock to a specific timestamp."""
        if timestamp < self._current_time:
            logger.warning(
                "Clock cannot go backwards: current=%f, requested=%f",
                self._current_time,
                timestamp,
            )
            return
        self._current_time = timestamp

    def advance_by(self, seconds: float) -> None:
        """Advance clock by a duration."""
        self._current_time += seconds

    def set_speed(self, multiplier: float) -> None:
        """Set replay speed multiplier (for throttled replay)."""
        self._speed_multiplier = max(0.0, multiplier)

    @property
    def speed(self) -> float:
        return self._speed_multiplier

    def to_clock_payload(self) -> Dict[str, Any]:
        """Generate payload for system.clock event."""
        return {
            "timestamp": self._current_time,
            "mode": "simulated",
            "speed": self._speed_multiplier,
        }
