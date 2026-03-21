# tests/unit/test_topics.py
import pytest
from tyche.utils.topics import TopicBuilder, TopicValidator, normalise_symbol, suffix_to_bar_interval

def test_normalise_fx_removes_slash():
    assert normalise_symbol("EUR/USD") == "EURUSD"

def test_normalise_option_uses_underscore():
    assert normalise_symbol("AAPL 150C 2025-01-17") == "AAPL_150C_20250117"

def test_normalise_future_uses_underscore():
    assert normalise_symbol("ES Z25") == "ES_Z25"

def test_build_tick_topic():
    assert TopicBuilder.tick("CRYPTO_SPOT", "BINANCE", "BTCUSDT") == "CRYPTO_SPOT.BINANCE.BTCUSDT.TICK"

def test_build_bar_topic():
    from tyche.model.enums import BarInterval
    assert TopicBuilder.bar("EQUITY", "NYSE", "AAPL", BarInterval.M5) == "EQUITY.NYSE.AAPL.BAR.M5"

def test_build_internal_topic():
    assert TopicBuilder.internal("OMS", "ORDER") == "INTERNAL.OMS.ORDER"

def test_invalid_topic_raises():
    with pytest.raises(ValueError):
        TopicValidator.validate("INVALID TOPIC WITH SPACES")

def test_valid_topic_passes():
    TopicValidator.validate("EQUITY.NYSE.AAPL.QUOTE")  # must not raise

def test_topic_with_slash_raises():
    with pytest.raises(ValueError):
        TopicValidator.validate("FX_SPOT.EBS.EUR/USD.TICK")

def test_suffix_to_bar_interval_roundtrip():
    from tyche.model.enums import BarInterval
    assert suffix_to_bar_interval("M5") == BarInterval.M5
    assert suffix_to_bar_interval("H4") == BarInterval.H4

def test_suffix_to_bar_interval_invalid_raises():
    with pytest.raises(ValueError):
        suffix_to_bar_interval("INVALID")
