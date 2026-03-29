"""Market data and order types (stub for early testing)."""

from dataclasses import dataclass
from typing import Literal


# Stub types to allow protocol tests to import the package
# Full implementation in Task 5
@dataclass(frozen=True)
class Tick:
    instrument_id: int
    price: float
    size: float
    side: Literal["buy", "sell"]
    timestamp_ns: int


@dataclass(frozen=True)
class Quote:
    instrument_id: int
    bid_price: float
    bid_size: float
    ask_price: float
    ask_size: float
    timestamp_ns: int


@dataclass(frozen=True)
class Trade:
    instrument_id: int
    price: float
    size: float
    aggressor_side: Literal["buy", "sell"]
    timestamp_ns: int


@dataclass(frozen=True)
class Bar:
    instrument_id: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    interval: str
    timestamp_ns: int


@dataclass(frozen=True)
class Order:
    instrument_id: int
    client_order_id: int
    price: float
    qty: float
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit", "stop", "stop_limit"]
    tif: Literal["GTC", "IOC", "FOK"]
    timestamp_ns: int


@dataclass(frozen=True)
class OrderEvent:
    instrument_id: int
    client_order_id: int
    exchange_order_id: int
    fill_price: float
    fill_qty: float
    kind: Literal["new", "cancel", "replace", "fill", "partial_fill", "reject"]
    timestamp_ns: int


@dataclass(frozen=True)
class Ack:
    client_order_id: int
    exchange_order_id: int
    status: Literal["accepted", "rejected", "cancel_acked"]
    sent_ns: int
    acked_ns: int


@dataclass(frozen=True)
class Position:
    instrument_id: int
    net_qty: float
    avg_cost: float
    timestamp_ns: int


@dataclass(frozen=True)
class Risk:
    instrument_id: int
    delta: float
    gamma: float
    vega: float
    theta: float
    dv01: float
    notional: float
    margin: float
    timestamp_ns: int
