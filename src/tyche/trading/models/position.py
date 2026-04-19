"""Position tracking model."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional

from tyche.trading.models.enums import PositionSide, Side


@dataclass
class Position:
    """Tracks a position in a single instrument."""

    instrument_id: str
    side: PositionSide = PositionSide.FLAT
    quantity: Decimal = Decimal("0")
    avg_entry_price: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    last_price: Decimal = Decimal("0")

    @property
    def market_value(self) -> Decimal:
        """Current market value of the position."""
        return self.quantity * self.last_price

    @property
    def cost_basis(self) -> Decimal:
        """Total cost of entry."""
        return self.quantity * self.avg_entry_price

    @property
    def net_pnl(self) -> Decimal:
        """Total P&L including commissions."""
        return self.realized_pnl + self.unrealized_pnl - self.commission

    def update_price(self, price: Decimal) -> None:
        """Update last price and recalculate unrealized P&L."""
        self.last_price = price
        if self.side == PositionSide.LONG:
            self.unrealized_pnl = (price - self.avg_entry_price) * self.quantity
        elif self.side == PositionSide.SHORT:
            self.unrealized_pnl = (self.avg_entry_price - price) * self.quantity
        else:
            self.unrealized_pnl = Decimal("0")

    def apply_fill(self, side: Side, quantity: Decimal, price: Decimal, fee: Decimal) -> None:
        """Apply a fill to update position state."""
        self.commission += fee

        if self.side == PositionSide.FLAT:
            # Opening new position
            self.quantity = quantity
            self.avg_entry_price = price
            self.side = PositionSide.LONG if side == Side.BUY else PositionSide.SHORT
        elif (self.side == PositionSide.LONG and side == Side.BUY) or (
            self.side == PositionSide.SHORT and side == Side.SELL
        ):
            # Adding to existing position
            total_cost = self.avg_entry_price * self.quantity + price * quantity
            self.quantity += quantity
            self.avg_entry_price = total_cost / self.quantity if self.quantity else Decimal("0")
        else:
            # Reducing or closing position
            if quantity >= self.quantity:
                # Close position (possibly flip)
                close_qty = self.quantity
                if self.side == PositionSide.LONG:
                    self.realized_pnl += (price - self.avg_entry_price) * close_qty
                else:
                    self.realized_pnl += (self.avg_entry_price - price) * close_qty

                remaining = quantity - close_qty
                if remaining > Decimal("0"):
                    # Flip position
                    self.quantity = remaining
                    self.avg_entry_price = price
                    self.side = PositionSide.LONG if side == Side.BUY else PositionSide.SHORT
                else:
                    # Flat
                    self.quantity = Decimal("0")
                    self.avg_entry_price = Decimal("0")
                    self.side = PositionSide.FLAT
            else:
                # Partial close
                if self.side == PositionSide.LONG:
                    self.realized_pnl += (price - self.avg_entry_price) * quantity
                else:
                    self.realized_pnl += (self.avg_entry_price - price) * quantity
                self.quantity -= quantity

        self.update_price(price)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "side": self.side.name,
            "quantity": str(self.quantity),
            "avg_entry_price": str(self.avg_entry_price),
            "realized_pnl": str(self.realized_pnl),
            "unrealized_pnl": str(self.unrealized_pnl),
            "commission": str(self.commission),
            "last_price": str(self.last_price),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Position":
        return cls(
            instrument_id=d["instrument_id"],
            side=PositionSide[d["side"]],
            quantity=Decimal(d["quantity"]),
            avg_entry_price=Decimal(d["avg_entry_price"]),
            realized_pnl=Decimal(d["realized_pnl"]),
            unrealized_pnl=Decimal(d["unrealized_pnl"]),
            commission=Decimal(d.get("commission", "0")),
            last_price=Decimal(d.get("last_price", "0")),
        )
