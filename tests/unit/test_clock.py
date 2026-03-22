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


def test_module_accepts_clock_kwarg():
    """Module.__init__ accepts keyword-only clock= and stores it as self._clock."""
    from tyche.core.module import Module
    from tyche.core.clock import SimClock

    class _M(Module):
        service_name = "test.clock_kwarg"

    sim = SimClock()
    m = _M("tcp://x:5555", "tcp://x:5556", "tcp://x:5557", clock=sim)
    assert m._clock is sim


def test_module_default_clock_is_live():
    """Module uses LiveClock when no clock= is provided."""
    from tyche.core.module import Module
    from tyche.core.clock import LiveClock

    class _M(Module):
        service_name = "test.default_clock"

    m = _M("tcp://x:5555", "tcp://x:5556", "tcp://x:5557")
    assert isinstance(m._clock, LiveClock)
