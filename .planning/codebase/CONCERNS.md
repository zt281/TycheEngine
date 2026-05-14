# Codebase Concerns

**Analysis Date:** 2026-05-14

## Tech Debt

### Uncommitted Working Tree Changes (CRITICAL)
- **Issue:** 41 files with 7,186 lines deleted from working tree, including all 37 test files, `engine_main.py`, and `conftest.py`. Only `src/tyche/cpp/types.h`, `src/tyche/engine.py`, and `src/tyche/types.py` have minor edits (removal of `Endpoint` field from `ModuleInfo`).
- **Files:** `tests/unit/*.py`, `tests/integration/*.py`, `tests/conftest.py`, `src/tyche/engine_main.py`
- **Impact:** Zero test coverage in working tree. CI will fail. Cannot run `pytest`. The deleted tests cover engine threading, message serialization, heartbeat protocol, job routing, trading pipeline, CTP gateway, persistence backends, and more.
- **Fix approach:** Either commit the deletions intentionally (with a plan to rewrite tests) or restore the test files immediately. The deletions appear accidental or part of an incomplete refactor.

### Cross-Language Type Drift (CRITICAL)
- **Issue:** `InterfacePattern` enum has 4 variants in Python (`ON`, `SEND`, `HANDLE`, `REQUEST`) but only 2 in C++ (`ON`, `SEND`) and only 2 in Rust (`On`, `Send`). The C++ `interface_pattern_to_str` only handles `ON` and `SEND`, missing `HANDLE` and `REQUEST`. Similarly, `MessageType` has 7 variants in Python but only 6 in C++ (missing `REQUEST`).
- **Files:** `src/tyche/types.py`, `src/tyche/cpp/types.h`, `src/tyche/rust/src/types.rs`
- **Impact:** C++ and Rust modules cannot register `handle_*` or `request_*` interfaces. Job routing (request/response pattern) is unsupported in C++ and Rust. Message deserialization may fail for `REQUEST` type messages in C++.
- **Fix approach:** Synchronize enums across all three languages. Add `HANDLE` and `REQUEST` to C++ `InterfacePattern`, add `REQUEST` to C++ `MessageType`, add `Handle` and `Request` to Rust `InterfacePattern`, add `Request` to Rust `MessageType`.

### Stale C++ `ModuleInfo` Struct
- **Issue:** C++ `ModuleInfo` still declares an `Endpoint endpoint` field that was removed from Python `ModuleInfo` in the working tree changes. The git diff shows this field was removed from Python but the C++ header still has it.
- **Files:** `src/tyche/cpp/types.h` (line 177 in HEAD)
- **Impact:** C++ code referencing `ModuleInfo.endpoint` will not compile against the current Python wire protocol. Registration payloads from Python no longer include endpoint.
- **Fix approach:** Remove `Endpoint endpoint` from C++ `ModuleInfo` struct to match Python.

### No PyBind11 / Cython Bindings for C++ Module
- **Issue:** The C++ `TycheModule` implementation (`src/tyche/cpp/module.cpp`, `src/tyche/cpp/module.h`) is a standalone library with no Python bindings. The test `tests/unit/test_cpp_example_module.py` expects `from cpp_module.example import CppExampleModule`, but no binding code exists in the repo.
- **Files:** `src/tyche/cpp/module.cpp`, `src/tyche/cpp/module.h`, `tests/unit/test_cpp_example_module.py`
- **Impact:** C++ module cannot be used from Python. The test is skipped at import time. The C++ code is effectively dead code until bindings are written.
- **Fix approach:** Add pybind11 binding layer (e.g., `src/tyche/cpp/bindings.cpp`) or a `setup.py`/`pyproject.toml` build extension configuration. The `third_party/pybind11` submodule is already present.

### Rust Crate Has No Python Bindings
- **Issue:** The Rust `tyche` crate (`src/tyche/rust/`) provides `TycheModuleBase` but no Python bindings. The test `tests/unit/test_rust_example_module.py` expects `from rust_module.example import RustExampleModule`, which does not exist.
- **Files:** `src/tyche/rust/src/`, `tests/unit/test_rust_example_module.py`
- **Impact:** Rust module cannot be used from Python. The test is skipped at import time.
- **Fix approach:** Add PyO3 or maturin-based Python bindings for the Rust crate.

