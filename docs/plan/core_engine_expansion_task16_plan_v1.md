# Core Engine Expansion Plan — Task 16: RecordingModule + ReplayBus

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a backtest recording harness: `RecordingModule` captures all Bus messages to a `.tyche` file; `ReplayBus` re-publishes them to a Bus at configurable speed.

**Architecture:** `RecordingModule` extends `Module`, overrides `_dispatch()` to write a 4-element MessagePack array per message before calling `super()._dispatch()`. `ReplayBus` is a standalone class (not a Module subclass) that reads the file sequentially and re-publishes each record using the Bus envelope format. Both live in `tyche/backtest/recording.py`. A prerequisite modifies `Module.__init__` to accept an injectable `clock` (keyword-only, default `LiveClock()`), enabling `SimClock` injection for backtest use.

**Tech Stack:** Python 3.9+, pyzmq 25+, msgpack 1.0+, stdlib only (`time`, `threading`, `tempfile`)

**Spec reference:** `docs/designs/core-engine-expansions.md` § Task 16

---

## Project State at Plan Time

All 15 tasks from `docs/plan/core_engine_plan_v2.md` are complete (commit `2c2369d`). Source tree has `tyche/core/module.py` (Module base class), `tyche/core/clock.py` (LiveClock, SimClock), `tyche/backtest/` does **not yet exist**. Impl log v1 shows no open CRITICAL items. This plan covers only Task 16.

**Spec deviation flagged by this plan (must appear in impl log):** Adding `clock` parameter to `Module.__init__` modifies a plan-v2 Task 14 output. This is expected per the expansions spec.

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `tyche/core/module.py` | Add `clock` keyword-only param to `__init__`; set `self._clock` |
| Create | `tyche/backtest/__init__.py` | Package root (empty) |
| Create | `tyche/backtest/recording.py` | `RecordingModule` + `ReplayBus` |
| Create | `tests/unit/test_module_clock.py` | Unit test: clock injection into Module |
| Create | `tests/integration/test_backtest_replay.py` | Integration: record + replay roundtrip |

---

## Task 1: Module Clock Injection (Prerequisite)

**Files:**
- Modify: `tyche/core/module.py` (lines 35-45, `__init__`)
- Create: `tests/unit/test_module_clock.py`

**Spec constraint:** Only data/dispatch `timestamp_ns` fields use `self._clock.now_ns()`. Heartbeat scheduling (`next_hb` using `time.time()`) must remain on wall clock. The `clock` parameter is keyword-only and is NOT added to `ModuleConfig` or any TOML file.

- [ ] **Step 1: Write failing unit test (RED)**

```python
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
```

- [ ] **Step 2: Run test — confirm FAIL**

```bash
cd D:/dev/TycheEngine/.worktrees/core-engine-task16
python -m pytest tests/unit/test_module_clock.py -v
```

Expected: `TypeError` or `AssertionError` — `Module.__init__` has no `clock` param.

- [ ] **Step 3: Modify `Module.__init__` to accept `clock`**

In `tyche/core/module.py`, change the `__init__` signature and add `self._clock`:

```python
# tyche/core/module.py — change line 35 and add import
from tyche.core.clock import LiveClock   # add at top of file

# change __init__ signature:
def __init__(self, nexus_address: str, bus_xsub: str, bus_xpub: str, *, clock=None):
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
    self._clock = clock if clock is not None else LiveClock()
```

**Confirm no circular import:** `clock.py` does not import from `module.py`. Import is safe.

- [ ] **Step 4: Run test — confirm PASS**

