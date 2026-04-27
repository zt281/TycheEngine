"""Unit tests for DataRecorderModule."""

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from modules.trading import events
from modules.trading.store.recorder import DataRecorderModule
from tyche.types import Endpoint


@pytest.fixture
def recorder(tmp_path: Path) -> DataRecorderModule:
    """Create a DataRecorderModule with a temporary data directory."""
    endpoint = Endpoint(host="127.0.0.1", port=5555)
    rec = DataRecorderModule(
        engine_endpoint=endpoint,
        data_dir=str(tmp_path / "recorded"),
        instrument_ids=["BTCUSDT.simulated.crypto"],
        record_fills=True,
        record_orders=True,
    )
    return rec


class TestRecordEvent:
    """Tests for _record_event behavior."""

    def test_writes_json_line_to_correct_path(self, recorder: DataRecorderModule, tmp_path: Path) -> None:
        """_record_event writes JSON line to {date}/{instrument_id}_{type}.jsonl."""
        payload = {
            "instrument_id": "BTCUSDT.simulated.crypto",
            "bid": "65000.00",
            "ask": "65001.00",
        }
        recorder._record_event(payload)

        date_str = time.strftime("%Y-%m-%d")
        file_path = tmp_path / "recorded" / date_str / "BTCUSDT.simulated.crypto_quote.jsonl"
        assert file_path.exists()

        lines = file_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert "timestamp" in record
        assert record["data"] == payload

    def test_creates_parent_directories(self, recorder: DataRecorderModule, tmp_path: Path) -> None:
        """_record_event creates parent directories if they do not exist."""
        payload = {
            "instrument_id": "ETHUSDT.simulated.crypto",
            "side": "BUY",
            "price": "3200.00",
        }
        recorder._record_event(payload)

        date_str = time.strftime("%Y-%m-%d")
        file_path = tmp_path / "recorded" / date_str / "ETHUSDT.simulated.crypto_trade.jsonl"
        assert file_path.exists()
        assert file_path.parent.is_dir()

    def test_multiple_events_appended_to_same_file(self, recorder: DataRecorderModule, tmp_path: Path) -> None:
        """Multiple events with same instrument and type are appended to the same file."""
        payload1 = {
            "instrument_id": "BTCUSDT.simulated.crypto",
            "bid": "65000.00",
            "ask": "65001.00",
        }
        payload2 = {
            "instrument_id": "BTCUSDT.simulated.crypto",
            "bid": "65002.00",
            "ask": "65003.00",
        }
        recorder._record_event(payload1)
        recorder._record_event(payload2)

        date_str = time.strftime("%Y-%m-%d")
        file_path = tmp_path / "recorded" / date_str / "BTCUSDT.simulated.crypto_quote.jsonl"
        lines = file_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["data"] == payload1
        assert json.loads(lines[1])["data"] == payload2

    def test_event_count_increments(self, recorder: DataRecorderModule) -> None:
        """event_count increments after each recorded event."""
        assert recorder.event_count == 0

        payload = {"instrument_id": "X", "bid": "1", "ask": "2"}
        recorder._record_event(payload)
        assert recorder.event_count == 1

        recorder._record_event(payload)
        assert recorder.event_count == 2

    def test_uses_system_for_missing_instrument_id(self, recorder: DataRecorderModule, tmp_path: Path) -> None:
        """When instrument_id is missing, 'system' is used in the filename."""
        payload = {"order_id": "abc123", "status": "NEW"}
        recorder._record_event(payload)

        date_str = time.strftime("%Y-%m-%d")
        file_path = tmp_path / "recorded" / date_str / "system_order.jsonl"
        assert file_path.exists()


