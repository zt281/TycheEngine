"""Market data types: Quote, Trade, Bar."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from tyche.trading.models.enums import Side


@dataclass
class Quote:
    """Level-1 quote (best bid/ask)."""

    instrument_id: str  # String form of InstrumentId
    bid: Decimal
    ask: Decimal
    bid_size: Decimal
    ask_size: Decimal
    timestamp: float  # Unix timestamp with microsecond precision
    venue_timestamp: Optional[float] = None  # Exchange-reported timestamp

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "bid": str(self.bid),
            "ask": str(self.ask),
            "bid_size": str(self.bid_size),
            "ask_size": str(self.ask_size),
            "timestamp": self.timestamp,
            "venue_timestamp": self.venue_timestamp,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Quote":
        return cls(
            instrument_id=d["instrument_id"],
            bid=Decimal(d["bid"]),
            ask=Decimal(d["ask"]),
            bid_size=Decimal(d["bid_size"]),
            ask_size=Decimal(d["ask_size"]),
            timestamp=d["timestamp"],
            venue_timestamp=d.get("venue_timestamp"),
        )


@dataclass
class Trade:
    """Individual trade/tick event."""

    instrument_id: str
    price: Decimal
    size: Decimal
    side: Side  # Aggressor side
    timestamp: float
    trade_id: Optional[str] = None
    venue_timestamp: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "price": str(self.price),
            "size": str(self.size),
            "side": self.side.name,
            "timestamp": self.timestamp,
            "trade_id": self.trade_id,
            "venue_timestamp": self.venue_timestamp,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Trade":
        return cls(
            instrument_id=d["instrument_id"],
            price=Decimal(d["price"]),
            size=Decimal(d["size"]),
            side=Side[d["side"]],
            timestamp=d["timestamp"],
            trade_id=d.get("trade_id"),
            venue_timestamp=d.get("venue_timestamp"),
        )


@dataclass
class Bar:
    """OHLCV bar/candle."""

    instrument_id: str
    timeframe: str  # e.g., "1m", "5m", "1h", "1d"
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    timestamp: float  # Bar open timestamp
    close_timestamp: Optional[float] = None
    trade_count: Optional[int] = None
    vwap: Optional[Decimal] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "instrument_id": self.instrument_id,
            "timeframe": self.timeframe,
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": str(self.volume),
            "timestamp": self.timestamp,
            "close_timestamp": self.close_timestamp,
            "trade_count": self.trade_count,
            "vwap": str(self.vwap) if self.vwap else None,
        }
        return result

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Bar":
        return cls(
            instrument_id=d["instrument_id"],
            timeframe=d["timeframe"],
            open=Decimal(d["open"]),
            high=Decimal(d["high"]),
            low=Decimal(d["low"]),
            close=Decimal(d["close"]),
            volume=Decimal(d["volume"]),
            timestamp=d["timestamp"],
            close_timestamp=d.get("close_timestamp"),
            trade_count=d.get("trade_count"),
            vwap=Decimal(d["vwap"]) if d.get("vwap") else None,
        )


@dataclass
class OrderBookLevel:
    """Single price level in the order book."""

    price: Decimal
    size: Decimal
    order_count: Optional[int] = None


@dataclass
class OrderBook:
    """Level-2 order book snapshot."""

    instrument_id: str
    bids: List[OrderBookLevel] = field(default_factory=list)
    asks: List[OrderBookLevel] = field(default_factory=list)
    timestamp: float = 0.0
    sequence: Optional[int] = None

    @property
    def best_bid(self) -> Optional[Decimal]:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[Decimal]:
        return self.asks[0].price if self.asks else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "bids": [[str(l.price), str(l.size)] for l in self.bids],
            "asks": [[str(l.price), str(l.size)] for l in self.asks],
            "timestamp": self.timestamp,
            "sequence": self.sequence,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "OrderBook":
        return cls(
            instrument_id=d["instrument_id"],
            bids=[OrderBookLevel(Decimal(p), Decimal(s)) for p, s in d["bids"]],
            asks=[OrderBookLevel(Decimal(p), Decimal(s)) for p, s in d["asks"]],
            timestamp=d["timestamp"],
            sequence=d.get("sequence"),
        )
