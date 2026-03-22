# Core Engine Expansion — Task 17: Dispatch Latency Instrumentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-dtype dispatch latency tracking to the `Module` base class — a fixed 1024-sample ring buffer per dtype that accumulates p50/p95/p99 and exposes them via the STATUS command.

**Architecture:** `LatencyStats` is a standalone utility class using a 8 KB fixed `bytearray` ring buffer (no heap growth). `Module` stores one `LatencyStats` per dtype key, initialized lazily. Timing is gated on a `metrics_enabled` class attribute (default `False`) so there is zero overhead when disabled. The STATUS command response includes latency percentiles when `metrics_enabled = True`.

**Tech Stack:** Python 3.9+, `struct` (stdlib), `time.time_ns()` (stdlib). No new dependencies.

**Spec:** `docs/designs/core-engine-expansions.md` — Task 17 section.

**Worktree:** `.worktrees/task-17-latency` (branch `core-engine/task-17-latency`)

---

## Project State at Plan Time

Core Engine v1 (Tasks 1-15 of `docs/plan/core_engine_plan_v2.md`) is fully implemented and committed (latest commit `2c2369d`). All 22 Rust unit tests and 27 Python unit tests pass. The expansion doc (`docs/designs/core-engine-expansions.md`) specifies Tasks 16-20; Task 16 (RecordingModule + ReplayBus) is not yet implemented.

The expansion doc places a sequencing requirement: "Task 16 Step 0 (adding `clock` parameter to `Module.__init__`) must be completed before Task 17 begins." Since Task 16 is not implemented here, this plan includes Task 16 Step 0 as Task 1 below. Task 17 proper follows as Tasks 2-4.

No CRITICAL items are open in `docs/impl/core_engine_implement_v1.md`.

Existing files modified by this plan:
- `tyche/core/module.py` — add `clock` kwarg (Task 1) + latency instrumentation (Task 4)
- `tyche/core/config.py` — add `metrics_enabled` field (Task 3)
- `tests/unit/test_config.py` — add `metrics_enabled` test (Task 3)

New files created by this plan:
- `tyche/utils/latency.py` — `LatencyStats` class
- `tests/unit/test_latency_stats.py` — ring buffer + percentile tests

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `tyche/utils/latency.py` | **Create** | `LatencyStats` ring buffer — fixed 8 KB, p50/p95/p99 |
| `tests/unit/test_latency_stats.py` | **Create** | Tests: empty, N=1, N=1024, N=2048 overflow, p≥1.0 error |
| `tyche/core/config.py` | **Modify** | Add `metrics_enabled: bool = False` to `ModuleConfig` |
| `tests/unit/test_config.py` | **Modify** | Add test for `metrics_enabled` default and TOML loading |
| `tyche/core/module.py` | **Modify** | Add `clock` kwarg; add `_metrics_enabled`/`_latency`; instrument `_dispatch()`; extend STATUS |

---

## Task 1: Prerequisite — Add `clock` Keyword Argument to `Module.__init__`

**Files:**
- Modify: `tyche/core/module.py`

This is Task 16 Step 0 from the expansion spec. It adds an optional keyword-only `clock` parameter to `Module.__init__`, defaulting to `LiveClock()`. This change is required before Task 17 (and Task 16) can be implemented.

Per the expansion spec: only data/dispatch timestamp fields use `self._clock.now_ns()`. Heartbeat scheduling (`next_hb` in `run()`) **must remain on `time.time()`** (wall clock).

This is a modification to a plan-approved file (Task 14 output from `core_engine_plan_v2.md`) and is flagged as a spec deviation in the impl log.

- [ ] **Step 1: Write a failing test that Module accepts a `clock` kwarg**

```python
# Add to tests/unit/test_clock.py (after existing tests)

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
```

- [ ] **Step 2: Run to confirm FAIL**

Run: `python -m pytest tests/unit/test_clock.py::test_module_accepts_clock_kwarg tests/unit/test_clock.py::test_module_default_clock_is_live -v`

Expected: `TypeError: __init__() got an unexpected keyword argument 'clock'`

