"""Example strategy: Simple Moving Average Crossover.

Demonstrates how to implement a trading strategy using the StrategyModule base.
Uses a fast/slow EMA crossover to generate buy/sell signals.
"""

import logging
from collections import deque
from decimal import Decimal
from typing import Any, Deque, Dict, List, Optional

from tyche.trading.models.enums import OrderType, Side
from tyche.trading.models.order import OrderUpdate
from tyche.trading.models.position import Position
from tyche.trading.models.tick import Quote
from tyche.trading.strategy.base import StrategyModule
from tyche.types import Endpoint

logger = logging.getLogger(__name__)


class MovingAverageCrossStrategy(StrategyModule):
    """EMA crossover strategy for demonstration.

    Logic:
    - Maintains fast EMA and slow EMA of mid prices
    - BUY when fast EMA crosses above slow EMA (golden cross)
    - SELL when fast EMA crosses below slow EMA (death cross)
    - Only one position per instrument at a time

    This is a simplified example - real strategies would include:
    - More sophisticated entry/exit logic
    - Position sizing based on volatility
    - Stop-loss and take-profit orders
    - Portfolio-level risk constraints
    """

    def __init__(
        self,
        engine_endpoint: Endpoint,
        instruments: List[str],
        fast_period: int = 5,
        slow_period: int = 20,
        order_quantity: Decimal = Decimal("0.1"),
        module_id: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(
            engine_endpoint=engine_endpoint,
            instruments=instruments,
            module_id=module_id,
            **kwargs,
        )
        self._fast_period = fast_period
        self._slow_period = slow_period
        self._order_quantity = order_quantity

        # Per-instrument state
        self._price_history: Dict[str, Deque[Decimal]] = {
            iid: deque(maxlen=slow_period + 1) for iid in instruments
        }
        self._fast_ema: Dict[str, Optional[Decimal]] = {iid: None for iid in instruments}
        self._slow_ema: Dict[str, Optional[Decimal]] = {iid: None for iid in instruments}
        self._prev_signal: Dict[str, int] = {iid: 0 for iid in instruments}  # -1, 0, +1
        self._tick_count: Dict[str, int] = {iid: 0 for iid in instruments}

    def on_quote(self, quote: Quote) -> None:
        """Process incoming quote and check for crossover signals."""
        instrument_id = quote.instrument_id
        mid = quote.mid

        # Initialize tracking for new instruments
        if instrument_id not in self._price_history:
            self._price_history[instrument_id] = deque(maxlen=self._slow_period + 1)
            self._fast_ema[instrument_id] = None
            self._slow_ema[instrument_id] = None
            self._prev_signal[instrument_id] = 0
            self._tick_count[instrument_id] = 0

        self._price_history[instrument_id].append(mid)
        self._tick_count[instrument_id] = self._tick_count.get(instrument_id, 0) + 1

        # Need enough data for slow EMA
        if len(self._price_history[instrument_id]) < self._slow_period:
            return

        # Calculate EMAs
        fast_ema = self._calculate_ema(instrument_id, self._fast_period)
        slow_ema = self._calculate_ema(instrument_id, self._slow_period)
        self._fast_ema[instrument_id] = fast_ema
        self._slow_ema[instrument_id] = slow_ema

        # Determine signal
        if fast_ema > slow_ema:
            signal = 1  # Bullish
        elif fast_ema < slow_ema:
            signal = -1  # Bearish
        else:
            signal = 0

        # Check for crossover (signal change)
        prev = self._prev_signal[instrument_id]
        self._prev_signal[instrument_id] = signal

        if signal == prev or prev == 0:
            return  # No crossover

        # Execute trade on crossover
        position = self.ctx.get_position(instrument_id)

        if signal == 1 and prev == -1:
            # Golden cross - go long
            logger.info(
                "[%s] GOLDEN CROSS on %s (fast=%.2f, slow=%.2f) -> BUY",
                self.module_id, instrument_id, fast_ema, slow_ema,
            )
            self.ctx.submit_order(
                instrument_id=instrument_id,
                side=Side.BUY,
                quantity=self._order_quantity,
                order_type=OrderType.MARKET,
                tag="ema_cross_buy",
            )

        elif signal == -1 and prev == 1:
            # Death cross - go short / close long
            logger.info(
                "[%s] DEATH CROSS on %s (fast=%.2f, slow=%.2f) -> SELL",
                self.module_id, instrument_id, fast_ema, slow_ema,
            )
            self.ctx.submit_order(
                instrument_id=instrument_id,
                side=Side.SELL,
                quantity=self._order_quantity,
                order_type=OrderType.MARKET,
                tag="ema_cross_sell",
            )

    def on_order_update(self, update: OrderUpdate) -> None:
        """Log order status changes."""
        logger.info(
            "[%s] Order %s: %s (filled=%s @ %s)",
            self.module_id,
            update.order_id[:8],
            update.status.name,
            update.filled_quantity,
            update.avg_fill_price,
        )

    def on_position_update(self, position: Position) -> None:
        """Log position changes."""
        logger.info(
            "[%s] Position %s: %s qty=%s pnl=%s",
            self.module_id,
            position.instrument_id,
            position.side.name,
            position.quantity,
            position.net_pnl,
        )

    def _calculate_ema(self, instrument_id: str, period: int) -> Decimal:
        """Calculate EMA from price history."""
        prices = list(self._price_history[instrument_id])
        if len(prices) < period:
            return prices[-1]

        multiplier = Decimal("2") / (Decimal(str(period)) + Decimal("1"))
        ema = prices[0]
        for price in prices[1:]:
            ema = (price - ema) * multiplier + ema
        return ema

    def get_stats(self) -> Dict[str, Any]:
        """Return strategy statistics."""
        return {
            "strategy_id": self.module_id,
            "instruments": self._instruments,
            "fast_period": self._fast_period,
            "slow_period": self._slow_period,
            "tick_counts": dict(self._tick_count),
            "current_emas": {
                iid: {
                    "fast": str(self._fast_ema.get(iid)),
                    "slow": str(self._slow_ema.get(iid)),
                }
                for iid in self._instruments
            },
        }
