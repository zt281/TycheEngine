"""Unit tests for StrategyContext, StrategyModule, and MovingAverageCrossStrategy."""

from decimal import Decimal
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from modules.trading import events
from modules.trading.models.enums import OrderStatus, OrderType, PositionSide, Side
from modules.trading.models.order import Order, OrderUpdate
from modules.trading.models.position import Position
from modules.trading.models.tick import Bar, Quote
from modules.trading.strategy.base import StrategyModule
from modules.trading.strategy.context import StrategyContext
from modules.trading.strategy.example_ma_cross import MovingAverageCrossStrategy
from tyche.types import Endpoint, Interface, InterfacePattern


def _noop_init(self, engine_endpoint, **kwargs):
    """No-op replacement for StrategyModule.__init__ to avoid ZMQ."""
    self._module_id = kwargs.get("module_id", "test-module")
    self._handlers: Dict[str, Any] = {}
    self._interfaces: List[Interface] = []
    self._running = False
    self._stop_event = MagicMock()
    self._instruments: List[str] = []


class TestStrategyContext:
    """Tests for StrategyContext order and market data methods."""

    def _ctx(self):
        return StrategyContext(strategy_id="s1", send_event_fn=MagicMock())

    def test_submit_order_creates_order_with_correct_fields(self):
        send_event_fn = MagicMock()
        ctx = StrategyContext(strategy_id="test-strat", send_event_fn=send_event_fn)
        order = ctx.submit_order(
            instrument_id="BTCUSDT.simulated.crypto",
            side=Side.BUY,
            quantity=Decimal("1.5"),
            order_type=OrderType.LIMIT,
            price=Decimal("50000.00"),
            tag="entry",
        )
        assert isinstance(order, Order)
        assert order.instrument_id == "BTCUSDT.simulated.crypto"
        assert order.side == Side.BUY
        assert order.quantity == Decimal("1.5")
        assert order.order_type == OrderType.LIMIT
        assert order.price == Decimal("50000.00")
        assert order.strategy_id == "test-strat"
        assert order.tag == "entry"
        send_event_fn.assert_called_once()
        event_name, payload = send_event_fn.call_args[0]
        assert event_name == events.ORDER_SUBMIT
        assert payload["instrument_id"] == "BTCUSDT.simulated.crypto"
        assert payload["side"] == "BUY"

    def test_submit_order_default_order_type_is_market(self):
        ctx = self._ctx()
        order = ctx.submit_order(
            instrument_id="ETHUSDT.simulated.crypto", side=Side.SELL, quantity=Decimal("0.5")
        )
        assert order.order_type == OrderType.MARKET
        assert order.price is None

    def test_cancel_order_calls_send_event(self):
        ctx = self._ctx()
        ctx.cancel_order(order_id="ord-123", instrument_id="BTCUSDT.simulated.crypto")
        event_name, payload = ctx._send_event.call_args[0]
        assert event_name == events.ORDER_CANCEL
        assert payload["order_id"] == "ord-123"
        assert payload["instrument_id"] == "BTCUSDT.simulated.crypto"

    def test_get_position_returns_flat_for_unknown_instrument(self):
        pos = self._ctx().get_position("UNKNOWN")
        assert isinstance(pos, Position)
        assert pos.instrument_id == "UNKNOWN"
        assert pos.side == PositionSide.FLAT
        assert pos.quantity == Decimal("0")

    def test_get_position_returns_cached_position(self):
        ctx = self._ctx()
        ctx._update_position(Position(instrument_id="BTCUSDT.simulated.crypto", side=PositionSide.LONG, quantity=Decimal("2.0")))
        result = ctx.get_position("BTCUSDT.simulated.crypto")
        assert result.side == PositionSide.LONG
        assert result.quantity == Decimal("2.0")

    def test_get_quote_returns_cached_quote(self):
        ctx = self._ctx()
        ctx._update_quote(Quote(instrument_id="BTCUSDT.simulated.crypto", bid=Decimal("64000.00"), ask=Decimal("64100.00"), bid_size=Decimal("1.0"), ask_size=Decimal("0.5"), timestamp=1234567890.0))
        result = ctx.get_quote("BTCUSDT.simulated.crypto")
        assert result is not None
        assert result.bid == Decimal("64000.00")
        assert result.ask == Decimal("64100.00")

    def test_get_quote_returns_none_for_unknown(self):
        assert self._ctx().get_quote("UNKNOWN") is None

    def test_get_bar_returns_cached_bar(self):
        ctx = self._ctx()
        ctx._update_bar(Bar(instrument_id="BTCUSDT.simulated.crypto", timeframe="1m", open=Decimal("64000.00"), high=Decimal("64500.00"), low=Decimal("63800.00"), close=Decimal("64200.00"), volume=Decimal("100.0"), timestamp=1234567890.0))
        result = ctx.get_bar("BTCUSDT.simulated.crypto")
        assert result is not None
        assert result.close == Decimal("64200.00")
        assert result.timeframe == "1m"

    def test_get_bar_returns_none_for_unknown(self):
        assert self._ctx().get_bar("UNKNOWN") is None


