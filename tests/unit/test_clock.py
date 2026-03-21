import time
from tyche.core.clock import LiveClock, SimClock


def test_live_clock_returns_positive_ns():
    clock = LiveClock()
    assert clock.now_ns() > 0


def test_live_clock_is_monotonic():
    clock = LiveClock()
    t1 = clock.now_ns()
    time.sleep(0.001)
    t2 = clock.now_ns()
    assert t2 >= t1


def test_sim_clock_advance_increases_time():
    clock = SimClock(start_ns=1_000_000_000)
    t1 = clock.now_ns()
    clock.advance(500_000_000)
    t2 = clock.now_ns()
    assert t2 == t1 + 500_000_000


def test_sim_clock_start_ns():
    clock = SimClock(start_ns=42)
    assert clock.now_ns() == 42
