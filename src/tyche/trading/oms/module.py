"""Order Management System module.

The OMS sits between the Risk module and Gateway modules. It:
- Receives approved orders from Risk
- Maintains order state (via OrderStore)
- Routes execution requests to the correct Gateway based on venue
- Processes fills and broadcasts order updates
"""

import logging
import time
from typing import Any, Dict, Optional

from tyche.module import TycheModule
from tyche.trading import events
from tyche.trading.models.enums import OrderStatus
from tyche.trading.models.order import Fill, Order, OrderUpdate
from tyche.trading.oms.order_store import OrderStore
from tyche.types import DurabilityLevel, Endpoint, InterfacePattern

logger = logging.getLogger(__name__)


class OMSModule(TycheModule):
    """Order Management System - manages order lifecycle and routing.

    Event flow:
        order.approved (from Risk) -> OMS stores order -> routes to Gateway
        fill.{instrument} (from Gateway) -> OMS updates order -> publishes order.update
    """

    def __init__(
        self,
        engine_endpoint: Endpoint,
        module_id: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(engine_endpoint, module_id=module_id, **kwargs)
        self.order_store = OrderStore()

        # Register event handlers
        self.add_interface(
            name=f"on_{events.ORDER_APPROVED}",
            handler=self._handle_order_approved,
            pattern=InterfacePattern.ON,
            durability=DurabilityLevel.ASYNC_FLUSH,
        )

        # Fill handler - subscribes to all fills
        self.add_interface(
            name=f"on_{events.FILL}",
            handler=self._handle_fill,
            pattern=InterfacePattern.ON,
            durability=DurabilityLevel.ASYNC_FLUSH,
        )

        # Cancel requests from strategies
        self.add_interface(
            name=f"on_{events.ORDER_CANCEL}",
            handler=self._handle_cancel_request,
            pattern=InterfacePattern.ON,
        )

    def _handle_order_approved(self, payload: Dict[str, Any]) -> None:
        """Process an approved order from the risk module.

        Stores the order and routes execution to the appropriate gateway.
        """
        order = Order.from_dict(payload)
        order.status = OrderStatus.PENDING_SUBMIT
        order.updated_at = time.time()
        self.order_store.add_order(order)

        logger.info(
            "OMS received approved order: %s %s %s %s",
            order.order_id,
            order.side.name,
            order.quantity,
            order.instrument_id,
        )

        # Route to gateway based on venue in instrument_id
        venue = self._extract_venue(order.instrument_id)
        execute_topic = f"ack_order_execute_{venue}"

        # Send execution request to gateway
        self.send_event(execute_topic, order.to_dict())

        # Publish order update
        self._publish_order_update(order)

    def _handle_fill(self, payload: Dict[str, Any]) -> None:
        """Process a fill from a gateway.

        Updates order state and publishes order update.
        """
        fill = Fill.from_dict(payload)
        order = self.order_store.apply_fill(fill)

        if order:
            order.updated_at = time.time()
            logger.info(
                "OMS fill: order=%s, filled=%s/%s, status=%s",
                order.order_id,
                order.filled_quantity,
                order.quantity,
                order.status.name,
            )
            self._publish_order_update(order)
        else:
            logger.warning("Fill for unknown order: %s", fill.order_id)

    def _handle_cancel_request(self, payload: Dict[str, Any]) -> None:
        """Handle cancel request from strategy.

        Routes to appropriate gateway for cancellation.
        """
        order_id = payload["order_id"]
        instrument_id = payload["instrument_id"]

        order = self.order_store.get_order(order_id)
        if order is None:
            logger.warning("Cancel request for unknown order: %s", order_id)
            return

        if not order.is_active:
            logger.warning("Cancel request for inactive order: %s (status=%s)", order_id, order.status.name)
            return

        # Update to pending cancel
        self.order_store.update_status(order_id, OrderStatus.PENDING_CANCEL)
        order.updated_at = time.time()

        # Route cancel to gateway
        venue = self._extract_venue(instrument_id)
        cancel_topic = f"ack_order_cancel_{venue}"
        self.send_event(cancel_topic, payload)

        self._publish_order_update(order)

    def _publish_order_update(self, order: Order) -> None:
        """Publish an order update event."""
        update = OrderUpdate(
            order_id=order.order_id,
            instrument_id=order.instrument_id,
            status=order.status,
            filled_quantity=order.filled_quantity,
            avg_fill_price=order.avg_fill_price,
            timestamp=time.time(),
        )
        self.send_event(events.ORDER_UPDATE, update.to_dict())

    @staticmethod
    def _extract_venue(instrument_id: str) -> str:
        """Extract venue name from instrument_id format 'SYMBOL.venue.asset_class'."""
        parts = instrument_id.split(".")
        if len(parts) >= 2:
            return parts[1]
        return "unknown"
