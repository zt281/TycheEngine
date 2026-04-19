"""Data replay module for backtesting.

Reads recorded market data and replays events through the engine
with simulated time advancement.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.trading import events
from modules.trading.clock.clock import SimulatedClock
from tyche.module import TycheModule
from tyche.types import Endpoint

logger = logging.getLogger(__name__)


class ReplayModule(TycheModule):
    """Replays recorded market data through the engine for backtesting.

    Reads JSONL files produced by DataRecorderModule and publishes events
    in timestamp order, advancing the simulated clock accordingly.
    """

    def __init__(
        self,
        engine_endpoint: Endpoint,
        data_dir: str = "./data/recorded",
        speed: float = 0.0,  # 0 = as fast as possible
        module_id: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(engine_endpoint, module_id=module_id, **kwargs)
        self._data_dir = Path(data_dir)
        self._speed = speed
        self._clock = SimulatedClock()
        self._replayed_count = 0

    @property
    def clock(self) -> SimulatedClock:
        return self._clock

    @property
    def replayed_count(self) -> int:
        return self._replayed_count

    def replay_date(self, date_str: str, instrument_ids: Optional[List[str]] = None) -> int:
        """Replay all data for a given date.

        Args:
            date_str: Date in YYYY-MM-DD format.
            instrument_ids: Optional filter for specific instruments.

        Returns:
            Number of events replayed.
        """
        date_dir = self._data_dir / date_str
        if not date_dir.exists():
            logger.warning("No data directory for date: %s", date_str)
            return 0

        # Collect all events from all files, sorted by timestamp
        all_events: List[Dict[str, Any]] = []

        for jsonl_file in sorted(date_dir.glob("*.jsonl")):
            # Filter by instrument if specified
            if instrument_ids:
                file_instrument = jsonl_file.stem.rsplit("_", 1)[0]
                if file_instrument not in instrument_ids:
                    continue

            try:
                with open(jsonl_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            record = json.loads(line)
                            all_events.append(record)
            except (OSError, json.JSONDecodeError) as e:
                logger.error("Error reading %s: %s", jsonl_file, e)

        # Sort by timestamp
        all_events.sort(key=lambda r: r.get("timestamp", 0.0))

        logger.info("Replaying %d events for %s", len(all_events), date_str)

        last_ts = 0.0
        for record in all_events:
            if not self._running:
                break

            ts = record.get("timestamp", 0.0)
            payload = record.get("data", {})

            # Advance simulated clock
            self._clock.advance_to(ts)

            # Throttle if speed > 0
            if self._speed > 0 and last_ts > 0:
                delay = (ts - last_ts) / self._speed
                if delay > 0:
                    time.sleep(delay)

            # Broadcast clock update
            self.send_event(events.SYSTEM_CLOCK, self._clock.to_clock_payload())

            # Publish the event based on its type
            event_topic = self._determine_topic(payload)
            if event_topic:
                self.send_event(event_topic, payload)
                self._replayed_count += 1

            last_ts = ts

        logger.info("Replay complete: %d events", self._replayed_count)
        return self._replayed_count

    @staticmethod
    def _determine_topic(payload: Dict[str, Any]) -> Optional[str]:
        """Determine the event topic from payload content."""
        instrument_id = payload.get("instrument_id", "")

        if "bid" in payload and "ask" in payload:
            return events.quote_event(instrument_id)
        elif "side" in payload and "price" in payload and "order_id" not in payload:
            return events.trade_event(instrument_id)
        elif "timeframe" in payload:
            return events.bar_event(instrument_id, payload["timeframe"])
        elif "order_id" in payload and "fill_id" in payload:
            return events.fill_event(instrument_id)
        elif "order_id" in payload and "status" in payload:
            return events.ORDER_UPDATE

        return None
