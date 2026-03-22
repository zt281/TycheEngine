# tests/unit/test_dispatch_latency.py
import tyche_core
from tyche.core.module import Module
from tyche.utils.latency import LatencyStats


class _MetricsMod(Module):
    """Concrete Module subclass with metrics enabled for testing."""
    service_name = "test.metrics_dispatch"
    metrics_enabled = True

    def __init__(self):
        # Pass dummy addresses; run() is never called in these tests
        super().__init__("tcp://x:5555", "tcp://x:5556", "tcp://x:5557")

    def on_quote(self, topic, quote):
        self._last_quote = quote


def test_dispatch_records_quote_latency():
    """Dispatching a QUOTE message records a latency sample under key 'QUOTE'."""
    m = _MetricsMod()
    q = tyche_core.PyQuote(1, 99.0, 5.0, 100.0, 3.0, 0)
    payload = bytes(tyche_core.serialize_quote(q))
    m._dispatch("EQUITY.NYSE.AAPL.QUOTE", payload)
    assert "QUOTE" in m._latency
    assert m._latency["QUOTE"]._count == 1


def test_dispatch_records_bar_latency():
    """BAR topics record under key 'BAR.M5' (not just 'BAR')."""
    m = _MetricsMod()
    bar = tyche_core.PyBar(1, 100.0, 105.0, 99.0, 103.0, 500.0, tyche_core.BarInterval.M5, 0)
    payload = bytes(tyche_core.serialize_bar(bar))
    m._dispatch("EQUITY.NYSE.AAPL.BAR.M5", payload)
    assert "BAR.M5" in m._latency
    assert m._latency["BAR.M5"]._count == 1


def test_dispatch_no_timing_for_on_raw():
    """Unknown dtype falls to on_raw(); no latency entry is created."""
    m = _MetricsMod()
    m._dispatch("EQUITY.NYSE.AAPL.UNKNOWN_DTYPE", b"garbage")
    assert len(m._latency) == 0


def test_dispatch_no_timing_when_disabled():
    """When metrics_enabled=False, _latency stays empty regardless of messages."""
    class _NoMetrics(Module):
        service_name = "test.no_metrics"
        metrics_enabled = False
        def __init__(self):
            super().__init__("tcp://x:5555", "tcp://x:5556", "tcp://x:5557")

    m = _NoMetrics()
    q = tyche_core.PyQuote(1, 99.0, 5.0, 100.0, 3.0, 0)
    payload = bytes(tyche_core.serialize_quote(q))
    m._dispatch("EQUITY.NYSE.AAPL.QUOTE", payload)
    assert len(m._latency) == 0


def test_dispatch_latency_accumulates():
    """Multiple dispatches accumulate samples in the same LatencyStats."""
    m = _MetricsMod()
    q = tyche_core.PyQuote(1, 99.0, 5.0, 100.0, 3.0, 0)
    payload = bytes(tyche_core.serialize_quote(q))
    for _ in range(5):
        m._dispatch("EQUITY.NYSE.AAPL.QUOTE", payload)
    assert m._latency["QUOTE"]._count == 5