## Known Bugs

### Job Router Memory Leak on Stale Responses
- **Issue:** `_pending_jobs` dictionary in `TycheEngine` stores `correlation_id -> requester_identity` mappings. If a handler never responds (e.g., crashes), the entry is never removed. There is no TTL or cleanup for pending jobs.
- **Files:** `src/tyche/engine.py` (lines 185, 781, 809, 834)
- **Trigger:** Send a job request to a handler that crashes or disconnects mid-processing. The requester times out, but the engine still holds the mapping.
- **Workaround:** Restart the engine to clear `_pending_jobs`.
- **Fix approach:** Add a TTL (e.g., 30 seconds) to pending job entries. Clean up expired entries in `_monitor_worker` or `_job_router_worker`.

### TopicQueue `popleft` Uses `pop(0)` (O(n))
- **Issue:** `TopicQueue.popleft()` calls `self._items.pop(0)`, which is O(n) for Python lists. This is used in the hot-path backpressure logic (`_enqueue_from_xsub`).
- **Files:** `src/tyche/engine.py` (line 55)
- **Impact:** Under high load with deep queues, dropping oldest messages becomes linear in queue depth, causing latency spikes.
- **Fix approach:** Replace the list with `collections.deque` for O(1) pops from both ends.

### `TrackedQueue.put` Silently Drops on Full
- **Issue:** `TrackedQueue.put` catches `queue.Full` and increments `dropped` but does not notify the caller. The caller has no way to know the message was lost.
- **Files:** `src/tyche/engine.py` (lines 72-77)
- **Impact:** Messages (e.g., registrations, heartbeats) can be silently dropped during overload. For a trading engine, silent message loss is unacceptable.
- **Fix approach:** Return a boolean from `put` indicating success/drop, or raise a custom exception. At minimum, log at WARNING level when a message is dropped.

### Heartbeat Receive Worker Swallows All Deserialization Errors
- **Issue:** `except Exception: pass` on line 639 of `engine.py` silently drops malformed heartbeats. This could mask wire protocol bugs or corruption.
- **Files:** `src/tyche/engine.py` (line 639)
- **Impact:** Debugging heartbeat issues is impossible. A module sending malformed heartbeats will never be diagnosed.
- **Fix approach:** Log at DEBUG or WARNING level when heartbeat deserialization fails, including the raw frame bytes (truncated).

### C++ Event Receiver Swallows All Exceptions
- **Issue:** `catch (...) { // Swallow unexpected exceptions in receiver loop }` in `module.cpp` (line 565) silently drops all exceptions in the event receiver thread.
- **Files:** `src/tyche/cpp/module.cpp` (line 565)
- **Impact:** Handler crashes, memory corruption, or ZMQ errors are completely invisible.
- **Fix approach:** Log exceptions before swallowing them. Consider terminating the module if the receiver thread crashes repeatedly.

## Security Considerations

### No Authentication on ZMQ Sockets
- **Issue:** All ZMQ sockets (ROUTER, DEALER, PUB, SUB, XPUB, XSUB) bind/connect without any authentication (no CURVE, no plain auth). Any process on the network can connect to the engine.
- **Files:** `src/tyche/engine.py`, `src/tyche/module.py`, `src/tyche/cpp/module.cpp`, `src/tyche/rust/src/module.rs`
- **Risk:** Unauthorized modules can register, publish events, or intercept traffic. In a trading context, this could lead to order injection or information leakage.
- **Current mitigation:** None.
- **Recommendations:** Implement ZMQ CURVE encryption and authentication. Add a shared secret or certificate-based auth to the registration handshake.

### CTP Gateway Passwords in Plain Text
- **Issue:** `CtpLiveGateway` and `CtpSimGateway` store passwords as plain strings in instance attributes (`_password`).
- **Files:** `tests/unit/test_ctp_gateway.py` (tests confirm this), `tests/unit/test_ctp_config.py`
- **Risk:** Passwords may be exposed in memory dumps, logs, or stack traces.
- **Current mitigation:** None.
- **Recommendations:** Use a secure credential store or environment variables. At minimum, do not retain passwords in instance attributes after connection.

