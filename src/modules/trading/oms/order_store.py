"""In-memory order state machine and store."""

import logging
import threading
from typing import Dict, List, Optional

from modules.trading.models.enums import OrderStatus
from modules.trading.models.order import Fill, Order

logger = logging.getLogger(__name__)

# Valid state transitions
_VALID_TRANSITIONS: Dict[OrderStatus, List[OrderStatus]] = {
    OrderStatus.NEW: [OrderStatus.PENDING_SUBMIT, OrderStatus.REJECTED],
    OrderStatus.PENDING_SUBMIT: [OrderStatus.SUBMITTED, OrderStatus.REJECTED],
    OrderStatus.SUBMITTED: [
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.PENDING_CANCEL,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
    ],
    OrderStatus.PARTIALLY_FILLED: [
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.PENDING_CANCEL,
        OrderStatus.CANCELLED,
    ],
    OrderStatus.PENDING_CANCEL: [
        OrderStatus.CANCELLED,
        OrderStatus.FILLED,
        OrderStatus.PARTIALLY_FILLED,
    ],
    OrderStatus.FILLED: [],
    OrderStatus.CANCELLED: [],
    OrderStatus.REJECTED: [],
    OrderStatus.EXPIRED: [],
}


class OrderStore:
    """Thread-safe in-memory order store with state machine enforcement.

    Tracks all orders and validates state transitions. Provides
    query methods for active/completed orders.
    """

    def __init__(self) -> None:
        self._orders: Dict[str, Order] = {}
        self._lock = threading.Lock()

    def add_order(self, order: Order) -> None:
        """Add a new order to the store."""
        with self._lock:
            self._orders[order.order_id] = order

    def get_order(self, order_id: str) -> Optional[Order]:
        """Get an order by ID."""
        with self._lock:
            return self._orders.get(order_id)

    def update_status(
        self,
        order_id: str,
        new_status: OrderStatus,
        venue_order_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Optional[Order]:
        """Update order status with state machine validation.

        Returns:
            Updated order if transition is valid, None otherwise.
        """
        with self._lock:
            order = self._orders.get(order_id)
            if order is None:
                logger.warning("Order not found: %s", order_id)
                return None

            valid_next = _VALID_TRANSITIONS.get(order.status, [])
            if new_status not in valid_next:
                logger.warning(
                    "Invalid state transition for order %s: %s -> %s",
                    order_id,
                    order.status.name,
                    new_status.name,
                )
                return None

            order.status = new_status
            if venue_order_id:
                order.venue_order_id = venue_order_id
            return order

    def apply_fill(self, fill: Fill) -> Optional[Order]:
        """Apply a fill to an order, updating quantities and status.

        Returns:
            Updated order, or None if order not found.
        """
        with self._lock:
            order = self._orders.get(fill.order_id)
            if order is None:
                logger.warning("Fill for unknown order: %s", fill.order_id)
                return None

            order.filled_quantity += fill.quantity

            # Calculate average fill price
            if order.avg_fill_price is None:
                order.avg_fill_price = fill.price
            else:
                prev_total = order.avg_fill_price * (order.filled_quantity - fill.quantity)
                order.avg_fill_price = (prev_total + fill.price * fill.quantity) / order.filled_quantity

            # Update status based on fill
            if order.filled_quantity >= order.quantity:
                order.status = OrderStatus.FILLED
            else:
                order.status = OrderStatus.PARTIALLY_FILLED

            return order

    def get_active_orders(self, instrument_id: Optional[str] = None) -> List[Order]:
        """Get all active (non-terminal) orders, optionally filtered by instrument."""
        with self._lock:
            orders = [o for o in self._orders.values() if o.is_active]
            if instrument_id:
                orders = [o for o in orders if o.instrument_id == instrument_id]
            return orders

    def get_orders_by_strategy(self, strategy_id: str) -> List[Order]:
        """Get all orders for a strategy."""
        with self._lock:
            return [o for o in self._orders.values() if o.strategy_id == strategy_id]

    def get_all_orders(self) -> List[Order]:
        """Get all orders."""
        with self._lock:
            return list(self._orders.values())

    @property
    def active_count(self) -> int:
        """Number of active orders."""
        with self._lock:
            return sum(1 for o in self._orders.values() if o.is_active)

    @property
    def total_count(self) -> int:
        """Total number of tracked orders."""
        with self._lock:
            return len(self._orders)
