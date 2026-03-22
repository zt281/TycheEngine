# tests/unit/test_module_clock.py
from tyche.core.clock import SimClock, LiveClock
from tyche.core.module import Module
from abc import ABC


class _Stub(Module):
    service_name = "test.clock.stub"
    cpu_core = None


def test_module_defaults_to_live_clock():
    m = _Stub.__new__(_Stub)
    m.__init__.__func__(m, "tcp://x:1", "tcp://x:2", "tcp://x:3")
    assert isinstance(m._clock, LiveClock)


def test_module_accepts_sim_clock():
    sim = SimClock(start_ns=1_000_000)
    m = _Stub.__new__(_Stub)
    m.__init__.__func__(m, "tcp://x:1", "tcp://x:2", "tcp://x:3", clock=sim)
    assert m._clock is sim
    assert m._clock.now_ns() == 1_000_000


def test_module_clock_is_keyword_only():
    """Passing clock as positional must raise TypeError."""
    import pytest
    sim = SimClock()
    with pytest.raises(TypeError):
        _Stub("tcp://x:1", "tcp://x:2", "tcp://x:3", sim)
