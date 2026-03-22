# Core Engine Expansion — Implementation Log v1

**Plan:** `docs/plan/core_engine_expansion_plan_v1.md` (commit `2878693`)
**Plan review:** `docs/review/core_engine_expansion_plan_review_v1.log` — Result: APPROVED
**Branch:** `core-engine/task-16-backtest-harness`

---

## Project State at Impl Time

Tasks 1-15 of the core engine are complete (committed to main, impl log v1 at `2c2369d`).
This log covers the Task 16 expansion: clock injection into Module and the backtest
recording/replay harness. All source files existed; only new tests and new modules were added.

---

## CRITICAL

_(none)_

---

## Task Log

### Task 1 — Module clock injection

**RED** (commit `6051386`):
- Created `tests/unit/test_module_clock.py` with 3 tests:
  - `test_module_defaults_to_live_clock`
  - `test_module_accepts_sim_clock`
  - `test_module_clock_is_keyword_only`
- Run: `python -m pytest tests/unit/test_module_clock.py -v`
- Result: 3 FAILED (AttributeError: Module has no `_clock`)

**GREEN** (commit `6051386`):
- Added `from tyche.core.clock import LiveClock` import to `tyche/core/module.py`
- Changed `__init__` signature to add `*, clock=None` keyword-only parameter
- Added `self._clock = clock if clock is not None else LiveClock()` as last line of `__init__`
- Heartbeat logic left untouched (`time.time()` only)
- Run: `python -m pytest tests/unit/test_module_clock.py -v`
- Result: 3 PASSED

**Quality fix** (commit `45ab31e`):
- Code quality reviewer: unused `from abc import ABC` in test file (F401)
- Fix: import was already absent in the committed file — no-op fix, confirmed clean

---

### Task 2 — Backtest package skeleton

**GREEN** (commit `3dabc38`):
- Created `tyche/backtest/__init__.py` (empty)
- Created `tyche/backtest/recording.py` (stub with class stubs, no implementation)
- Run: `python -c "from tyche.backtest.recording import RecordingModule, ReplayBus"`
- Result: ImportError — expected (stubs only, no logic yet)

---

### Task 3 — Integration tests (RED)

**RED** (commit `fb5c571`):
- Created `tests/integration/test_backtest_replay.py` with 3 tests:
  - `test_recording_module_writes_tyche_file` — verifies .tyche file is written with correct schema
  - `test_record_replay_roundtrip` — full record→replay cycle, payload bytes must be equal
  - `test_replay_bus_speed_zero_is_faster` — speed=0.0 completes in < 0.5s for 3×0.5s-spaced records
- Port assignments: Test1: 35555-35557, Test2: 35560-35564, Test3: 35565-35566 (each isolated)
- Run: `python -m pytest tests/integration/test_backtest_replay.py -v`
- Result: 3 FAILED (ImportError / NotImplementedError from stubs)

---

### Task 4 — RecordingModule (GREEN)

**GREEN** (commit `87a201f`):
- Implemented `RecordingModule` in `tyche/backtest/recording.py`:
  - `__init__`: stores `file_path`, passes remaining args to `super().__init__`
  - `on_start`: opens file in append-binary mode; subscribes to all topics via `zmq.SUBSCRIBE, b""`
  - `on_stop`: flushes and closes file
  - `_dispatch`: records `[topic, timestamp_ns, payload, wall_ns]` as MessagePack, then calls `super()._dispatch`
- Run: `python -m pytest tests/integration/test_backtest_replay.py::test_recording_module_writes_tyche_file -v`
- Result: PASSED

**Quality fixes** (incorporated into `87a201f`):
- Added `if self._file is None: return` guard at top of `_dispatch` (crash if called before `on_start`)
- Wrapped `msgpack.packb` + file write in `try/except OSError` with `self._log.error` (disk-full safety)

---

### Task 5 — ReplayBus (GREEN)

**GREEN** (commit `3dfa6c5`):
- Implemented `ReplayBus` in `tyche/backtest/recording.py`:
  - Plain class (not Module subclass)
  - `__init__`: stores params, creates `zmq.Context()`
  - `run()`: creates PUB socket, connects to `bus_xsub`, sleeps 50ms, then streams the .tyche file
    using `msgpack.Unpacker(f, raw=False)`, applies inter-message delay based on `wall_ns` diff
    and `speed`, re-publishes each record as 3-frame multipart
  - Closes socket and terminates context in `finally` block
- Port reuse fix: each integration test given its own port range (35555-35557, 35560-35564, 35565-35566)
- Run: `python -m pytest tests/integration/test_backtest_replay.py -v`
- Result: 3 PASSED

**Quality fixes** (commit `8500d0d`):
- Code quality reviewer found 3 issues (all Important/Critical):
  1. Resource leak: no `try/finally` → socket/context leaked on exception → **fixed**
  2. `unpacker.feed(f.read())` loads entire file into RAM → use `Unpacker(f)` streaming → **fixed**
  3. `to_bytes(8, "big")` with no `signed` → OverflowError on negative timestamp_ns → added `signed=True` → **fixed**
  4. No validation of `speed < 0.0` → silent "publish as fast as possible" → added `ValueError` → **fixed**
- Re-run after fixes: 3 PASSED

---

## Verification

### Unit tests

```
python -m pytest tests/unit/ -v
30 passed, 1 warning in 0.12s
```

### Integration tests

```
python -m pytest tests/integration/ -v
```

Results:
- `test_backtest_replay.py::test_recording_module_writes_tyche_file` PASSED
- `test_backtest_replay.py::test_record_replay_roundtrip` PASSED
- `test_backtest_replay.py::test_replay_bus_speed_zero_is_faster` PASSED
- `test_bus_pubsub.py::test_bus_forwards_published_message` PASSED
- `test_bus_pubsub.py::test_bus_topic_filtering` PASSED
- `test_module_e2e.py::test_module_registers_with_nexus` PASSED
- `test_module_e2e.py::test_module_receives_typed_quote` FAILED ← **pre-existing** (see note)
- `test_module_e2e.py::test_module_receives_typed_bar` PASSED
- `test_nexus_lifecycle.py::test_nexus_registration` PASSED
- `test_nexus_lifecycle.py::test_nexus_heartbeat` PASSED
- `test_nexus_lifecycle.py::test_nexus_stop_command` PASSED

10 passed, 1 failed (pre-existing)

**Note on pre-existing failure:** `test_module_receives_typed_quote` has a port-reuse race
condition when run sequentially with other integration tests. This is documented in impl log v1
(`2c2369d`) under the Task 15 notes and is not related to Task 16 work. It passes when run in
isolation. No new failures were introduced by this branch.

---

## Commits

| Hash | Description |
|------|-------------|
| `2878693` | docs: add expansion plan v1 and plan review log (Task 16, APPROVED) |
| `6051386` | feat(python): add clock injection to Module.__init__ (Task 1) |
| `45ab31e` | fix(tests): remove unused ABC import in test_module_clock |
| `3dabc38` | feat(python): add backtest package skeleton (Task 2) |
| `fb5c571` | test(python): add backtest replay integration tests (RED, Task 3) |
| `87a201f` | feat(python): implement RecordingModule (Task 4) |
| `3dfa6c5` | feat(python): implement ReplayBus; isolate integration test ports (Task 5) |
| `8500d0d` | fix(python): harden ReplayBus against resource leaks and edge cases |
