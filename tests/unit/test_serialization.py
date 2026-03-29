"""Unit tests for tyche_client.serialization module."""

import pytest


def test_encode_tick():
    from tyche_client.types import Tick
    from tyche_client.serialization import encode

    tick = Tick(
        instrument_id=12345,
        price=150.25,
        size=100.0,
        side="buy",
        timestamp_ns=1711632000000000000
    )
    data = encode(tick)
    assert isinstance(data, bytes)

    # Verify msgpack format with _type field
    import msgpack
    d = msgpack.unpackb(data, raw=False)
    assert d["_type"] == "Tick"
    assert d["instrument_id"] == 12345
    assert d["price"] == 150.25


def test_decode_tick():
    import msgpack
    from tyche_client.types import Tick
    from tyche_client.serialization import decode

    data = msgpack.packb({
        "_type": "Tick",
        "instrument_id": 12345,
        "price": 150.25,
        "size": 100.0,
        "side": "buy",
        "timestamp_ns": 1711632000000000000
    })
    obj = decode(data)
    assert isinstance(obj, Tick)
    assert obj.instrument_id == 12345
    assert obj.price == 150.25


def test_roundtrip_quote():
    from tyche_client.types import Quote
    from tyche_client.serialization import encode, decode

    quote = Quote(
        instrument_id=12345,
        bid_price=150.20,
        bid_size=500.0,
        ask_price=150.30,
        ask_size=300.0,
        timestamp_ns=1711632000000000000
    )
    data = encode(quote)
    decoded = decode(data)
    assert decoded == quote


def test_roundtrip_order():
    from tyche_client.types import Order
    from tyche_client.serialization import encode, decode

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
    data = encode(order)
    decoded = decode(data)
    assert decoded == order


def test_decode_unknown_type_raises():
    import msgpack
    from tyche_client.serialization import decode

    data = msgpack.packb({
        "_type": "UnknownType",
        "field": "value"
    })
    with pytest.raises(ValueError, match="Unknown type"):
        decode(data)


def test_type_map_has_all_types():
    from tyche_client.serialization import TYPE_MAP
    from tyche_client.types import Tick, Quote, Trade, Bar, Order, OrderEvent, Ack, Position, Risk

    assert "Tick" in TYPE_MAP
    assert "Quote" in TYPE_MAP
    assert "Trade" in TYPE_MAP
    assert "Bar" in TYPE_MAP
    assert "Order" in TYPE_MAP
    assert "OrderEvent" in TYPE_MAP
    assert "Ack" in TYPE_MAP
    assert "Position" in TYPE_MAP
    assert "Risk" in TYPE_MAP
