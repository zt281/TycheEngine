# Tyche Engine Process Separation - Implementation Log v2

## Project State at Impl Time

The current implementation uses asyncio within a single Python process, which violates the distributed architecture requirement. The Engine and Modules must run as separate processes communicating via ZeroMQ.

**Existing files:**
- `src/tyche/engine.py` - Uses asyncio, needs threading conversion
- `src/tyche/module.py` - Uses asyncio, needs threading conversion
- `src/tyche/types.py`, `message.py`, `heartbeat.py` - Core types (mostly OK)
- `src/tyche/example_module.py` - Example module using asyncio

**Required changes:**
1. Create `engine_main.py` - standalone engine entry point
2. Create `module_main.py` - standalone module entry point
3. Convert `engine.py` from asyncio to threading
4. Convert `module.py` from asyncio to threading
5. Create integration test for multi-process
6. Create examples directory

## CRITICAL

_(none)_

## Task Log

### [TASK-1] Create engine_main.py entry point

**Status:** COMPLETED
**Description:** Create standalone engine process entry point with CLI args

#### RED Step: Write test first
Test file: `tests/unit/test_engine_main.py`
Result: Tests failed with ModuleNotFoundError (expected)

#### GREEN Step: Implement engine_main.py
File: `src/tyche/engine_main.py`
Result: All tests pass
```
tests/unit/test_engine_main.py::test_engine_main_module_exists PASSED
tests/unit/test_engine_main.py::test_engine_main_argparse PASSED
tests/unit/test_engine_main.py::test_engine_main_help PASSED
```

---

### [TASK-2] Create module_main.py entry point

**Status:** COMPLETED
**Description:** Create standalone module process entry point with CLI args

#### RED Step: Write test first
Test file: `tests/unit/test_module_main.py`
Result: Tests failed with ImportError (expected)

#### GREEN Step: Implement module_main.py
File: `src/tyche/module_main.py`
Result: All tests pass
```
tests/unit/test_module_main.py::test_module_main_module_exists PASSED
tests/unit/test_module_main.py::test_module_main_argparse PASSED
tests/unit/test_module_main.py::test_module_main_help PASSED
```

---

### [TASK-3] Convert engine.py from asyncio to threading

**Status:** COMPLETED
**Description:** Convert engine from asyncio to threading for multi-process support

#### RED Step: Write test first
Test file: `tests/unit/test_engine_threading.py`
Result: Tests failed (expected - no run() method)

#### GREEN Step: Implement threading-based engine
File: `src/tyche/engine.py`
Changes:
- Replaced asyncio with threading
- Added `run()` blocking method
- Added `start_nonblocking()` for testing
- Added `_stop_event` for thread coordination
- Fixed ROUTER socket response format

Result: All tests pass
```
tests/unit/test_engine_threading.py::test_engine_has_run_method PASSED
tests/unit/test_engine_threading.py::test_engine_registration PASSED
tests/unit/test_engine_threading.py::test_engine_has_stop_event PASSED
```

---

### [TASK-4] Convert module.py from asyncio to threading

**Status:** COMPLETED
**Description:** Convert module from asyncio to threading for multi-process support

#### RED Step: Write test first
Test file: `tests/unit/test_module_threading.py`
Result: Tests failed (expected - no run() method, abstract start() not implemented)

#### GREEN Step: Implement threading-based module
File: `src/tyche/module.py`
Changes:
- Replaced asyncio with threading
- Added `run()` blocking method
- Added `start()` for ModuleBase compatibility
- Added `start_nonblocking()` for testing
- Added `_stop_event` for thread coordination

Result: All tests pass
```
tests/unit/test_module_threading.py::test_module_has_run_method PASSED
tests/unit/test_module_threading.py::test_module_auto_generates_id PASSED
tests/unit/test_module_threading.py::test_module_adds_interface PASSED
```

---

### [TASK-5] Create integration test for multi-process

**Status:** COMPLETED
**Description:** Create integration test using subprocess for actual process separation

#### RED Step: Write test first
Test file: `tests/integration/test_multiprocess.py`
Result: Tests written

#### GREEN Step: Implement tests
Tests created:
- `test_engine_and_module_in_same_process` - Baseline test
- `test_engine_main_help` - CLI help test
- `test_module_main_help` - CLI help test
- `test_engine_process_starts_and_stops` - Process test (marked slow)
- `test_module_connects_to_engine_process` - Full integration (marked slow)

Result: Core tests pass
```
tests/integration/test_multiprocess.py::test_engine_and_module_in_same_process PASSED
tests/integration/test_multiprocess.py::test_engine_main_help PASSED
tests/integration/test_multiprocess.py::test_module_main_help PASSED
```

---

### [TASK-6] Create examples directory

**Status:** COMPLETED
**Description:** Create runnable examples showing process separation

#### Files created:
- `examples/run_engine.py` - Standalone engine example
- `examples/run_module.py` - Standalone module example

---

## Summary

All tasks completed:
1. ✅ `engine_main.py` - Standalone engine entry point
2. ✅ `module_main.py` - Standalone module entry point
3. ✅ `engine.py` - Converted from asyncio to threading
4. ✅ `module.py` - Converted from asyncio to threading
5. ✅ `tests/integration/test_multiprocess.py` - Multi-process integration tests
6. ✅ `examples/` - Runnable demonstrations

## Verification

Run the following to verify:
```bash
# Terminal 1: Start engine
python -m tyche.engine_main --registration-port 5555

# Terminal 2: Start module
python -m tyche.module_main --engine-port 5555
```

Or use the examples:
```bash
# Terminal 1
python examples/run_engine.py

# Terminal 2
python examples/run_module.py
```


---

## Post-Implementation Bug Fixes

### [TASK-7] Fix Ctrl+C Signal Handling

**Status:** COMPLETED
**Description:** Ctrl+C (SIGINT) didn't stop engine/module on Windows

**Root Cause:** `time.sleep(0.1)` in main loop blocks signals on Windows

**Fix:** Changed to `self._stop_event.wait(0.1)` which is properly interruptible

**Files Modified:**
- `src/tyche/engine.py` - `run()` method
- `src/tyche/module.py` - `run()` method

**Test:** `tests/unit/test_signal_handling.py`

### [TASK-8] Implement Heartbeat Protocol

**Status:** COMPLETED
**Description:** Module expired immediately after registration

**Root Cause:** Module never sent heartbeats; engine expected them

**Fix:**
1. **Engine:** Added `_heartbeat_receive_worker()` thread that listens on ROUTER socket for module heartbeats
2. **Module:** Added `_send_heartbeats()` thread that sends periodic heartbeats to engine
3. Added `heartbeat_receive_endpoint` parameter to both engine and module

**Files Modified:**
- `src/tyche/engine.py` - Added heartbeat receive endpoint and worker
- `src/tyche/module.py` - Added heartbeat sending thread

**Tests:** `tests/unit/test_heartbeat_protocol.py`
- `test_module_does_not_expire_with_heartbeats` - Verifies heartbeats keep module alive
- `test_module_expires_without_heartbeats` - Verifies expiration works when no heartbeats