### Admin Socket Has No Authorization
- **Issue:** The admin ROUTER socket (`_admin_worker`) accepts any query without authentication or authorization.
- **Files:** `src/tyche/engine.py` (lines 836-857)
- **Risk:** Any process that can reach the admin port can query engine state, module lists, and queue statistics.
- **Recommendations:** Add an auth token check to admin queries, or bind admin to localhost only by default.

### Rust `unwrap()` in Serialization Hot Path
- **Issue:** `serialize_message` in Rust uses `.expect("Failed to serialize message")` which will panic on serialization failure.
- **Files:** `src/tyche/rust/src/message.rs` (line 9)
- **Risk:** A malformed message can crash a Rust module entirely.
- **Recommendations:** Return `Result<Vec<u8>, Error>` instead of panicking.

## Performance Bottlenecks

### Event Proxy Hot Path Copies Through Python
- **Issue:** The event proxy worker (`_event_proxy_worker`) receives frames from XSUB, passes them through `_enqueue_from_xsub` (which may call `popleft()` O(n)), then the egress worker dequeues and sends to XPUB. The "fast path" comment says it bypasses queues, but the actual implementation always enqueues.
- **Files:** `src/tyche/engine.py` (lines 444-575)
- **Cause:** Every event goes through Python list operations, dict lookups, and lock acquisitions.
- **Improvement path:** Use `zmq.proxy()` for the true hot path (direct XSUB->XPUB forwarding) and only tap into the topic queues for persistence/backpressure monitoring.

### Egress Worker Wakeup Queue Can Grow Unbounded
- **Issue:** `_egress_wakeup` is a standard `queue.Queue` with no size limit. Every message enqueued to a topic queue also puts a sentinel into `_egress_wakeup`. Under high load, the wakeup queue can grow much larger than the topic queues themselves.
- **Files:** `src/tyche/engine.py` (lines 171, 530, 540, 551)
- **Improvement path:** Use a bounded queue for `_egress_wakeup`, or coalesce wakeups (e.g., only put if queue was empty).

### Heartbeat Queue Can Grow Unbounded
- **Issue:** `_heartbeat_queue` is a `TrackedQueue(maxsize=10000)` but `put` silently drops on full. If the heartbeat worker is slow, heartbeats are lost.
- **Files:** `src/tyche/engine.py` (line 166)
- **Improvement path:** Monitor heartbeat drop rate. Consider a dedicated high-priority queue for heartbeats.

### Python GIL Contention on Engine
- **Issue:** `TycheEngine` spawns 9 daemon threads all competing for the Python GIL. The event proxy and job router threads do ZMQ I/O which releases the GIL, but the registration and admin workers do significant Python work under locks.
- **Files:** `src/tyche/engine.py` (lines 211-243)
- **Improvement path:** Profile under load. Consider moving the event proxy to a separate process or using `zmq.proxy()` in a background thread.

## Fragile Areas

### Thread Join Timeout Too Short
- **Issue:** `stop()` methods use `t.join(timeout=2.0)` for all worker threads. If a thread is blocked on ZMQ I/O or a slow handler, 2 seconds may not be enough for graceful shutdown.
- **Files:** `src/tyche/engine.py` (line 254), `src/tyche/module.py` (line 284)
- **Why fragile:** Threads may still be running after `stop()` returns, leading to use-after-free of ZMQ contexts or sockets.
- **Safe modification:** Increase timeout or check `is_alive()` after join and log warnings.

### `_event_breakdown` Logic Is Broken
- **Issue:** `TycheModule._event_breakdown("on_broadcasted_ping")` returns `("broadcasted_ping", "ping")` which is used nowhere. The actual dispatch logic strips the prefix directly (`topic[3:]`). The method appears to be dead code.
- **Files:** `src/tyche/module.py` (lines 121-125)
- **Why fragile:** Dead code adds confusion. Tests assert its behavior, locking in an unused implementation.
- **Safe modification:** Remove `_event_breakdown` and update tests.

### Module Registration Is Fire-and-Forget (No Retry)
- **Issue:** `_register()` in `TycheModule` tries once and returns `False` on failure. There is no retry logic. If the engine is temporarily unavailable during module startup, the module fails permanently.
- **Files:** `src/tyche/module.py` (lines 303-358)
- **Why fragile:** Race conditions during startup (engine not fully bound yet) cause module startup failures.
- **Safe modification:** Add exponential backoff retry (3-5 attempts) with logging.

