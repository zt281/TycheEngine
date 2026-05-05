"""Portfolio module - tracks positions and P&L across all instruments.

Listens to fill events to update positions and broadcasts position/account
updates to the rest of the system.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, Optional

from modules.trading import events
from modules.trading.models.order import Fill
from modules.trading.models.position import Position
from tyche.module import TycheModule
from tyche.types import Endpoint

logger = logging.getLogger(__name__)


class PortfolioModule(TycheModule):
    """Portfolio tracking module.

    Responsibilities:
    - Track positions across all instruments
    - Calculate realized and unrealized P&L
    - Broadcast position updates on state changes
    - Broadcast account summary updates

    Listens to:
    - fill events: Update positions on fills
    - quote events: Update mark-to-market pricing

    Publishes:
    - position.update (on_broadcasted): When position changes
    - account.update (on_broadcasted): Periodic account summary
    """

    def __init__(
        self,
        engine_endpoint: Endpoint,
        module_id: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(engine_endpoint, module_id=module_id, **kwargs)
        self._positions: Dict[str, Position] = {}
        self._total_realized_pnl: Decimal = Decimal("0")
        self._total_unrealized_pnl: Decimal = Decimal("0")

    def subscribe_quotes(self, instrument_ids: list) -> None:  # type: ignore[type-arg]
        """Track quote events for mark-to-market updates.

        Under v2, all quote events flow through on_streaming_quote and
        are filtered by instrument_id internally.
        """
        # Ensure positions exist for tracking
        for instrument_id in instrument_ids:
            if instrument_id not in self._positions:
                self._positions[instrument_id] = Position(instrument_id=instrument_id)

    def get_position(self, instrument_id: str) -> Position:
        """Get position for an instrument."""
        if instrument_id not in self._positions:
            self._positions[instrument_id] = Position(instrument_id=instrument_id)
        return self._positions[instrument_id]

    def get_all_positions(self) -> Dict[str, Position]:
        """Get all positions."""
        return dict(self._positions)

    @property
    def total_realized_pnl(self) -> Decimal:
        return sum((p.realized_pnl for p in self._positions.values()), Decimal("0"))

    @property
    def total_unrealized_pnl(self) -> Decimal:
        return sum((p.unrealized_pnl for p in self._positions.values()), Decimal("0"))

    def on_fill(self, payload: Dict[str, Any]) -> None:
        """Process a fill and update position."""
        fill = Fill.from_dict(payload)
        position = self.get_position(fill.instrument_id)

        position.apply_fill(
            side=fill.side,
            quantity=fill.quantity,
            price=fill.price,
            fee=fill.fee,
        )

        logger.info(
            "Portfolio updated: %s %s qty=%s avg=%s pnl=%s",
            fill.instrument_id,
            position.side.name,
            position.quantity,
            position.avg_entry_price,
            position.net_pnl,
        )

        # Broadcast position update
        self._publish_position_update(position)

    def on_streaming_quote(self, payload: Dict[str, Any]) -> None:
        """Update mark-to-market pricing from quotes."""
        instrument_id = payload.get("instrument_id", "")
        if instrument_id not in self._positions:
            return

        # Use mid price for mark-to-market
        bid = Decimal(payload.get("bid", "0"))
        ask = Decimal(payload.get("ask", "0"))
        mid = (bid + ask) / 2 if bid and ask else Decimal("0")

        if mid > Decimal("0"):
            position = self._positions[instrument_id]
            old_pnl = position.unrealized_pnl
            position.update_price(mid)

            # Only broadcast if P&L changed materially
            if abs(position.unrealized_pnl - old_pnl) > Decimal("0.01"):
                self._publish_position_update(position)

    def _publish_position_update(self, position: Position) -> None:
        """Broadcast position update to all subscribers."""
        self.send_event(events.POSITION_UPDATE, position.to_dict())