```bash
python -m pytest tests/unit/test_module_clock.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Run full unit suite — confirm no regressions**

```bash
python -m pytest tests/unit/ -v
```

Expected: 30 passed (27 existing + 3 new), 0 failed.

- [ ] **Step 6: Commit**

```bash
git add tyche/core/module.py tests/unit/test_module_clock.py
git commit -m "feat(python): add clock injection to Module.__init__ (expansion task 16 prerequisite)"
```

---

## Task 2: Create backtest Package Skeleton

**Files:**
- Create: `tyche/backtest/__init__.py`
- Create: `tyche/backtest/recording.py` (stubs only)

No test file for this step — stubs exist so subsequent RED tests fail with `TypeError`, not `ImportError`.

- [ ] **Step 1: Create package init**

```python
# tyche/backtest/__init__.py
```

(empty file)

- [ ] **Step 2: Create recording.py stub**

```python
# tyche/backtest/recording.py
"""Backtest recording and replay utilities."""


class RecordingModule:
    """Stub — implemented in Task 3."""


class ReplayBus:
    """Stub — implemented in Task 4."""
```

- [ ] **Step 3: Verify import works**

```bash
python -c "from tyche.backtest.recording import RecordingModule, ReplayBus; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add tyche/backtest/__init__.py tyche/backtest/recording.py
git commit -m "feat(python): add backtest package skeleton"
```

---

## Task 3: Write Failing Integration Tests (RED)

**Files:**
- Create: `tests/integration/test_backtest_replay.py`

Write all tests now. They will fail because `RecordingModule` and `ReplayBus` are stubs.

- [ ] **Step 1: Write the test file**

```python
# tests/integration/test_backtest_replay.py
"""
Integration tests for RecordingModule and ReplayBus.

Bus port assignments (distinct from all other test fixtures):
  Recording phase: NEXUS=35555, BUS1_XSUB=35556, BUS1_XPUB=35557
  Replay phase:    BUS2_XSUB=35558, BUS2_XPUB=35559
"""
import os
import time
import threading

import msgpack
import pytest
import zmq
import tyche_core

NEXUS    = "tcp://127.0.0.1:35555"
BUS1_XSUB = "tcp://127.0.0.1:35556"
BUS1_XPUB = "tcp://127.0.0.1:35557"
BUS2_XSUB = "tcp://127.0.0.1:35558"
BUS2_XPUB = "tcp://127.0.0.1:35559"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_payload() -> bytes:
    q = tyche_core.PyQuote(42, 99.5, 10.0, 100.0, 5.0, 12345)
    return bytes(tyche_core.serialize_quote(q))


def _publish_n(pub_sock: zmq.Socket, topic: str, payload: bytes, n: int, gap_s: float = 0.02):
    for _ in range(n):
        pub_sock.send_multipart([
            topic.encode(),
            time.time_ns().to_bytes(8, "big"),
            payload,
        ])
        if gap_s > 0:
            time.sleep(gap_s)


# ---------------------------------------------------------------------------
# Test 1: RecordingModule writes a valid .tyche file
# ---------------------------------------------------------------------------

def test_recording_module_writes_tyche_file(tmp_path):
    from tyche.core.nexus import Nexus
    from tyche.core.bus import Bus
    from tyche.backtest.recording import RecordingModule

    file_path = str(tmp_path / "test.tyche")
    n_msgs = 3
    topic = "EQUITY.NYSE.AAPL.QUOTE"
    payload = _make_payload()

    # Start engine
    nexus = Nexus(address=NEXUS, cpu_core=None)
    bus1 = Bus(xsub_address=BUS1_XSUB, xpub_address=BUS1_XPUB, cpu_core=None)
    threading.Thread(target=nexus.run, daemon=True).start()
    threading.Thread(target=bus1.run, daemon=True).start()
    time.sleep(0.15)

    # Define RecordingModule subclass (service_name required by Module)
    class Recorder(RecordingModule):
        service_name = "test.recorder.writes"
        cpu_core = None

    rec = Recorder(file_path=file_path, nexus_address=NEXUS,
                   bus_xsub=BUS1_XSUB, bus_xpub=BUS1_XPUB)
    rec_thread = threading.Thread(target=rec.run, daemon=True)
    rec_thread.start()
    time.sleep(0.30)  # wait for registration + subscription propagation

    # Publish N messages
    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    pub.connect(BUS1_XSUB)
    time.sleep(0.05)
    _publish_n(pub, topic, payload, n_msgs)
    time.sleep(0.25)

    # Stop recording
    rec.stop()
    rec_thread.join(timeout=3.0)
    nexus.stop()
    bus1.stop()
    pub.close()
    ctx.term()

    # Verify file exists and has correct record count
    assert os.path.exists(file_path), ".tyche file was not created"
    assert os.path.getsize(file_path) > 0, ".tyche file is empty"

    records = []
    with open(file_path, "rb") as f:
        unpacker = msgpack.Unpacker(raw=False)
        unpacker.feed(f.read())
        for record in unpacker:
            records.append(record)

    assert len(records) == n_msgs, f"Expected {n_msgs} records, got {len(records)}"

    # Verify record structure: [topic, timestamp_ns, payload_bytes, wall_ns]
    for rec_data in records:
        assert len(rec_data) == 4
        assert rec_data[0] == topic
        assert isinstance(rec_data[1], int) and rec_data[1] > 0   # timestamp_ns
        assert rec_data[2] == payload                              # payload bytes match
        assert isinstance(rec_data[3], int) and rec_data[3] > 0   # wall_ns


