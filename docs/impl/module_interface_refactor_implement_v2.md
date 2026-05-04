# Module Interface Refactor - Implementation Log v2

## Project State at Impl Time

- Plan `module_interface_refactor_plan_v2.md` APPROVED at commit `c8329a8`.
- Baseline: 403 passed, 3 warnings.
- Branch: `refactor/base_module`.
- Task 0 decision: Option A — implement reverse channel for `handle_*` request-response.

## CRITICAL

_(none)_

## Plan Amendments

### [AMEND-1] Increase ZMQ HWM for perf tests
**Date:** 2026-05-02
**Approved by:** team lead (user)
**Amendment:** Add `zmq.SNDHWM=10000` and `zmq.RCVHWM=10000` to engine XPUB/XSUB proxy sockets and module PUB/SUB sockets.
**Reason:** `test_message_queue_perf.py::test_single_sender_single_receiver_throughput` was consistently failing with exactly 4000/5000 messages received. Root cause: default ZMQ HWM=1000 causes PUB to drop messages when receiver cannot keep up. Plan v1 baseline already noted "1 flaky perf failure"; the HWM increase stabilizes it.
**Files touched:** `src/tyche/engine.py`, `src/tyche/module.py`

## Design Gaps Surfaced

_(none)_

## Task Log

### Task 1: Reconcile ModuleBase — ABC vs Protocol (1a)
**Status:** GREEN

**RED:** `pytest tests/unit/test_module_base.py -v` fails after switching `ModuleBase` from `ABC` to `typing.Protocol` + `@runtime_checkable`. Tests reference `__abstractmethods__` and expect ABC behavior.

**Changes:**
- `src/tyche/module_base.py`: `ABC` → `Protocol` + `@runtime_checkable`
- `tests/unit/test_module_base.py`: Replace `__abstractmethods__` assertions with `__protocol_attrs__`. Add `test_protocol_structural_subtyping` and `test_protocol_rejects_incomplete_class`.

**GREEN:** `pytest tests/unit/test_module_base.py tests/unit/test_module.py -v` → 14 passed.

---

### Task 5: API Cleanup — `start` / `run` / `heartbeat_endpoint`
**Status:** GREEN

**RED:** `grep -r "start_nonblocking" src/tyche/module.py` and `grep heartbeat_endpoint src/tyche/module.py` both return hits. `start()` aliases blocking `run()`, violating `ModuleBase` contract.

**Changes:**
- `src/tyche/module.py`: Remove `heartbeat_endpoint` param/attribute. `start()` non-blocking (calls `_start_workers`). `run()` blocking (`start(); _stop_event.wait()`). Remove `start_nonblocking()`.
- `src/modules/trading/clock/clock.py`: Override `start()` instead of `start_nonblocking()`.
- `tests/unit/test_module.py`: Add `test_start_does_not_block`.
- `tests/integration/test_engine_module.py`, `test_message_queue_perf.py`, `test_multiprocess.py`, `test_heartbeat_protocol.py`: Replace `module.start_nonblocking()` with `module.start()`.

**GREEN:** `pytest tests/unit/test_module.py tests/unit/test_module_base.py tests/integration/test_engine_module.py tests/integration/test_multiprocess.py -v` → 24 passed.

---

### Task 2: Wire Dynamic `_register_handler` to SUB Subscription
**Status:** GREEN

**RED:** New test `test_dynamic_register_subscribes_topic` fails — handler registered post-start never receives events because SUB socket was not subscribed to the new topic.

**Changes:**
- `src/tyche/module.py`: `_register_handler` now checks `if self._sub_socket is not None` and calls `setsockopt(zmq.SUBSCRIBE, name.encode())`.

**GREEN:** `pytest tests/unit/test_module.py::test_dynamic_register_subscribes_topic -v` → 1 passed.

---

### Task 4a: Engine ACK Worker
**Status:** GREEN

**Changes:**
- `src/tyche/types.py`: Add `RESPONSE` to `MessageType`.
- `src/tyche/engine.py`:
  - Add `_ack_correlations: Dict[str, bytes]` + `_ack_lock`.
  - `_ack_worker` thread binds ROUTER on `ack_endpoint`, connects internal PUB to `event_sub_endpoint`.
  - On `COMMAND`: records `correlation_id → identity`, broadcasts request via PUB.
  - On `RESPONSE`: looks up `correlation_id`, forwards reply to caller's identity via ROUTER.
  - `_process_registration` ACK payload now includes `ack_port`.

**GREEN:** Verified via integration test (Task 4b).

---

### Task 4b: Module DEALER Socket + `send_event_with_response`
**Status:** GREEN

**RED:** First attempt used `recv()` on DEALER socket — received empty delimiter frame instead of payload. `msgpack.unpackb` failed with "incomplete input".

**Fix:** Changed to `recv_multipart()` and extracted last frame.

**Changes:**
- `src/tyche/module.py`:
  - `_register` stores `ack_port` from engine ACK.
  - `_start_workers` creates `_ack_socket` (DEALER) connected to `ack_endpoint`.
  - `_event_receiver`: ignores self-sent messages (`msg.sender == module_id`). On non-None dispatch result, sends `RESPONSE` via `_ack_socket` with `correlation_id`.
  - New `send_event_with_response(event, payload, timeout_ms)`: generates `correlation_id`, sends `COMMAND` via DEALER, awaits `RESPONSE`.

**GREEN:** `pytest tests/integration/test_handle_response.py -v` → 1 passed.

---

### Task 3: Resolve `call_ack` Fate
**Status:** GREEN

**Changes:**
- `src/tyche/module.py`: `call_ack` rewritten as thin wrapper around `send_event_with_response`. Old REQ-to-engine dead code removed.

**GREEN:** Verified via integration test (Task 4b). No `call_ack` callers in `tests/` needed updating.

---

### Task 6: Robustness — Locking and Explicit Error Returns
**Status:** GREEN

**Changes:**
- `src/tyche/module.py`:
  - Add `self._handlers_lock = threading.RLock()`.
  - `_register_handler`, `_subscribe_to_interfaces`, `_dispatch` all acquire lock.
  - `_dispatch` for `handle_*` topics on exception returns `{"error": str(e), "type": type(e).__name__}` instead of `None`.
- `tests/unit/test_module.py`:
  - `test_dispatch_handle_error_returns_error_dict`
  - `test_concurrent_register_and_dispatch`

**GREEN:** `pytest tests/unit/test_module.py::test_dispatch_handle_error_returns_error_dict tests/unit/test_module.py::test_concurrent_register_and_dispatch -v` → 2 passed.

---

### Verification (Full Suite)
```bash
pytest tests/ -q --ignore=tests/integration/test_clickhouse_backend.py
=> 410 passed, 3 warnings (pre-existing)
```

All Plan v2 tasks complete. No regressions.