- [ ] **Step 3: Implement — add `clock` kwarg and `LiveClock` import**

In `tyche/core/module.py`, make these two changes:

**Change 1 — add import at top of file:**
```python
from tyche.core.clock import LiveClock
```

**Change 2 — update `__init__` signature and body:**

Old:
```python
def __init__(self, nexus_address: str, bus_xsub: str, bus_xpub: str):
    self._nexus_address = nexus_address
    self._bus_xsub = bus_xsub
    self._bus_xpub = bus_xpub
    self._stop_event = threading.Event()
    self._log = StructuredLogger(self.service_name)
    self._correlation_id = 0
    self._ctx: Optional[zmq.Context] = None
    self._pub_sock: Optional[zmq.Socket] = None
    self._sub_sock: Optional[zmq.Socket] = None
    self._pair_sock: Optional[zmq.Socket] = None
```

New:
```python
def __init__(self, nexus_address: str, bus_xsub: str, bus_xpub: str, *, clock=None):
    self._nexus_address = nexus_address
    self._bus_xsub = bus_xsub
    self._bus_xpub = bus_xpub
    self._clock = clock if clock is not None else LiveClock()
    self._stop_event = threading.Event()
    self._log = StructuredLogger(self.service_name)
    self._correlation_id = 0
    self._ctx: Optional[zmq.Context] = None
    self._pub_sock: Optional[zmq.Socket] = None
    self._sub_sock: Optional[zmq.Socket] = None
    self._pair_sock: Optional[zmq.Socket] = None
```

- [ ] **Step 4: Run tests to confirm GREEN**

Run: `python -m pytest tests/unit/test_clock.py -v`

Expected: all clock tests pass (was 4, now 6).

- [ ] **Step 5: Run full unit suite to confirm no regressions**

Run: `python -m pytest tests/unit/ -v`

Expected: all tests pass (was 27, now 29).

- [ ] **Step 6: Commit**

```bash
git add tyche/core/module.py tests/unit/test_clock.py
git commit -m "feat(python): add clock kwarg to Module.__init__ (Task 16 Step 0 prerequisite)"
```

---

## Task 2: LatencyStats Ring Buffer

**Files:**
- Create: `tyche/utils/latency.py`
- Create: `tests/unit/test_latency_stats.py`

`LatencyStats` is a fixed-memory ring buffer: 1024 slots × 8 bytes each = 8 KB total. Each sample is a signed 64-bit integer (nanoseconds). `record(ns)` writes using `struct.pack_into` (no allocation). `percentile(p)` unpacks, sorts, and indexes.

- [ ] **Step 1: Write failing tests**

```python
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
    # Write 2048 values: first 1024 are [0..1023], second 1024 are [1024..2047]
    for i in range(2048):
        s.record(i)
    # After wrap, buffer holds the second 1024 values: [1024..2047]
    active_len = min(s._count, 1024)
    assert active_len == 1024
    # The oldest 1024 values are overwritten; minimum in buffer is 1024
    assert s.percentile(0.0) == 1024
    assert s.percentile(0.99) == sorted(range(1024, 2048))[min(int(0.99 * 1024), 1023)]
```

- [ ] **Step 2: Run to confirm FAIL**

Run: `python -m pytest tests/unit/test_latency_stats.py -v`

Expected: `ModuleNotFoundError: No module named 'tyche.utils.latency'`

- [ ] **Step 3: Implement `tyche/utils/latency.py`**