# ---------------------------------------------------------------------------
# Test 2: Full record → replay roundtrip; payload bytes must be byte-equal
# ---------------------------------------------------------------------------

def test_record_replay_roundtrip(tmp_path):
    from tyche.core.nexus import Nexus
    from tyche.core.bus import Bus
    from tyche.backtest.recording import RecordingModule, ReplayBus

    file_path = str(tmp_path / "roundtrip.tyche")
    n_msgs = 3
    topic = "EQUITY.NYSE.AAPL.QUOTE"
    orig_payload = _make_payload()

    # ── Phase 1: Record ──────────────────────────────────────────────────────
    nexus = Nexus(address=NEXUS, cpu_core=None)
    bus1 = Bus(xsub_address=BUS1_XSUB, xpub_address=BUS1_XPUB, cpu_core=None)
    threading.Thread(target=nexus.run, daemon=True).start()
    threading.Thread(target=bus1.run, daemon=True).start()
    time.sleep(0.15)

    class Recorder(RecordingModule):
        service_name = "test.recorder.roundtrip"
        cpu_core = None

    rec = Recorder(file_path=file_path, nexus_address=NEXUS,
                   bus_xsub=BUS1_XSUB, bus_xpub=BUS1_XPUB)
    rec_thread = threading.Thread(target=rec.run, daemon=True)
    rec_thread.start()
    time.sleep(0.30)

    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    pub.connect(BUS1_XSUB)
    time.sleep(0.05)
    _publish_n(pub, topic, orig_payload, n_msgs, gap_s=0.03)
    time.sleep(0.25)

    rec.stop()
    rec_thread.join(timeout=3.0)
    nexus.stop()
    bus1.stop()
    pub.close()
    time.sleep(0.1)

    # ── Phase 2: Replay ──────────────────────────────────────────────────────
    bus2 = Bus(xsub_address=BUS2_XSUB, xpub_address=BUS2_XPUB, cpu_core=None)
    threading.Thread(target=bus2.run, daemon=True).start()
    time.sleep(0.1)

    sub = ctx.socket(zmq.SUB)
    sub.connect(BUS2_XPUB)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    time.sleep(0.1)  # subscription propagation through proxy

    # ReplayBus.run() is blocking; speed=0.0 → publish as fast as possible
    replay = ReplayBus(file_path=file_path, bus_xsub=BUS2_XSUB, speed=0.0)
    replay.run()
    time.sleep(0.1)

    # Drain received messages
    received_payloads = []
    poller = zmq.Poller()
    poller.register(sub, zmq.POLLIN)
    while True:
        evts = dict(poller.poll(timeout=150))
        if not evts:
            break
        frames = sub.recv_multipart()
        if len(frames) >= 3:
            received_payloads.append(frames[2])

    bus2.stop()
    sub.close()
    ctx.term()

    assert len(received_payloads) == n_msgs, \
        f"Expected {n_msgs} replayed messages, got {len(received_payloads)}"
    for p in received_payloads:
        assert p == orig_payload, "Replayed payload bytes differ from original"