### Rust Module Base Has No Job Socket Support
- **Issue:** The Rust `TycheModuleBase` only creates PUB, SUB, and HEARTBEAT sockets. It does not create a DEALER socket for job request/response, so Rust modules cannot participate in job routing.
- **Files:** `src/tyche/rust/src/module.rs` (lines 93-138)
- **Why fragile:** This is a feature gap, not a bug, but it means Rust modules have strictly less capability than Python modules.
- **Safe modification:** Add job socket creation and `request_event` / job receiver loop to Rust module base.

## Scaling Limits

### Single-Process Engine
- **Current capacity:** One Python process with 9 threads. The GIL limits true parallelism.
- **Limit:** CPU-bound work in handlers or admin queries will stall the event proxy.
- **Scaling path:** Split engine into multiple processes (e.g., separate process for event proxy, separate for job router). Consider rewriting the hot path in Rust or C++.

### Topic Queue Memory Usage
- **Current capacity:** Default 10,000 items per topic queue. Each item is a list of byte frames.
- **Limit:** At high message rates with large payloads, memory usage can grow unbounded across many topics.
- **Scaling path:** Add per-topic memory limits (bytes, not just item count). Implement spill-to-disk for overflow.

## Dependencies at Risk

### `pyzmq` Version Compatibility
- **Risk:** The codebase uses `zmq.Socket` typing and `zmq.Poller` patterns that may change in future pyzmq versions. The `zmq.error.Again` exception handling is version-dependent.
- **Impact:** Upgrade to pyzmq 26+ may break timeout handling or socket options.
- **Migration plan:** Pin pyzmq version in `pyproject.toml` and test before upgrading.

### `msgpack` Decimal Serialization
- **Risk:** Custom `_encode_decimal` / `_decode_decimal` hooks rely on msgpack's `default` and `object_hook` APIs. These are stable but the `use_bin_type=True` flag behavior changed in msgpack 1.0.
- **Impact:** Decimal precision loss or deserialization failure on msgpack upgrade.
- **Migration plan:** Add property tests for Decimal round-trips (mentioned in CLAUDE.md but not implemented in working tree).

## Missing Critical Features

### Persistence Is a No-Op
- **Problem:** `DurabilityLevel` enum exists (`BEST_EFFORT`, `ASYNC_FLUSH`, `SYNC_FLUSH`) but the engine does not implement any persistence logic. The `SYNC_FLUSH` and `ASYNC_FLUSH` levels are treated identically to `BEST_EFFORT`.
- **Blocks:** Event replay, audit trails, crash recovery.
- **Files:** `src/tyche/engine.py`, `src/tyche/types.py`

### No Event Replay / Recovery
- **Problem:** There is no mechanism to replay events from persistence after an engine restart. The `JsonlBackend` and `ClickHouseBackend` exist in tests but are not wired into the engine.
- **Blocks:** Stateful module recovery after crash.

### No Rate Limiting on Event Publishing
- **Problem:** Modules can publish events as fast as they want. A misbehaving module can overwhelm the engine's XSUB socket and cause backpressure drops for all modules.
- **Blocks:** Fair resource sharing between modules.

### No Module Isolation
- **Problem:** All modules share the same ZMQ context and the same Python process. A crashing module handler can bring down the entire engine.
- **Blocks:** Production deployment with untrusted module code.

## Test Coverage Gaps

### All Tests Deleted from Working Tree
- **What's not tested:** Everything. The working tree has zero test files.
- **Files:** `tests/` (entire directory deleted in working tree)
- **Risk:** Any code change could break functionality with no way to detect it.
- **Priority:** CRITICAL

### Missing Tests (Even in HEAD)
- **C++ module bindings:** No tests for the actual C++ module lifecycle with a real engine (test was skipped).
- **Rust module bindings:** No tests for the actual Rust module lifecycle with a real engine (test was skipped).
- **Job router under load:** No stress tests for concurrent job requests to the same handler.
- **Engine graceful shutdown:** No test verifies all threads terminate cleanly under load.
- **ZMQ reconnection:** No tests for module reconnection after engine restart.
- **Decimal edge cases:** No tests for `Decimal("NaN")`, `Decimal("Infinity")`, very large decimals.
- **Malformed message handling:** No tests for corrupted msgpack data, missing fields, or wrong types.

---

*Concerns audit: 2026-05-14*
