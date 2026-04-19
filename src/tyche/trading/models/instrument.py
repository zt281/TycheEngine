"""Instrument identification and specification."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional

from tyche.trading.models.enums import AssetClass, VenueType


@dataclass(frozen=True)
class InstrumentId:
    """Unique instrument identifier: symbol.venue.asset_class.

    Examples:
        - BTCUSDT.binance.crypto
        - IF2406.ctp.futures
        - AAPL.ib.equity
    """

    symbol: str
    venue: str
    asset_class: AssetClass

    def __str__(self) -> str:
        return f"{self.symbol}.{self.venue}.{self.asset_class.name.lower()}"

    @classmethod
    def from_str(cls, s: str) -> "InstrumentId":
        """Parse from 'SYMBOL.venue.asset_class' string."""
        parts = s.split(".")
        if len(parts) != 3:
            raise ValueError(f"Invalid InstrumentId format: {s!r}, expected 'symbol.venue.asset_class'")
        return cls(
            symbol=parts[0],
            venue=parts[1],
            asset_class=AssetClass[parts[2].upper()],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "venue": self.venue,
            "asset_class": self.asset_class.name,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "InstrumentId":
        return cls(
            symbol=d["symbol"],
            venue=d["venue"],
            asset_class=AssetClass[d["asset_class"]],
        )


@dataclass
class Instrument:
    """Full instrument specification with trading parameters."""

    instrument_id: InstrumentId
    venue_type: VenueType
    tick_size: Decimal = Decimal("0.01")
    lot_size: Decimal = Decimal("1")
    min_quantity: Decimal = Decimal("1")
    max_quantity: Optional[Decimal] = None
    price_precision: int = 2
    quantity_precision: int = 0
    contract_multiplier: Decimal = Decimal("1")
    base_currency: str = "USD"
    quote_currency: str = "USD"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instrument_id": self.instrument_id.to_dict(),
            "venue_type": self.venue_type.name,
            "tick_size": str(self.tick_size),
            "lot_size": str(self.lot_size),
            "min_quantity": str(self.min_quantity),
            "max_quantity": str(self.max_quantity) if self.max_quantity else None,
            "price_precision": self.price_precision,
            "quantity_precision": self.quantity_precision,
            "contract_multiplier": str(self.contract_multiplier),
            "base_currency": self.base_currency,
            "quote_currency": self.quote_currency,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Instrument":
        return cls(
            instrument_id=InstrumentId.from_dict(d["instrument_id"]),
            venue_type=VenueType[d["venue_type"]],
            tick_size=Decimal(d["tick_size"]),
            lot_size=Decimal(d["lot_size"]),
            min_quantity=Decimal(d["min_quantity"]),
            max_quantity=Decimal(d["max_quantity"]) if d.get("max_quantity") else None,
            price_precision=d["price_precision"],
            quantity_precision=d["quantity_precision"],
            contract_multiplier=Decimal(d["contract_multiplier"]),
            base_currency=d["base_currency"],
            quote_currency=d["quote_currency"],
        )