class DummyStrategy(StrategyModule):
    """Minimal concrete strategy for testing dispatchers."""

    def __init__(self, engine_endpoint: Endpoint, instruments: List[str]):
        with patch.object(StrategyModule, "__init__", _noop_init):
            super().__init__(engine_endpoint=engine_endpoint, instruments=instruments)
        self._module_id = "dummy-strat"
        self.ctx = StrategyContext(strategy_id=self._module_id, send_event_fn=MagicMock())
        self.on_quote_calls: List[Quote] = []
        self.on_position_calls: List[Position] = []

    def add_interface(self, name, handler, pattern=InterfacePattern.ON, durability=1):
        self._handlers[name] = handler
        self._interfaces.append(Interface(name=name, pattern=pattern, event_type=name, durability=durability))

    def on_quote(self, quote: Quote) -> None:
        self.on_quote_calls.append(quote)

    def on_position_update(self, position: Position) -> None:
        self.on_position_calls.append(position)


class TestStrategyModule:
    """Tests for StrategyModule dispatchers and subscription."""

    def _strat(self):
        return DummyStrategy(engine_endpoint=Endpoint(host="127.0.0.1", port=5555), instruments=["BTCUSDT.simulated.crypto"])

    def test_dispatch_quote_parses_and_calls_on_quote(self):
        strat = self._strat()
        strat._dispatch_quote({"instrument_id": "BTCUSDT.simulated.crypto", "bid": "64000.00", "ask": "64100.00", "bid_size": "1.0", "ask_size": "0.5", "timestamp": 1234567890.0})
        assert len(strat.on_quote_calls) == 1
        quote = strat.on_quote_calls[0]
        assert quote.instrument_id == "BTCUSDT.simulated.crypto"
        assert quote.bid == Decimal("64000.00")
        cached = strat.ctx.get_quote("BTCUSDT.simulated.crypto")
        assert cached is not None
        assert cached.mid == Decimal("64050.00")

    def test_dispatch_position_update_parses_and_calls_callback(self):
        strat = self._strat()
        strat._dispatch_position_update({"instrument_id": "BTCUSDT.simulated.crypto", "side": "LONG", "quantity": "2.5", "avg_entry_price": "63000.00", "realized_pnl": "0", "unrealized_pnl": "100.00", "commission": "5.00", "last_price": "64000.00"})
        assert len(strat.on_position_calls) == 1
        pos = strat.on_position_calls[0]
        assert pos.side == PositionSide.LONG
        assert pos.quantity == Decimal("2.5")
        cached = strat.ctx.get_position("BTCUSDT.simulated.crypto")
        assert cached.side == PositionSide.LONG
        assert cached.quantity == Decimal("2.5")

    def test_subscribe_instrument_adds_instrument_and_interfaces(self):
        strat = self._strat()
        strat.subscribe_instrument("ETHUSDT.simulated.crypto")
        assert "ETHUSDT.simulated.crypto" in strat._instruments
        assert any("ETHUSDT.simulated.crypto" in name for name in strat._handlers.keys())


