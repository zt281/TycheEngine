"""Order and fill models for order lifecycle management."""

import secrets
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Optional

from modules.trading.models.enums import Offset, OrderStatus, OrderType, Side, TimeInForce


def _generate_order_id() -> str:
    """Generate a unique order ID (client-side)."""
    return secrets.token_hex(8)


@dataclass
class Order:
    """Represents a trading order through its lifecycle."""

    instrument_id: str  # String form of InstrumentId
    side: Side
    order_type: OrderType
    quantity: Decimal
    price: Optional[Decimal] = None  # Required for LIMIT/STOP_LIMIT
    stop_price: Optional[Decimal] = None  # Required for STOP/STOP_LIMIT
    time_in_force: TimeInForce = TimeInForce.GTC
    offset: Offset = Offset.OPEN
    status: OrderStatus = OrderStatus.NEW
    order_id: str = field(default_factory=_generate_order_id)
    venue_order_id: Optional[str] = None  # Exchange-assigned ID
    filled_quantity: Decimal = Decimal("0")
    avg_fill_price: Optional[Decimal] = None
    strategy_id: Optional[str] = None  # Owning strategy module
    created_at: float = 0.0
    updated_at: float = 0.0
    tag: Optional[str] = None  # User-defined tag for grouping

    @property
    def remaining_quantity(self) -> Decimal:
        return self.quantity - self.filled_quantity

    @property
    def is_active(self) -> bool:
        return self.status in (
            OrderStatus.NEW,
            OrderStatus.PENDING_SUBMIT,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIALLY_FILLED,
        )

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "side": self.side.name,
            "order_type": self.order_type.name,
            "quantity": str(self.quantity),
            "price": str(self.price) if self.price else None,
            "stop_price": str(self.stop_price) if self.stop_price else None,
            "time_in_force": self.time_in_force.name,
            "offset": self.offset.name,
            "status": self.status.name,
            "order_id": self.order_id,
            "venue_order_id": self.venue_order_id,
            "filled_quantity": str(self.filled_quantity),
            "avg_fill_price": str(self.avg_fill_price) if self.avg_fill_price else None,
            "strategy_id": self.strategy_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tag": self.tag,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Order":
        return cls(
            instrument_id=d["instrument_id"],
            side=Side[d["side"]],
            order_type=OrderType[d["order_type"]],
            quantity=Decimal(d["quantity"]),
            price=Decimal(d["price"]) if d.get("price") else None,
            stop_price=Decimal(d["stop_price"]) if d.get("stop_price") else None,
            time_in_force=TimeInForce[d["time_in_force"]],
            offset=Offset[d.get("offset", "OPEN")],
            status=OrderStatus[d["status"]],
            order_id=d["order_id"],
            venue_order_id=d.get("venue_order_id"),
            filled_quantity=Decimal(d["filled_quantity"]),
            avg_fill_price=Decimal(d["avg_fill_price"]) if d.get("avg_fill_price") else None,
            strategy_id=d.get("strategy_id"),
            created_at=d.get("created_at", 0.0),
            updated_at=d.get("updated_at", 0.0),
            tag=d.get("tag"),
        )


@dataclass
class Fill:
    """Represents a trade fill (partial or complete)."""

    order_id: str
    instrument_id: str
    side: Side
    price: Decimal
    quantity: Decimal
    timestamp: float
    fill_id: str = field(default_factory=lambda: secrets.token_hex(6))
    fee: Decimal = Decimal("0")
    fee_currency: str = "USD"
    venue_fill_id: Optional[str] = None
    is_maker: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "instrument_id": self.instrument_id,
            "side": self.side.name,
            "price": str(self.price),
            "quantity": str(self.quantity),
            "timestamp": self.timestamp,
            "fill_id": self.fill_id,
            "fee": str(self.fee),
            "fee_currency": self.fee_currency,
            "venue_fill_id": self.venue_fill_id,
            "is_maker": self.is_maker,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Fill":
        return cls(
            order_id=d["order_id"],
            instrument_id=d["instrument_id"],
            side=Side[d["side"]],
            price=Decimal(d["price"]),
            quantity=Decimal(d["quantity"]),
            timestamp=d["timestamp"],
            fill_id=d.get("fill_id", secrets.token_hex(6)),
            fee=Decimal(d.get("fee", "0")),
            fee_currency=d.get("fee_currency", "USD"),
            venue_fill_id=d.get("venue_fill_id"),
            is_maker=d.get("is_maker"),
        )


@dataclass
class OrderUpdate:
    """Order state change notification."""

    order_id: str
    instrument_id: str
    status: OrderStatus
    filled_quantity: Decimal = Decimal("0")
    avg_fill_price: Optional[Decimal] = None
    timestamp: float = 0.0
    reason: Optional[str] = None  # Rejection/cancellation reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "instrument_id": self.instrument_id,
            "status": self.status.name,
            "filled_quantity": str(self.filled_quantity),
            "avg_fill_price": str(self.avg_fill_price) if self.avg_fill_price else None,
            "timestamp": self.timestamp,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "OrderUpdate":
        return cls(
            order_id=d["order_id"],
            instrument_id=d["instrument_id"],
            status=OrderStatus[d["status"]],
            filled_quantity=Decimal(d.get("filled_quantity", "0")),
            avg_fill_price=Decimal(d["avg_fill_price"]) if d.get("avg_fill_price") else None,
            timestamp=d.get("timestamp", 0.0),
            reason=d.get("reason"),
        )
