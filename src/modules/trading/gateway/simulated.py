"""Simulated exchange gateway for testing and development.

Generates random market data (quotes/trades) and simulates order execution
with configurable latency and fill probability.
"""

import logging
import random
import threading
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

from modules.trading.gateway.base import GatewayModule
from modules.trading.models.enums import OrderStatus, Side
from modules.trading.models.order import Fill, Order, OrderUpdate
from modules.trading.models.tick import Quote, Trade
from tyche.types import Endpoint

logger = logging.getLogger(__name__)


class SimulatedGateway(GatewayModule):
    """A mock exchange gateway that generates synthetic market data.

    Useful for:
    - Testing the full trading pipeline without a real exchange
    - Development and debugging of strategies
    - Integration testing of OMS/Risk/Portfolio modules

    Configuration:
    - instruments: List of instrument IDs to simulate
    - tick_interval: Seconds between quote updates (default 0.5)
    - base_prices: Starting prices per instrument
    - fill_latency: Simulated order fill delay in seconds
    - fill_probability: Chance of order being filled (0.0-1.0)
    """

    def __init__(
        self,
        engine_endpoint: Endpoint,
        instruments: Optional[List[str]] = None,
        tick_interval: float = 0.5,
        base_prices: Optional[Dict[str, Decimal]] = None,
        fill_latency: float = 0.1,
        fill_probability: float = 0.95,
        module_id: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(
            engine_endpoint=engine_endpoint,
            venue_name="simulated",
            module_id=module_id,
            **kwargs,
        )
        self._instruments = instruments or [
            "BTCUSDT.simulated.crypto",
            "ETHUSDT.simulated.crypto",
        ]
        self._tick_interval = tick_interval
        self._base_prices: Dict[str, Decimal] = base_prices or {
            "BTCUSDT.simulated.crypto": Decimal("65000.00"),
            "ETHUSDT.simulated.crypto": Decimal("3200.00"),
        }
        self._fill_latency = fill_latency
        self._fill_probability = fill_probability

        # Current simulated prices
        self._current_prices: Dict[str, Decimal] = dict(self._base_prices)
        self._market_data_thread: Optional[threading.Thread] = None
        self._trade_counter = 0

    def connect(self) -> None:
        """Simulate exchange connection."""
        self._connected = True
        logger.info("SimulatedGateway connected (venue=%s)", self.venue_name)

    def disconnect(self) -> None:
        """Simulate exchange disconnection."""
        self._connected = False
        logger.info("SimulatedGateway disconnected")

    def subscribe_market_data(self, instrument_ids: List[str]) -> None:
        """Start generating market data for instruments."""
        for iid in instrument_ids:
            if iid not in self._instruments:
                self._instruments.append(iid)
                if iid not in self._current_prices:
                    self._current_prices[iid] = Decimal("100.00")
        logger.info("Subscribed to market data: %s", instrument_ids)

    def submit_order(self, order: Order) -> OrderUpdate:
        """Simulate order submission and fill."""
        logger.info(
            "SimGW submit: %s %s %s @ %s",
            order.side.name, order.quantity, order.instrument_id, order.price,
        )

        # Simulate network/processing latency
        time.sleep(self._fill_latency)

        # Simulate fill probability
        if random.random() < self._fill_probability:
            # Simulate fill at current market price (with slippage)
            base_price = self._current_prices.get(
                order.instrument_id, order.price or Decimal("100")
            )
            slippage = Decimal(str(random.uniform(-0.001, 0.001)))
            fill_price = base_price * (1 + slippage)
            fill_price = fill_price.quantize(Decimal("0.01"))

            # Create and publish fill
            fill = Fill(
                order_id=order.order_id,
                instrument_id=order.instrument_id,
                side=order.side,
                price=fill_price,
                quantity=order.quantity,
                timestamp=time.time(),
                fee=fill_price * order.quantity * Decimal("0.0004"),  # 4bps fee
                is_maker=False,
            )
            self.publish_fill(fill)

            return OrderUpdate(
                order_id=order.order_id,
                instrument_id=order.instrument_id,
                status=OrderStatus.FILLED,
                filled_quantity=order.quantity,
                avg_fill_price=fill_price,
                timestamp=time.time(),
            )
        else:
            return OrderUpdate(
                order_id=order.order_id,
                instrument_id=order.instrument_id,
                status=OrderStatus.REJECTED,
                timestamp=time.time(),
                reason="Simulated rejection (random)",
            )

    def cancel_order(self, order_id: str, instrument_id: str) -> OrderUpdate:
        """Simulate order cancellation (always succeeds)."""
        return OrderUpdate(
            order_id=order_id,
            instrument_id=instrument_id,
            status=OrderStatus.CANCELLED,
            timestamp=time.time(),
        )

    def query_account(self) -> Dict[str, Any]:
        """Return simulated account balances."""
        return {
            "venue": "simulated",
            "balances": [
                {"currency": "USDT", "total": "100000.00", "available": "95000.00", "frozen": "5000.00"},
                {"currency": "BTC", "total": "1.5", "available": "1.5", "frozen": "0"},
                {"currency": "ETH", "total": "20.0", "available": "20.0", "frozen": "0"},
            ],
        }

    # --- Market data generation ---

    def start_market_data(self) -> None:
        """Start the market data generation thread."""
        self.connect()
        self._market_data_thread = threading.Thread(
            target=self._generate_market_data, daemon=True, name="sim-market-data"
        )
        self._market_data_thread.start()

    def _generate_market_data(self) -> None:
        """Generate random walk quotes and occasional trades."""
        while self._running:
            for instrument_id in self._instruments:
                price = self._current_prices.get(instrument_id, Decimal("100"))

                # Random walk: ±0.1% per tick
                change_pct = Decimal(str(random.gauss(0, 0.001)))
                new_price = price * (1 + change_pct)
                new_price = max(new_price, Decimal("0.01"))
                self._current_prices[instrument_id] = new_price

                # Generate spread (0.01% - 0.05%)
                spread_pct = Decimal(str(random.uniform(0.0001, 0.0005)))
                half_spread = new_price * spread_pct / 2

                bid = (new_price - half_spread).quantize(Decimal("0.01"))
                ask = (new_price + half_spread).quantize(Decimal("0.01"))
                bid_size = Decimal(str(round(random.uniform(0.1, 5.0), 4)))
                ask_size = Decimal(str(round(random.uniform(0.1, 5.0), 4)))

                quote = Quote(
                    instrument_id=instrument_id,
                    bid=bid,
                    ask=ask,
                    bid_size=bid_size,
                    ask_size=ask_size,
                    timestamp=time.time(),
                )
                self.publish_quote(quote)

                # Occasionally generate a trade (30% chance per tick)
                if random.random() < 0.3:
                    self._trade_counter += 1
                    trade_side = random.choice([Side.BUY, Side.SELL])
                    trade_price = bid if trade_side == Side.SELL else ask
                    trade = Trade(
                        instrument_id=instrument_id,
                        price=trade_price,
                        size=Decimal(str(round(random.uniform(0.01, 2.0), 4))),
                        side=trade_side,
                        timestamp=time.time(),
                        trade_id=f"sim-{self._trade_counter}",
                    )
                    self.publish_trade(trade)

            self._stop_event.wait(self._tick_interval)