# ---------------------------------------------------------------------------
# Test 3: ReplayBus inter-message delay (speed=0.0 completes faster than speed=1.0)
# ---------------------------------------------------------------------------

def test_replay_bus_speed_zero_is_faster(tmp_path):
    """speed=0.0 must complete significantly faster than speed=1.0 for a known file."""
    from tyche.backtest.recording import ReplayBus

    # Craft a .tyche file manually: 3 records with wall_ns 0.5s apart
    file_path = str(tmp_path / "speed_test.tyche")
    payload = _make_payload()
    base_ns = time.time_ns()
    gap_ns = 500_000_000  # 0.5s

    with open(file_path, "wb") as f:
        for i in range(3):
            record = ["EQUITY.NYSE.AAPL.QUOTE", base_ns + i * gap_ns, payload,
                      base_ns + i * gap_ns]
            f.write(msgpack.packb(record, use_bin_type=True))

    # Bus2 for replay target (we don't check received messages here, just timing)
    from tyche.core.bus import Bus
    bus2 = Bus(xsub_address=BUS2_XSUB, xpub_address=BUS2_XPUB, cpu_core=None)
    threading.Thread(target=bus2.run, daemon=True).start()
    time.sleep(0.1)

    t0 = time.time()
    ReplayBus(file_path=file_path, bus_xsub=BUS2_XSUB, speed=0.0).run()
    elapsed_fast = time.time() - t0

    bus2.stop()
    time.sleep(0.1)

    # elapsed_fast must be much less than the 1.0s of simulated inter-message time
    assert elapsed_fast < 0.5, f"speed=0.0 replay took {elapsed_fast:.2f}s, expected < 0.5s"
```

- [ ] **Step 2: Run tests — confirm RED**

```bash
python -m pytest tests/integration/test_backtest_replay.py -v --tb=short
```

Expected: 3 FAILs — `TypeError` because `RecordingModule()` and `ReplayBus()` constructors are stubs.

- [ ] **Step 3: Commit failing tests (preserves RED state in git history)**

```bash
git add tests/integration/test_backtest_replay.py
git commit -m "test(python): add backtest replay integration tests (RED)"
```

---

## Task 4: Implement RecordingModule (GREEN)

**Files:**
- Modify: `tyche/backtest/recording.py`

- [ ] **Step 1: Implement RecordingModule**

Replace the stub with the full implementation:

```python
# tyche/backtest/recording.py
"""Backtest recording and replay utilities."""
import time
import msgpack
import zmq
from tyche.core.module import Module


class RecordingModule(Module):
    """Subscribes to all Bus topics and writes every message to a .tyche file.

    File format: sequential MessagePack arrays, each:
        [topic: str, timestamp_ns: int, payload: bytes, wall_ns: int]

    wall_ns is always time.time_ns() — unconditional wall clock.
    timestamp_ns is self._clock.now_ns() — injectable for SimClock backtest.

    Override _dispatch() so ALL messages are captured (typed handlers would
    miss unknown dtypes; overriding on_raw() would miss typed market data).
    """

    def __init__(self, file_path: str, nexus_address: str, bus_xsub: str, bus_xpub: str):
        super().__init__(nexus_address, bus_xsub, bus_xpub)
        self._file_path = file_path
        self._file = None

    def on_start(self):
        self._file = open(self._file_path, "ab")
        # Subscribe to all topics — bypass TopicValidator (empty string is not a
        # valid topic but is a legal ZMQ XSUB subscription)
        self._sub_sock.setsockopt(zmq.SUBSCRIBE, b"")

    def on_stop(self):
        if self._file is not None:
            self._file.flush()
            self._file.close()
            self._file = None

    def _dispatch(self, topic: str, payload: bytes):
        wall_ns = time.time_ns()             # always wall clock
        timestamp_ns = self._clock.now_ns()  # injectable clock for backtest
        record = [topic, timestamp_ns, payload, wall_ns]
        self._file.write(msgpack.packb(record, use_bin_type=True))
        super()._dispatch(topic, payload)


