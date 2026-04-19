"""Abstract base class for exchange/venue gateway modules.

A Gateway is a TycheModule that bridges external exchange APIs with the internal
event system. Each venue should have its own Gateway process for fault isolation.
"""

import logging
import time
from abc import abstractmethod
from typing import Any, Dict, List, Optional

from tyche.module import TycheModule
from tyche.trading import events
from tyche.trading.models.enums import OrderStatus
from tyche.trading.models.order import Fill, Order, OrderUpdate
from tyche.trading.models.tick import Bar, Quote, Trade
from tyche.types import DurabilityLevel, Endpoint, InterfacePattern

logger = logging.getLogger(__name__)


class GatewayModule(TycheModule):
    """Abstract base for exchange gateway modules.

    Subclasses implement venue-specific connectivity while this base
    provides standardized event publishing and order handling.

    Responsibilities:
    - Connect to exchange API (REST + WebSocket)
    - Normalize market data into Quote/Trade/Bar and publish via events
    - Receive order.execute / order.cancel and route to exchange
    - Publish fill events back to the system
    """

    def __init__(
        self,
        engine_endpoint: Endpoint,
        venue_name: str,
        module_id: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(engine_endpoint, module_id=module_id, **kwargs)
        self.venue_name = venue_name
        self._subscribed_instruments: List[str] = []
        self._connected = False

        # Register standard order handling interfaces
        self.add_interface(
            name=f"ack_order_execute_{venue_name}",
            handler=self._handle_order_execute,
            pattern=InterfacePattern.ACK,
            durability=DurabilityLevel.ASYNC_FLUSH,
        )
        self.add_interface(
            name=f"ack_order_cancel_{venue_name}",
            handler=self._handle_order_cancel,
            pattern=InterfacePattern.ACK,
            durability=DurabilityLevel.ASYNC_FLUSH,
        )

    # --- Abstract methods (venue-specific implementation) ---

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the exchange."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the exchange."""
        ...

    @abstractmethod
    def subscribe_market_data(self, instrument_ids: List[str]) -> None:
        """Subscribe to market data for given instruments.

        Args:
            instrument_ids: List of instrument ID strings to subscribe to.
        """
        ...

    @abstractmethod
    def submit_order(self, order: Order) -> OrderUpdate:
        """Submit an order to the exchange.

        Args:
            order: The order to submit.

        Returns:
            OrderUpdate with submission result (SUBMITTED or REJECTED).
        """
        ...

    @abstractmethod
    def cancel_order(self, order_id: str, instrument_id: str) -> OrderUpdate:
        """Cancel an order on the exchange.

        Args:
            order_id: The order ID to cancel.
            instrument_id: The instrument the order belongs to.

        Returns:
            OrderUpdate with cancellation result.
        """
        ...

    @abstractmethod
    def query_account(self) -> Dict[str, Any]:
        """Query account balance and position state from exchange.

        Returns:
            Raw account data dictionary (venue-specific format).
        """
        ...

    # --- Event publishing helpers ---

    def publish_quote(self, quote: Quote) -> None:
        """Publish a quote event to the engine."""
        topic = events.quote_event(quote.instrument_id)
        self.send_event(topic, quote.to_dict())

    def publish_trade(self, trade: Trade) -> None:
        """Publish a trade event to the engine."""
        topic = events.trade_event(trade.instrument_id)
        self.send_event(topic, trade.to_dict())

    def publish_bar(self, bar: Bar) -> None:
        """Publish a bar event to the engine."""
        topic = events.bar_event(bar.instrument_id, bar.timeframe)
        self.send_event(topic, bar.to_dict())

    def publish_fill(self, fill: Fill) -> None:
        """Publish a fill event to the engine."""
        topic = events.fill_event(fill.instrument_id)
        self.send_event(topic, fill.to_dict())

    def publish_order_update(self, update: OrderUpdate) -> None:
        """Publish an order update event."""
        self.send_event(events.ORDER_UPDATE, update.to_dict())

    # --- Internal order handling ---

    def _handle_order_execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming order execution request (ack_ pattern).

        Called by engine when OMS sends order.execute targeted at this gateway.
        """
        order = Order.from_dict(payload)
        logger.info(
            "Gateway %s executing order: %s %s %s @ %s",
            self.venue_name,
            order.side.name,
            order.quantity,
            order.instrument_id,
            order.price,
        )
        try:
            result = self.submit_order(order)
            return result.to_dict()
        except Exception as e:
            logger.error("Order execution failed: %s", e)
            return OrderUpdate(
                order_id=order.order_id,
                instrument_id=order.instrument_id,
                status=OrderStatus.REJECTED,
                timestamp=time.time(),
                reason=str(e),
            ).to_dict()

    def _handle_order_cancel(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming order cancellation request (ack_ pattern)."""
        order_id = payload["order_id"]
        instrument_id = payload["instrument_id"]
        logger.info(
            "Gateway %s cancelling order: %s",
            self.venue_name,
            order_id,
        )
        try:
            result = self.cancel_order(order_id, instrument_id)
            return result.to_dict()
        except Exception as e:
            logger.error("Order cancel failed: %s", e)
            return OrderUpdate(
                order_id=order_id,
                instrument_id=instrument_id,
                status=OrderStatus.REJECTED,
                timestamp=time.time(),
                reason=str(e),
            ).to_dict()