```python
# tyche/utils/latency.py
import struct


class LatencyStats:
    """Fixed-size 1024-sample ring buffer for dispatch latency (nanoseconds).

    Memory: 1024 * 8 = 8192 bytes (fixed; never grows).
    Thread safety: single-writer assumed (only the Module run loop writes).
    """

    _CAPACITY = 1024
    _ITEM_SIZE = 8  # bytes per int64

    def __init__(self):
        self._buf = bytearray(self._CAPACITY * self._ITEM_SIZE)
        self._count = 0  # total samples written (unbounded)

    def record(self, ns: int) -> None:
        """Write a latency sample (nanoseconds) into the ring buffer."""
        struct.pack_into('<q', self._buf, (self._count % self._CAPACITY) * self._ITEM_SIZE, ns)
        self._count += 1

    def percentile(self, p: float) -> int:
        """Return the p-th percentile (p in [0.0, 1.0)).

        Returns 0 when no samples have been recorded.
        Raises ValueError if p >= 1.0.
        """
        if p >= 1.0:
            raise ValueError(f"p must be in [0.0, 1.0), got {p}")
        active_len = min(self._count, self._CAPACITY)
        if active_len == 0:
            return 0
        values = list(struct.unpack_from(f'<{active_len}q', self._buf))
        values.sort()
        return values[min(int(p * active_len), active_len - 1)]
```

- [ ] **Step 4: Run tests to confirm GREEN**

Run: `python -m pytest tests/unit/test_latency_stats.py -v`

Expected: all 6 tests pass.

**Note on `test_latency_stats_overflow_2048_samples`:** After writing indices `[0..2047]`, the ring wraps and the second 1024 writes (`[1024..2047]`) overwrite slots `0..1023`. The buffer now holds values `[1024..2047]` in ring order. `unpack_from` reads from offset 0 in write order (not sorted), which is correct — `percentile()` sorts before indexing so order-in-buffer doesn't matter.

- [ ] **Step 5: Run full unit suite**

Run: `python -m pytest tests/unit/ -v`

Expected: all tests pass (was 29 after Task 1, now 35).

- [ ] **Step 6: Commit**

```bash
git add tyche/utils/latency.py tests/unit/test_latency_stats.py
git commit -m "feat(python): add LatencyStats fixed ring buffer with p50/p95/p99"
```

---

## Task 3: ModuleConfig.metrics_enabled

**Files:**
- Modify: `tyche/core/config.py`
- Modify: `tests/unit/test_config.py`

Add `metrics_enabled: bool = False` to `ModuleConfig`. The field must be optional in TOML (defaults to `False` when absent). The existing config test (`test_module_config_loads`) must continue passing without modifying `config/modules/example_strategy.toml`.

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_config.py`:

```python
def test_module_config_metrics_enabled_default():
    """metrics_enabled defaults to False when absent from TOML."""
    from tyche.core.config import ModuleConfig
    # Use _ROOT (already defined at module scope in test_config.py) for an absolute path
    cfg = ModuleConfig.from_file(str(_ROOT / "config" / "modules" / "example_strategy.toml"))
    assert cfg.metrics_enabled is False


def test_module_config_metrics_enabled_true(tmp_path):
    """metrics_enabled=true is read from TOML correctly."""
    import tomllib
    from tyche.core.config import ModuleConfig
    toml_content = b"""
[module]
service_name = "test.metrics"
metrics_enabled = true
"""
    p = tmp_path / "test_mod.toml"
    p.write_bytes(toml_content)
    cfg = ModuleConfig.from_file(str(p))
    assert cfg.metrics_enabled is True
    assert cfg.service_name == "test.metrics"
```

- [ ] **Step 2: Run to confirm FAIL**

Run: `python -m pytest tests/unit/test_config.py::test_module_config_metrics_enabled_default tests/unit/test_config.py::test_module_config_metrics_enabled_true -v`

Expected: `AttributeError: 'ModuleConfig' object has no attribute 'metrics_enabled'`

- [ ] **Step 3: Implement — update `ModuleConfig`**

In `tyche/core/config.py`, update `ModuleConfig`:

Old:
```python
@dataclass
class ModuleConfig:
    service_name: str
    cpu_core: Optional[int] = None
    subscriptions: list = field(default_factory=list)

    @classmethod
    def from_file(cls, path: str) -> "ModuleConfig":
        with open(path, "rb") as f:
            data = tomllib.load(f)
        m = data["module"]
        return cls(
            service_name=m["service_name"],
            cpu_core=m.get("cpu_core"),
            subscriptions=m.get("subscriptions", []),
        )
