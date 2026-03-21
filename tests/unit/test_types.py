# tests/unit/test_types.py
import tyche_core

def test_all_types_importable():
    from tyche.model.types import Quote, Tick, Trade, Bar, Order, Position, Risk, Model, Ack, OrderEvent
    from tyche.model.enums import BarInterval, Side, OrderType, TIF, ModelKind, AssetClass
    # If imports succeed, test passes
    assert Quote is tyche_core.PyQuote
    assert BarInterval is tyche_core.BarInterval

def test_quote_spread():
    from tyche.model.types import Quote
    q = Quote(instrument_id=1, bid_price=99.0, bid_size=5.0, ask_price=100.0, ask_size=3.0, timestamp_ns=0)
    assert q.spread() == 1.0

def test_bar_interval_suffix():
    from tyche.model.enums import BarInterval
    assert BarInterval.M5.topic_suffix == "M5"
    assert BarInterval.H4.topic_suffix == "H4"

def test_side_equality():
    from tyche.model.enums import Side
    assert Side.Buy == tyche_core.Side.Buy
    assert Side.Sell != Side.Buy
