"""Strategy runtime context providing market state and order submission."""

import logging
import time
from decimal import Decimal
from typing import Any, Callable, Dict, Optional

from modules.trading import events
from modules.trading.models.enums import OrderType, Side, TimeInForce
from modules.trading.models.order import Order
from modules.trading.models.position import Position
from modules.trading.models.tick import Bar, Quote

logger = logging.getLogger(__name__)


class StrategyContext:
    """Provides strategies with access to market state and order operations.

    The context is the strategy's interface to the trading system. It holds:
    - Current positions across instruments
    - Latest quotes/bars per instrument
    - Order submission/cancellation methods (delegated to module's send_event)
    - Clock access (current time, which may be simulated in backtest)
    """

    def __init__(
        self,
        strategy_id: str,
        send_event_fn: Callable[[str, Dict[str, Any]], None],
    ):
        self._strategy_id = strategy_id
        self._send_event = send_event_fn

        # Market state
        self._positions: Dict[str, Position] = {}
        self._latest_quotes: Dict[str, Quote] = {}
        self._latest_bars: Dict[str, Bar] = {}

        # Clock (updated by system.clock events)
        self._current_time: float = time.time()

    @property
    def strategy_id(self) -> str:
        return self._strategy_id

    @property
    def current_time(self) -> float:
        """Current system time (wall clock or simulated)."""
        return self._current_time

    # --- Market data access ---

    def get_position(self, instrument_id: str) -> Position:
        """Get current position for an instrument (returns flat position if none)."""
        if instrument_id not in self._positions:
            self._positions[instrument_id] = Position(instrument_id=instrument_id)
        return self._positions[instrument_id]

    def get_all_positions(self) -> Dict[str, Position]:
        """Get all tracked positions."""
        return dict(self._positions)

    def get_quote(self, instrument_id: str) -> Optional[Quote]:
        """Get latest quote for an instrument."""
        return self._latest_quotes.get(instrument_id)

    def get_bar(self, instrument_id: str) -> Optional[Bar]:
        """Get latest bar for an instrument."""
        return self._latest_bars.get(instrument_id)

    # --- Order operations ---

    def submit_order(
        self,
        instrument_id: str,
        side: Side,
        quantity: Decimal,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[Decimal] = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        tag: Optional[str] = None,
    ) -> Order:
        """Submit a new order through the risk module.

        The order flows: Strategy -> Risk (ack) -> OMS -> Gateway.

        Returns:
            The Order object (status=NEW, will be updated via events).
        """
        order = Order(
            instrument_id=instrument_id,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            time_in_force=time_in_force,
            strategy_id=self._strategy_id,
            created_at=self._current_time,
            tag=tag,
        )
        self._send_event(events.ORDER_SUBMIT, order.to_dict())
        logger.info(
            "Strategy %s submitted order: %s %s %s @ %s",
            self._strategy_id,
            side.name,
            quantity,
            instrument_id,
            price,
        )
        return order

    def cancel_order(self, order_id: str, instrument_id: str) -> None:
        """Request cancellation of an active order.

        Args:
            order_id: The client order ID to cancel.
            instrument_id: The instrument the order belongs to.
        """
        self._send_event(
            events.ORDER_CANCEL,
            {"order_id": order_id, "instrument_id": instrument_id},
        )
        logger.info("Strategy %s cancelling order: %s", self._strategy_id, order_id)

    # --- Internal state updates (called by StrategyModule) ---

    def _update_quote(self, quote: Quote) -> None:
        """Update latest quote cache."""
        self._latest_quotes[quote.instrument_id] = quote

    def _update_bar(self, bar: Bar) -> None:
        """Update latest bar cache."""
        self._latest_bars[bar.instrument_id] = bar

    def _update_position(self, position: Position) -> None:
        """Update position from portfolio event."""
        self._positions[position.instrument_id] = position

    def _update_clock(self, timestamp: float) -> None:
        """Update current time from clock event."""
        self._current_time = timestamp