```

New:
```python
@dataclass
class ModuleConfig:
    service_name: str
    cpu_core: Optional[int] = None
    subscriptions: list = field(default_factory=list)
    metrics_enabled: bool = False

    @classmethod
    def from_file(cls, path: str) -> "ModuleConfig":
        with open(path, "rb") as f:
            data = tomllib.load(f)
        m = data["module"]
        return cls(
            service_name=m["service_name"],
            cpu_core=m.get("cpu_core"),
            subscriptions=m.get("subscriptions", []),
            metrics_enabled=m.get("metrics_enabled", False),
        )
```

- [ ] **Step 4: Run tests to confirm GREEN**

Run: `python -m pytest tests/unit/test_config.py -v`

Expected: all config tests pass (was 3, now 5).

- [ ] **Step 5: Run full unit suite**

Run: `python -m pytest tests/unit/ -v`

Expected: all tests pass (was 35 after Task 2, now 37).

- [ ] **Step 6: Commit**

```bash
git add tyche/core/config.py tests/unit/test_config.py
git commit -m "feat(python): add metrics_enabled field to ModuleConfig"
```

---

## Task 4: Instrument `Module._dispatch()` + Extend STATUS Response

**Files:**
- Modify: `tyche/core/module.py`

This task instruments `Module._dispatch()` with per-dtype latency timing gated on a `metrics_enabled` class attribute, and extends the STATUS command response to include percentile data when enabled.

**Key rules from spec:**
- `metrics_enabled: bool = False` is a **class-level attribute** on `Module` (mirrors `service_name` / `cpu_core` pattern). Subclasses override it in their class body or it can be set from `ModuleConfig` externally.
- `self._latency: dict[str, LatencyStats]` initialized to `{}` in `__init__`.
- Timer starts at the **top** of `_dispatch()` (before dtype extraction). Elapsed is recorded **immediately after** each typed handler returns.
- `on_raw()` fallback paths are **NOT timed** (unknown dtypes are error conditions).
- When `metrics_enabled = False`: zero overhead — no `time.time_ns()` call, no dict access.
- Dtype key derivation (from topic `parts`):
  - 5-segment BAR topic (`parts[3] == "BAR"`): key = `f"BAR.{parts[4]}"`
  - 4-segment topic: key = `parts[3]`
  - All other (including INTERNAL): key = `parts[-1]`

This is a modification to plan-approved Task 14 output and is flagged as a spec deviation in the impl log.

- [ ] **Step 1: Write failing unit tests for dispatch latency**

```python
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
```

- [ ] **Step 2: Run to confirm FAIL**

Run: `python -m pytest tests/unit/test_dispatch_latency.py -v`

Expected: `AttributeError: '_MetricsMod' object has no attribute '_latency'` — `metrics_enabled = True` resolves fine on the subclass, but `self._latency` doesn't exist yet in `__init__`

- [ ] **Step 3: Implement — update `Module` in `tyche/core/module.py`**

Make the following changes to `tyche/core/module.py`:

**Change 1 — add import at top:**
```python
from tyche.utils.latency import LatencyStats
```

**Change 2 — add class-level attribute after `cpu_core`:**
```python
class Module(ABC):
    service_name: str = "module.base"
    cpu_core: Optional[int] = None
    metrics_enabled: bool = False       # ← add this line
```

**Change 3 — add `self._latency` initialization in `__init__` (after `self._pair_sock`):**
```python
    self._pair_sock: Optional[zmq.Socket] = None
    self._latency: dict = {}            # ← add this line
