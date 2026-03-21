# tests/unit/test_bindings.py
import tyche_core

def test_pyquote_construction():
    q = tyche_core.PyQuote(1, 99.0, 10.0, 100.0, 5.0, 0)
    assert q.spread() == 1.0

def test_bar_interval_eq_int():
    b = tyche_core.bar_interval_from_suffix("M5")
    assert b == tyche_core.BarInterval.M5

def test_bar_interval_topic_suffix_property():
    assert tyche_core.BarInterval.M5.topic_suffix == "M5"
    assert tyche_core.BarInterval.H4.topic_suffix == "H4"

def test_init_ffi_bridge_and_take_pending():
    tyche_core.init_ffi_bridge("svc_test_py")
    result = tyche_core.take_pending("svc_test_py", "NO_TOPIC")
    assert result is None

def test_serialize_deserialize_roundtrip():
    q = tyche_core.PyQuote(42, 10.0, 5.0, 11.0, 3.0, 1000)
    raw = bytes(tyche_core.serialize_quote(q))
    q2 = tyche_core.deserialize_quote(raw)
    assert q2.bid_price == 10.0
