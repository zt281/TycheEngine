"""Data recorder module - persists market data and trading events.

Subscribes to market data events and writes them to storage for
later replay/backtesting or analysis.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from tyche.module import TycheModule
from tyche.types import Endpoint

logger = logging.getLogger(__name__)


class DataRecorderModule(TycheModule):
    """Records market data and trading events to file storage.

    Subscribes to configurable event topics and writes each event
    as a JSON line to date-partitioned files.

    File structure:
        {data_dir}/{date}/{topic}.jsonl

    Future: Pluggable backends (SQLite, Parquet, ClickHouse).
    """

    def __init__(
        self,
        engine_endpoint: Endpoint,
        data_dir: str = "./data/recorded",
        instrument_ids: Optional[List[str]] = None,
        record_fills: bool = True,
        record_orders: bool = True,
        module_id: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(engine_endpoint, module_id=module_id, **kwargs)
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._instrument_ids = instrument_ids or []
        self._record_fills = record_fills
        self._record_orders = record_orders
        self._event_count = 0
        self._file_handles: Dict[str, Any] = {}

    def subscribe_instrument(self, instrument_id: str) -> None:
        """Add an instrument to track at runtime."""
        if instrument_id not in self._instrument_ids:
            self._instrument_ids.append(instrument_id)

    def on_streaming_quote(self, payload: Dict[str, Any]) -> None:
        """Record quote events."""
        self._record_event(payload)

    def on_streaming_trade(self, payload: Dict[str, Any]) -> None:
        """Record trade events."""
        self._record_event(payload)

    def on_streaming_bar(self, payload: Dict[str, Any]) -> None:
        """Record bar events."""
        self._record_event(payload)

    def on_broadcasted_fill(self, payload: Dict[str, Any]) -> None:
        """Record fill events."""
        if self._record_fills:
            self._record_event(payload)

    def on_broadcasted_order_update(self, payload: Dict[str, Any]) -> None:
        """Record order update events."""
        if self._record_orders:
            self._record_event(payload)

    def _record_event(self, payload: Dict[str, Any]) -> None:
        """Write event payload to file as JSON line."""
        record = {
            "timestamp": time.time(),
            "data": payload,
        }

        # Determine file path based on date and event type
        date_str = time.strftime("%Y-%m-%d")
        instrument_id = payload.get("instrument_id", "system")
        event_type = self._infer_event_type(payload)

        file_path = self._data_dir / date_str / f"{instrument_id}_{event_type}.jsonl"
        file_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
            self._event_count += 1
        except OSError as e:
            logger.error("Failed to write record: %s", e)

    @staticmethod
    def _infer_event_type(payload: Dict[str, Any]) -> str:
        """Infer event type from payload contents."""
        if "bid" in payload and "ask" in payload:
            return "quote"
        elif "side" in payload and "price" in payload and "order_id" not in payload:
            return "trade"
        elif "order_id" in payload and "fill_id" in payload:
            return "fill"
        elif "order_id" in payload and "status" in payload:
            return "order"
        elif "timeframe" in payload:
            return "bar"
        return "unknown"

    @property
    def event_count(self) -> int:
        """Total number of events recorded."""
        return self._event_count

    def stop(self) -> None:
        """Stop recording and close file handles."""
        super().stop()
        logger.info("DataRecorder stopped. Total events recorded: %d", self._event_count)
