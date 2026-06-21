"""Tests for GreeksEngine - TASK-12: on_compute_greeks event handler adaptation.

Verifies the Greeks Engine correctly receives CTP Gateway's
``send_compute_greeks`` event (replacing the legacy ``request_event``
``compute_greeks`` job pattern from the ctp_gateway_cpp improvement v1).
"""

import logging
from datetime import date, timedelta

import pytest

from src.modules.greeks_engine.config import GreeksConfig
from src.modules.greeks_engine.greeks import GreeksEngine


class TestGreeksEngineOnComputeGreeks:
    """Verify on_compute_greeks event handler matches handle_compute_greeks output."""

    @pytest.fixture
    def engine(self):
        """Create a GreeksEngine with pre-populated mappings (no network)."""
        config = GreeksConfig(
            risk_free_rate=0.02,
            underlyings={"SHFE": ["ag"]},
            underlying_map={"ag2506C6000": "ag2506"},
            expiry_map={"ag2506C6000": (date.today() + timedelta(days=30)).isoformat()},
            underlying_instruments={"ag2506"},
            engine_host="127.0.0.1",
            engine_port=5555,
        )
        engine = GreeksEngine(config)
        engine._resolved = True
        # Pre-populate underlying price cache
        engine.underlying_prices["ag2506"] = 6200.0
        return engine

    def test_on_compute_greeks_exists(self, engine):
        """RED: on_compute_greeks method must exist on GreeksEngine."""
        assert hasattr(engine, "on_compute_greeks")
        assert callable(engine.on_compute_greeks)

    def test_on_compute_greeks_produces_same_greeks_as_handle(self, engine):
        """RED: on_compute_greeks must produce same Greeks as handle_compute_greeks."""
        payload = {
            "instrument_id": "ag2506-C-6000",
            "last_price": 250.0,
            "bid_price1": 248.0,
            "ask_price1": 252.0,
            "volume": 100,
        }

        # Call the job handler (synchronous, returns dict)
        job_result = engine.handle_compute_greeks(payload)

        # Call the event handler (async consumer, no return value)
        # But it should still compute and publish the same Greeks
        engine.on_compute_greeks(payload)

        # Both should succeed (status ok from job handler)
        assert job_result["status"] == "ok"
        assert job_result["instrument_id"] == "ag2506-C-6000"

    def test_on_compute_greeks_skips_non_option(self, engine):
        """RED: on_compute_greeks should skip non-option instruments gracefully."""
        payload = {
            "instrument_id": "ag2506",  # futures, not an option
            "last_price": 6200.0,
        }
        # Should not raise; just return None (fire-and-forget consumer)
        result = engine.on_compute_greeks(payload)
        assert result is None

    def test_on_compute_greeks_skips_when_unresolved(self, engine):
        """RED: on_compute_greeks should skip when instruments not yet resolved."""
        engine._resolved = False
        payload = {
            "instrument_id": "ag2506-C-6000",
            "last_price": 250.0,
        }
        result = engine.on_compute_greeks(payload)
        assert result is None

    def test_on_compute_greeks_skips_when_no_underlying_price(self, engine):
        """RED: on_compute_greeks should skip when underlying price is missing."""
        engine.underlying_prices.clear()
        payload = {
            "instrument_id": "ag2506-C-6000",
            "last_price": 250.0,
        }
        result = engine.on_compute_greeks(payload)
        assert result is None

    def test_on_compute_greeks_warns_on_empty_instrument_id(self, engine, caplog):
        """GREEN: Empty instrument_id must log a warning (not silently drop)."""
        payload = {"instrument_id": "", "last_price": 100.0}
        with caplog.at_level(logging.WARNING, logger="src.modules.greeks_engine.greeks"):
            result = engine.on_compute_greeks(payload)
        assert result is None
        assert any(
            "empty or missing instrument_id" in record.message
            for record in caplog.records
        ), f"Expected warning about empty instrument_id; got: {[r.message for r in caplog.records]}"

    def test_on_compute_greeks_accepts_full_ctp_gateway_payload(self, engine, caplog):
        """GREEN: on_compute_greeks must consume the full ctp_gateway_cpp tick_to_payload shape.

        The C++ gateway emits a payload with fields: instrument_id,
        exchange_id, last_price, volume, bid_price1, bid_volume1,
        ask_price1, ask_volume1, upper_limit, lower_limit, open/high/low
        prices, pre_settle, open_interest, turnover, update_time,
        update_millisec, trading_day. The simplified path only consumes a
        subset but must not choke on the full payload.
        """
        payload = {
            "instrument_id": "ag2506-C-6000",
            "exchange_id": "SHFE",
            "last_price": 250.0,
            "volume": 100,
            "bid_price1": 248.0,
            "bid_volume1": 5,
            "ask_price1": 252.0,
            "ask_volume1": 3,
            "upper_limit": 320.0,
            "lower_limit": 180.0,
            "open_price": 245.0,
            "high_price": 255.0,
            "low_price": 240.0,
            "pre_settle": 248.0,
            "open_interest": 12345.0,
            "turnover": 2500000.0,
            "update_time": "09:30:15",
            "update_millisec": 123,
            "trading_day": "20260614",
        }
        result = engine.on_compute_greeks(payload)
        # Must not raise and must return None (fire-and-forget)
        assert result is None