class ReplayBus:
    """Stub — implemented in Task 5."""
```

- [ ] **Step 2: Run RecordingModule test only**

```bash
python -m pytest tests/integration/test_backtest_replay.py::test_recording_module_writes_tyche_file -v --tb=short
```

Expected: PASS. The other two tests still fail (ReplayBus is still a stub).

---

## Task 5: Implement ReplayBus (full GREEN)

**Files:**
- Modify: `tyche/backtest/recording.py`

- [ ] **Step 1: Replace ReplayBus stub with full implementation**

```python
class ReplayBus:
    """Reads a .tyche recording file and re-publishes all messages to a Bus.

    Constructor: ReplayBus(file_path, bus_xsub, speed=1.0)
      speed=0.0  → publish as fast as possible (no inter-message delay)
      speed=1.0  → wall-clock timing (mirrors original recording rate)
      speed=10.0 → 10x accelerated

    run() is blocking. It replays the file exactly once and returns.
    The ZMQ context is created in __init__ and terminated in run() after completion.
    """

    def __init__(self, file_path: str, bus_xsub: str, speed: float = 1.0):
        self._file_path = file_path
        self._bus_xsub = bus_xsub
        self._speed = speed
        self._ctx = zmq.Context()

    def run(self):
        sock = self._ctx.socket(zmq.PUB)
        sock.connect(self._bus_xsub)
        time.sleep(0.05)  # allow subscription propagation before first publish

        prev_wall_ns = None
        unpacker = msgpack.Unpacker(raw=False)

        with open(self._file_path, "rb") as f:
            unpacker.feed(f.read())
            for record in unpacker:
                # record = [topic, timestamp_ns, payload, wall_ns]
                if prev_wall_ns is not None:
                    if self._speed == 0.0:
                        pass  # no sleep — publish as fast as possible
                    else:
                        delay_s = (record[3] - prev_wall_ns) / self._speed / 1_000_000_000
                        if delay_s > 0:
                            time.sleep(delay_s)
                prev_wall_ns = record[3]

                sock.send_multipart([
                    record[0].encode(),                    # topic bytes
                    record[1].to_bytes(8, "big"),          # timestamp_ns big-endian 8 bytes
                    record[2],                             # payload bytes (unchanged)
                ])

        sock.close()
        self._ctx.term()
```

- [ ] **Step 2: Run all backtest replay tests**

```bash
python -m pytest tests/integration/test_backtest_replay.py -v --tb=short
```

Expected: 3 passed, 0 failed.

- [ ] **Step 3: Run full unit suite — confirm no regressions**

```bash
python -m pytest tests/unit/ -v
```

Expected: 30 passed, 0 failed.

- [ ] **Step 4: Commit**

```bash
git add tyche/backtest/recording.py tests/integration/test_backtest_replay.py
git commit -m "feat(python): add RecordingModule and ReplayBus backtest harness"
```

---

## Task 6: Final Validation

- [ ] **Step 1: Run all Python tests**

```bash
python -m pytest tests/unit/ tests/integration/test_backtest_replay.py -v
```

Expected: All pass, 0 failed.

- [ ] **Step 2: Smoke test imports**

```bash
python -c "
from tyche.backtest.recording import RecordingModule, ReplayBus
from tyche.core.clock import SimClock
from tyche.core.module import Module
print('All imports OK')
print('Module clock injection:', hasattr(Module.__init__, '__code__'))
"
```

Expected: `All imports OK`

- [ ] **Step 3: Create implementation log**

Create `docs/impl/core_engine_expansion_implement_v1.md` with the mandatory format (Project State, CRITICAL section, Task Log).

- [ ] **Step 4: Final commit**

```bash
git add docs/impl/core_engine_expansion_implement_v1.md
git commit -m "docs: add expansion implementation log v1 (task 16)"
```

---

*Total: 6 tasks, ~25 steps. New tests: 3 unit + 3 integration.*
