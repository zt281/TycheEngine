# tests/unit/test_latency_stats.py
import pytest
import struct
from tyche.utils.latency import LatencyStats


def test_latency_stats_empty_returns_zero():
    s = LatencyStats()
    assert s.percentile(0.50) == 0
    assert s.percentile(0.99) == 0


def test_latency_stats_p_gte_one_raises():
    s = LatencyStats()
    with pytest.raises(ValueError, match="p must be in"):
        s.percentile(1.0)
    with pytest.raises(ValueError, match="p must be in"):
        s.percentile(1.5)


def test_latency_stats_single_sample():
    s = LatencyStats()
    s.record(1000)
    assert s.percentile(0.0) == 1000
    assert s.percentile(0.50) == 1000
    assert s.percentile(0.99) == 1000


def test_latency_stats_n_samples_sorted():
    """p50/p95/p99 are correct for N=10 distinct values."""
    s = LatencyStats()
    for ns in range(10, 0, -1):   # insert descending: 10,9,...,1
        s.record(ns)
    # sorted: [1,2,3,4,5,6,7,8,9,10] (10 samples)
    # Spec formula: values[min(int(p * active_len), active_len - 1)]
    # p=0.50 → values[min(int(0.50*10), 9)] = values[5] = 6
    assert s.percentile(0.50) == 6
    assert s.percentile(0.0)  == 1
    assert s.percentile(0.90) == sorted(range(1, 11))[min(int(0.90*10), 9)]


def test_latency_stats_exactly_1024_samples():
    """At capacity: active_len == 1024, all slots used."""
    s = LatencyStats()
    for i in range(1024):
        s.record(i)
    assert s.percentile(0.0) == 0
    assert s.percentile(0.99) == sorted(range(1024))[min(int(0.99 * 1024), 1023)]


def test_latency_stats_overflow_2048_samples():
    """After 2048 writes the ring wraps twice; active_len stays capped at 1024."""
    s = LatencyStats()
    for i in range(2048):
        s.record(i)
    # After wrap, buffer holds the second 1024 values: [1024..2047]
    active_len = min(s._count, 1024)
    assert active_len == 1024
    # The oldest 1024 values are overwritten; minimum in buffer is 1024
    assert s.percentile(0.0) == 1024
    assert s.percentile(0.99) == sorted(range(1024, 2048))[min(int(0.99 * 1024), 1023)]