class TestSendComputeGreeksHandlerRegistration:
    """Verify the send_compute_greeks event is registered for subscription."""

    def test_send_compute_greeks_handler_is_registered(self, engine_from_config):
        """GREEN: _register_handler("send_compute_greeks", ...) must wire the handler.

        Without this registration, the engine's SUB socket will not
        subscribe to the topic that ctp_gateway_cpp publishes via
        ``send_event("send_compute_greeks", ...)``.
        """
        engine = engine_from_config
        # The handler must be discoverable under the bare topic name
        assert "send_compute_greeks" in engine._handlers
        handler, pattern = engine._handlers["send_compute_greeks"]
        # Bound methods are fresh objects on each access; compare underlying functions
        assert handler.__func__ is engine.on_compute_greeks.__func__

    def test_on_quote_handler_is_registered_for_future_quotes(self, engine_from_config):
        """GREEN: on_quote handler must be registered for ctp_gateway_cpp quote broadcast."""
        engine = engine_from_config
        assert "quote" in engine._handlers
        handler, _ = engine._handlers["quote"]
        assert handler.__func__ is engine.on_quote.__func__

    def test_compute_greeks_job_handler_is_registered(self, engine_from_config):
        """GREEN: handle_compute_greeks must win the compute_greeks topic.

        Without explicit registration, ``inspect.getmembers`` ordering is
        undefined and ``on_compute_greeks`` could overwrite the job handler,
        causing ``request_event("compute_greeks", ...)`` to silently swallow
        the job as a fire-and-forget event.
        """
        engine = engine_from_config
        # handle_* methods are stripped to bare name for lookup
        assert "compute_greeks" in engine._handlers
        handler, pattern = engine._handlers["compute_greeks"]
        assert handler.__func__ is engine.handle_compute_greeks.__func__
        # Job handlers carry InterfacePattern.HANDLE
        from src.tyche.types import InterfacePattern
        assert pattern == InterfacePattern.HANDLE

    def test_greeks_update_producer_is_declared(self, engine_from_config):
        """GREEN: send_greeks_update must declare a greeks_update producer interface."""
        engine = engine_from_config
        producer_names = [
            iface.name for iface in engine._interfaces
            if iface.event_type == "greeks_update"
        ]
        assert "send_greeks_update" in producer_names

    @pytest.fixture
    def engine_from_config(self):
        """Create a bare GreeksEngine (no resolved state)."""
        config = GreeksConfig(
            risk_free_rate=0.02,
            underlyings={"SHFE": ["ag"]},
            engine_host="127.0.0.1",
            engine_port=5555,
        )
        return GreeksEngine(config)


class TestNormalizeOptionId:
    """Verify _normalize_option_id handles both CTP and CZCE option id formats."""

    def test_ctp_dashed_format_is_normalized(self):
        """GREEN: 'ag2506-C-6000' must become 'ag2506C6000' (CTP format)."""
        assert GreeksEngine._normalize_option_id("ag2506-C-6000") == "ag2506C6000"

    def test_ctp_put_dashed_format_is_normalized(self):
        """GREEN: 'ag2506-P-6000' must become 'ag2506P6000' (CTP put format)."""
        assert GreeksEngine._normalize_option_id("ag2506-P-6000") == "ag2506P6000"

    def test_czce_format_passes_through_unchanged(self):
        """GREEN: 'TA608C6700' (CZCE no-dash format) must pass through unchanged."""
        assert GreeksEngine._normalize_option_id("TA608C6700") == "TA608C6700"

    def test_czce_put_format_passes_through_unchanged(self):
        """GREEN: 'TA608P6700' (CZCE put no-dash) must pass through unchanged."""
        assert GreeksEngine._normalize_option_id("TA608P6700") == "TA608P6700"

    def test_futures_id_passes_through_unchanged(self):
        """GREEN: A regular futures id (no dashes) must pass through unchanged."""
        assert GreeksEngine._normalize_option_id("ag2506") == "ag2506"

    def test_returns_str_type(self):
        """GREEN: Return type must always be str (was previously mis-annotated as bool)."""
        result = GreeksEngine._normalize_option_id("ag2506-C-6000")
        assert isinstance(result, str)
        assert isinstance(GreeksEngine._normalize_option_id("TA608C6700"), str)
