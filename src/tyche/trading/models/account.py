"""Account and balance models for portfolio tracking."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional


@dataclass
class Balance:
    """Single currency balance."""

    currency: str
    total: Decimal = Decimal("0")
    available: Decimal = Decimal("0")
    frozen: Decimal = Decimal("0")

    @property
    def used(self) -> Decimal:
        """Amount currently in use (frozen + in orders)."""
        return self.total - self.available

    def to_dict(self) -> Dict[str, Any]:
        return {
            "currency": self.currency,
            "total": str(self.total),
            "available": str(self.available),
            "frozen": str(self.frozen),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Balance":
        return cls(
            currency=d["currency"],
            total=Decimal(d["total"]),
            available=Decimal(d["available"]),
            frozen=Decimal(d.get("frozen", "0")),
        )


@dataclass
class Account:
    """Trading account state across all currencies."""

    account_id: str = ""
    venue: str = ""
    balances: List[Balance] = field(default_factory=list)
    total_equity: Decimal = Decimal("0")
    margin_used: Decimal = Decimal("0")
    margin_available: Decimal = Decimal("0")
    margin_ratio: Optional[Decimal] = None  # margin_used / total_equity
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    timestamp: float = 0.0

    def get_balance(self, currency: str) -> Optional[Balance]:
        """Get balance for a specific currency."""
        for b in self.balances:
            if b.currency == currency:
                return b
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "account_id": self.account_id,
            "venue": self.venue,
            "balances": [b.to_dict() for b in self.balances],
            "total_equity": str(self.total_equity),
            "margin_used": str(self.margin_used),
            "margin_available": str(self.margin_available),
            "margin_ratio": str(self.margin_ratio) if self.margin_ratio else None,
            "unrealized_pnl": str(self.unrealized_pnl),
            "realized_pnl": str(self.realized_pnl),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Account":
        return cls(
            account_id=d.get("account_id", ""),
            venue=d.get("venue", ""),
            balances=[Balance.from_dict(b) for b in d.get("balances", [])],
            total_equity=Decimal(d.get("total_equity", "0")),
            margin_used=Decimal(d.get("margin_used", "0")),
            margin_available=Decimal(d.get("margin_available", "0")),
            margin_ratio=Decimal(d["margin_ratio"]) if d.get("margin_ratio") else None,
            unrealized_pnl=Decimal(d.get("unrealized_pnl", "0")),
            realized_pnl=Decimal(d.get("realized_pnl", "0")),
            timestamp=d.get("timestamp", 0.0),
        )
