"""Abstract base class for trading strategy modules.

Strategies subscribe to market data events, process signals, and submit
orders through the StrategyContext.
"""

import logging
from abc import abstractmethod
from typing import Any, Dict, List, Optional

from modules.trading import events
from modules.trading.models.order import Fill, OrderUpdate
from modules.trading.models.position import Position
from modules.trading.models.tick import Bar, Quote, Trade
from modules.trading.strategy.context import StrategyContext
from tyche.module import TycheModule
from tyche.types import Endpoint

logger = logging.getLogger(__name__)


class StrategyModule(TycheModule):
    """Abstract base for trading strategy modules.

    Subclasses implement trading logic by overriding callback methods:
    - on_quote(): React to quote updates
    - on_trade(): React to trade ticks
    - on_bar(): React to bar/candle closes
    - on_fill(): React to order fills
    - on_order_update(): React to order status changes
    - on_position_update(): React to position changes

    The StrategyContext provides methods for submitting orders and
    accessing current market state.
    """

    def __init__(
        self,
        engine_endpoint: Endpoint,
        instruments: Optional[List[str]] = None,
        module_id: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(engine_endpoint, module_id=module_id, **kwargs)
        self._instruments = instruments or []
        self._bar_subscriptions: set[str] = set()
        self.ctx: StrategyContext = StrategyContext(
            strategy_id=self.module_id,
            send_event_fn=self.send_event,
        )

    def subscribe_instrument(self, instrument_id: str) -> None:
        """Subscribe to market data for an additional instrument at runtime."""
        if instrument_id not in self._instruments:
            self._instruments.append(instrument_id)

    def subscribe_bars(self, instrument_id: str, timeframe: str) -> None:
        """Subscribe to bar events for a specific instrument and timeframe."""
        self._bar_subscriptions.add(f"{instrument_id}.{timeframe}")

    # --- Abstract callbacks (implement in subclass) ---

    @abstractmethod
    def on_quote(self, quote: Quote) -> None:
        """Called on each quote update for subscribed instruments."""
        ...

    def on_trade(self, trade: Trade) -> None:
        """Called on each trade tick (optional override)."""
        pass

    def on_bar(self, bar: Bar) -> None:
        """Called on each bar close (optional override)."""
        pass

    def on_fill(self, fill: Fill) -> None:
        """Called when an order is filled (optional override)."""
        pass

    def on_order_update(self, update: OrderUpdate) -> None:
        """Called on order status change (optional override)."""
        pass

    def on_position_update(self, position: Position) -> None:
        """Called when position changes (optional override)."""
        pass

    # --- v2 interface handlers (auto-discovered) ---

    def on_streaming_quote(self, payload: Dict[str, Any]) -> None:
        """Handle streaming quote events."""
        instrument_id = payload.get("instrument_id", "")
        if instrument_id not in self._instruments:
            return
        quote = Quote.from_dict(payload)
        self.ctx._update_quote(quote)
        self.on_quote(quote)

    def on_streaming_trade(self, payload: Dict[str, Any]) -> None:
        """Handle streaming trade events."""
        instrument_id = payload.get("instrument_id", "")
        if instrument_id not in self._instruments:
            return
        trade = Trade.from_dict(payload)
        self.on_trade(trade)

    def on_streaming_bar(self, payload: Dict[str, Any]) -> None:
        """Handle streaming bar events."""
        instrument_id = payload.get("instrument_id", "")
        timeframe = payload.get("timeframe", "")
        key = f"{instrument_id}.{timeframe}"
        if key not in self._bar_subscriptions:
            return
        bar = Bar.from_dict(payload)
        self.ctx._update_bar(bar)
        self.on_bar(bar)

    def on_broadcasted_order_update(self, payload: Dict[str, Any]) -> None:
        """Handle order update broadcasts."""
        update = OrderUpdate.from_dict(payload)
        # Only forward updates for orders belonging to this strategy
        if payload.get("strategy_id") == self.module_id or not payload.get("strategy_id"):
            self.on_order_update(update)

    def on_broadcasted_position_update(self, payload: Dict[str, Any]) -> None:
        """Handle position update broadcasts."""
        position = Position.from_dict(payload)
        self.ctx._update_position(position)
        self.on_position_update(position)

    def on_broadcasted_system_clock(self, payload: Dict[str, Any]) -> None:
        """Handle system clock broadcasts."""
        timestamp = payload.get("timestamp", 0.0)
        self.ctx._update_clock(timestamp)