```

**Change 4 — replace `_dispatch()` with the instrumented version:**

```python
def _dispatch(self, topic: str, payload: bytes):
    parts = topic.split(".")

    # Latency instrumentation — entirely skipped when metrics_enabled=False
    if self.metrics_enabled:
        _t0 = time.time_ns()
        # Determine stats key from topic structure
        if len(parts) >= 5 and parts[3] == "BAR":
            _lkey = f"BAR.{parts[4]}"
        elif len(parts) >= 4:
            _lkey = parts[3]
        else:
            _lkey = parts[-1] if parts else "_"

    # INTERNAL topics: INTERNAL.SUBSYSTEM.EVENT
    if parts[0] == "INTERNAL" and len(parts) >= 3:
        event = parts[2]
        if event in _INTERNAL_DISPATCH:
            deser_name, handler_name = _INTERNAL_DISPATCH[event]
            try:
                obj = getattr(tyche_core, deser_name)(payload)
                getattr(self, handler_name)(topic, obj)
                if self.metrics_enabled:
                    self._latency.setdefault(_lkey, LatencyStats()).record(time.time_ns() - _t0)
            except Exception as e:
                self._log.warn("Internal dispatch failed", event=event, error=str(e))
        else:
            self.on_raw(topic, payload)  # not timed — unknown dtype
        return

    if len(parts) < 4:
        self.on_raw(topic, payload)  # not timed — malformed topic
        return

    dtype = parts[3]

    if dtype == "BAR" and len(parts) >= 5:
        try:
            bar = tyche_core.deserialize_bar(payload)
            interval = suffix_to_bar_interval(parts[4])
            self.on_bar(topic, bar, interval)
            if self.metrics_enabled:
                self._latency.setdefault(_lkey, LatencyStats()).record(time.time_ns() - _t0)
        except Exception as e:
            self._log.warn("Bar dispatch failed", error=str(e))
        return

    if dtype in _MARKET_DISPATCH:
        deser_name, handler_name = _MARKET_DISPATCH[dtype]
        try:
            obj = getattr(tyche_core, deser_name)(payload)
            getattr(self, handler_name)(topic, obj)
            if self.metrics_enabled:
                self._latency.setdefault(_lkey, LatencyStats()).record(time.time_ns() - _t0)
        except Exception as e:
            self._log.warn("Market dispatch failed", dtype=dtype, error=str(e))
    else:
        self.on_raw(topic, payload)  # not timed — unknown dtype
```

**Change 5 — extend STATUS handler in `_handle_nexus()`:**

Old STATUS branch:
```python
elif command == "STATUS":
    result = {"status": "RUNNING", "pid": _os.getpid()}
```

New STATUS branch:
```python
elif command == "STATUS":
    result = {"status": "RUNNING", "pid": _os.getpid()}
    if self.metrics_enabled and self._latency:
        result["dispatch_latency_ns"] = {
            key: {
                "p50": stats.percentile(0.50),
                "p95": stats.percentile(0.95),
                "p99": stats.percentile(0.99),
            }
            for key, stats in self._latency.items()
        }
```

- [ ] **Step 4: Run dispatch latency tests to confirm GREEN**

Run: `python -m pytest tests/unit/test_dispatch_latency.py -v`

Expected: all 5 tests pass.

- [ ] **Step 5: Run full unit suite**

Run: `python -m pytest tests/unit/ -v`

Expected: all tests pass (was 37 after Task 3, now 42).

- [ ] **Step 6: Commit**

```bash
git add tyche/core/module.py tests/unit/test_dispatch_latency.py
git commit -m "feat(python): add dispatch latency instrumentation with per-dtype ring buffer"
```

---

## Task 5: Final Verification

- [ ] **Step 1: Run Rust tests (offline)**

Run: `cargo test --manifest-path tyche-core/Cargo.toml --offline`

Expected: 22 passed, 0 failed.

- [ ] **Step 2: Run full Python unit suite**

Run: `python -m pytest tests/unit/ -v`

Expected: all 42 tests pass (27 original + 2 clock + 6 latency_stats + 2 config + 5 dispatch_latency).

- [ ] **Step 3: Create implementation log**

Create `docs/impl/core_engine_implement_v2.md` with the standard structure (see CLAUDE.md for format). Initial CRITICAL section: `_(none)_`.

- [ ] **Step 4: Final commit for impl log**

```bash
git add docs/impl/core_engine_implement_v2.md
git commit -m "docs: add core engine expansion v2 implementation log (Task 17)"
```

---

*Total: 5 tasks, ~25 steps. New Python unit tests: 15 (2 clock, 6 latency_stats, 2 config, 5 dispatch_latency).*