class TestMovingAverageCrossStrategy:
    """Tests for EMA crossover signal generation."""

    @pytest.fixture
    def strategy(self):
        with patch.object(StrategyModule, "__init__", _noop_init):
            strat = MovingAverageCrossStrategy(
                engine_endpoint=Endpoint(host="127.0.0.1", port=5555),
                instruments=["BTCUSDT.simulated.crypto"],
                fast_period=3,
                slow_period=5,
                order_quantity=Decimal("0.1"),
            )
        strat._module_id = "ma-cross-test"
        strat.ctx = StrategyContext(strategy_id="ma-cross-test", send_event_fn=MagicMock())
        return strat

    def _q(self, bid: str, ask: str) -> Quote:
        return Quote(instrument_id="BTCUSDT.simulated.crypto", bid=Decimal(bid), ask=Decimal(ask), bid_size=Decimal("1.0"), ask_size=Decimal("1.0"), timestamp=1234567890.0)

    def test_on_quote_ema_calculation(self, strategy):
        for p in ["100", "101", "102", "103", "104"]:
            strategy.on_quote(self._q(p, p))
        assert strategy._fast_ema["BTCUSDT.simulated.crypto"] is not None
        assert strategy._slow_ema["BTCUSDT.simulated.crypto"] is not None

    def test_golden_cross_generates_buy_signal(self, strategy):
        for p in ["110", "109", "108", "107", "106"]:
            strategy.on_quote(self._q(p, p))
        for p in ["120", "125", "130"]:
            strategy.on_quote(self._q(p, p))
        submits = [c for c in strategy.ctx._send_event.call_args_list if c[0][0] == events.ORDER_SUBMIT]
        assert len(submits) >= 1
        assert submits[-1][0][1]["side"] == "BUY"

    def test_death_cross_generates_sell_signal(self, strategy):
        for p in ["100", "101", "102", "103", "104"]:
            strategy.on_quote(self._q(p, p))
        for p in ["90", "85", "80"]:
            strategy.on_quote(self._q(p, p))
        submits = [c for c in strategy.ctx._send_event.call_args_list if c[0][0] == events.ORDER_SUBMIT]
        assert len(submits) >= 1
        assert any(c[0][1]["side"] == "SELL" for c in submits)

    def test_no_signal_without_crossover(self, strategy):
        for p in ["100", "100", "100", "100", "100"]:
            strategy.on_quote(self._q(p, p))
        submits = [c for c in strategy.ctx._send_event.call_args_list if c[0][0] == events.ORDER_SUBMIT]
        assert len(submits) == 0

    def test_on_order_update_logs(self, strategy, caplog):
        import logging
        with caplog.at_level(logging.INFO):
            strategy.on_order_update(OrderUpdate(order_id="ord-abc123", instrument_id="BTCUSDT.simulated.crypto", status=OrderStatus.FILLED, filled_quantity=Decimal("0.1"), avg_fill_price=Decimal("100.00")))
        assert "ord-abc123" in caplog.text or "FILLED" in caplog.text

    def test_on_position_update_logs(self, strategy, caplog):
        import logging
        with caplog.at_level(logging.INFO):
            strategy.on_position_update(Position(instrument_id="BTCUSDT.simulated.crypto", side=PositionSide.LONG, quantity=Decimal("1.0")))
        assert "BTCUSDT.simulated.crypto" in caplog.text

    def test_get_stats_returns_dict(self, strategy):
        stats = strategy.get_stats()
        assert stats["strategy_id"] == "ma-cross-test"
        assert stats["fast_period"] == 3
        assert stats["slow_period"] == 5
        assert "tick_counts" in stats
        assert "current_emas" in stats