class TestInferEventType:
    """Tests for _infer_event_type static method."""

    def test_quote(self) -> None:
        """Correctly identifies quote events (has bid + ask)."""
        payload = {"instrument_id": "X", "bid": "1.0", "ask": "2.0"}
        assert DataRecorderModule._infer_event_type(payload) == "quote"

    def test_trade(self) -> None:
        """Correctly identifies trade events (has side + price, no order_id)."""
        payload = {"instrument_id": "X", "side": "BUY", "price": "100.00"}
        assert DataRecorderModule._infer_event_type(payload) == "trade"

    def test_fill(self) -> None:
        """Correctly identifies fill events (has order_id + fill_id)."""
        payload = {
            "instrument_id": "X",
            "order_id": "abc",
            "fill_id": "fill-1",
            "side": "BUY",
            "price": "100.00",
        }
        assert DataRecorderModule._infer_event_type(payload) == "fill"

    def test_order(self) -> None:
        """Correctly identifies order events (has order_id + status)."""
        payload = {"instrument_id": "X", "order_id": "abc", "status": "NEW"}
        assert DataRecorderModule._infer_event_type(payload) == "order"

    def test_bar(self) -> None:
        """Correctly identifies bar events (has timeframe)."""
        payload = {"instrument_id": "X", "timeframe": "1m", "open": "100"}
        assert DataRecorderModule._infer_event_type(payload) == "bar"

    def test_unknown(self) -> None:
        """Returns 'unknown' for unrecognized payloads."""
        payload = {"instrument_id": "X", "foo": "bar"}
        assert DataRecorderModule._infer_event_type(payload) == "unknown"

    def test_quote_takes_precedence_over_trade(self) -> None:
        """Quote is identified before trade when both bid/ask and side/price are present."""
        payload = {"instrument_id": "X", "bid": "1", "ask": "2", "side": "BUY", "price": "1.5"}
        assert DataRecorderModule._infer_event_type(payload) == "quote"

    def test_fill_takes_precedence_over_order(self) -> None:
        """Fill is identified before order when both fill_id and status are present."""
        payload = {"instrument_id": "X", "order_id": "abc", "fill_id": "f1", "status": "FILLED"}
        assert DataRecorderModule._infer_event_type(payload) == "fill"


class TestSubscribeInstrument:
    """Tests for subscribe_instrument."""

    def test_adds_instrument(self, recorder: DataRecorderModule) -> None:
        """subscribe_instrument adds a new instrument to the list."""
        assert "ETHUSDT.simulated.crypto" not in recorder._instrument_ids
        recorder.subscribe_instrument("ETHUSDT.simulated.crypto")
        assert "ETHUSDT.simulated.crypto" in recorder._instrument_ids

    def test_adds_handlers(self, recorder: DataRecorderModule) -> None:
        """subscribe_instrument registers quote and trade handlers."""
        recorder.subscribe_instrument("ETHUSDT.simulated.crypto")

        quote_handler = recorder._handlers.get(f"on_{events.quote_event('ETHUSDT.simulated.crypto')}")
        trade_handler = recorder._handlers.get(f"on_{events.trade_event('ETHUSDT.simulated.crypto')}")

        assert quote_handler is not None
        assert trade_handler is not None
        assert quote_handler == recorder._record_event
        assert trade_handler == recorder._record_event

    def test_does_not_duplicate(self, recorder: DataRecorderModule) -> None:
        """subscribe_instrument does not duplicate an existing instrument."""
        recorder.subscribe_instrument("BTCUSDT.simulated.crypto")
        recorder.subscribe_instrument("BTCUSDT.simulated.crypto")
        assert recorder._instrument_ids.count("BTCUSDT.simulated.crypto") == 1


class TestEventCount:
    """Tests for event_count property."""

    def test_initial_zero(self, recorder: DataRecorderModule) -> None:
        """event_count starts at zero."""
        assert recorder.event_count == 0

    def test_increments_per_event(self, recorder: DataRecorderModule) -> None:
        """event_count increments once per recorded event."""
        payload = {"instrument_id": "X", "bid": "1", "ask": "2"}
        for _ in range(5):
            recorder._record_event(payload)
        assert recorder.event_count == 5


class TestErrorHandling:
    """Tests for error handling in _record_event."""

    def test_oserror_logged(self, recorder: DataRecorderModule, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """OSError during write is logged and does not crash."""
        with patch("builtins.open", side_effect=OSError("disk full")):
            payload = {"instrument_id": "X", "bid": "1", "ask": "2"}
            # Should not raise
            recorder._record_event(payload)
        assert "Failed to write record" in caplog.text
