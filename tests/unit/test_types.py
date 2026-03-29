"""Unit tests for tyche_client.types module."""

import pytest


def test_tick_creation():
    from tyche_client.types import Tick

    tick = Tick(
        instrument_id=12345,
        price=150.25,
        size=100.0,
        side="buy",
        timestamp_ns=1711632000000000000
    )
    assert tick.instrument_id == 12345
    assert tick.price == 150.25
    assert tick.side == "buy"


def test_tick_is_frozen():
    from tyche_client.types import Tick

    tick = Tick(
        instrument_id=12345,
        price=150.25,
        size=100.0,
        side="buy",
        timestamp_ns=1711632000000000000
    )
    with pytest.raises(AttributeError):
        tick.price = 200.0


def test_quote_creation():
    from tyche_client.types import Quote

    quote = Quote(
        instrument_id=12345,
        bid_price=150.20,
        bid_size=500.0,
        ask_price=150.30,
        ask_size=300.0,
        timestamp_ns=1711632000000000000
    )
    assert quote.bid_price == 150.20
    assert quote.ask_price == 150.30


def test_trade_creation():
    from tyche_client.types import Trade

    trade = Trade(
        instrument_id=12345,
        price=150.25,
        size=100.0,
        aggressor_side="buy",
        timestamp_ns=1711632000000000000
    )
    assert trade.aggressor_side == "buy"


def test_bar_creation():
    from tyche_client.types import Bar

    bar = Bar(
        instrument_id=12345,
        open=150.0,
        high=151.0,
        low=149.0,
        close=150.5,
        volume=10000.0,
        interval="M1",
        timestamp_ns=1711632000000000000
    )
    assert bar.interval == "M1"


def test_order_creation():
    from tyche_client.types import Order

    order = Order(
        instrument_id=12345,
        client_order_id=987654321,
        price=150.25,
        qty=100.0,
        side="buy",
        order_type="limit",
        tif="GTC",
        timestamp_ns=1711632000000000000
    )
    assert order.order_type == "limit"
    assert order.tif == "GTC"


def test_order_event_creation():
    from tyche_client.types import OrderEvent

    event = OrderEvent(
        instrument_id=12345,
        client_order_id=987654321,
        exchange_order_id=111,
        fill_price=150.25,
        fill_qty=100.0,
        kind="fill",
        timestamp_ns=1711632000000000000
    )
    assert event.kind == "fill"


def test_ack_creation():
    from tyche_client.types import Ack

    ack = Ack(
        client_order_id=987654321,
        exchange_order_id=111,
        status="accepted",
        sent_ns=1711632000000000000,
        acked_ns=1711632000001000000
    )
    assert ack.status == "accepted"


def test_position_creation():
    from tyche_client.types import Position

    pos = Position(
        instrument_id=12345,
        net_qty=100.0,
        avg_cost=150.0,
        timestamp_ns=1711632000000000000
    )
    assert pos.net_qty == 100.0


def test_risk_creation():
    from tyche_client.types import Risk

    risk = Risk(
        instrument_id=12345,
        delta=0.5,
        gamma=0.01,
        vega=0.1,
        theta=-0.05,
        dv01=1000.0,
        notional=100000.0,
        margin=10000.0,
        timestamp_ns=1711632000000000000
    )
    assert risk.delta == 0.5
