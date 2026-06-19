# CTP Gateway C++ Improvement Plan v1

> **Design reference:** `docs/design/ctp_gateway_cpp_improvement_v1.md`
> **Impl reference:** `docs/impl/ctp_gateway_cpp_latency_optimization.md`
> **Predecessor:** none (new plan for design v1)

## Project State at Plan Time

- **Design spec:** `docs/design/ctp_gateway_cpp_improvement_v1.md` (v1, approved) defines five implementation phases. Phases 1-4 are in scope for this plan; Phase 5 (advanced performance: micro-batching, CPU affinity, shared memory) is deferred to a future design cycle.
- **Current code:** `src/modules/ctp_gateway_cpp/src/` contains ~1559 LOC across 8 files (`ctp_gateway.h/cpp`, `md_spi.h/cpp`, `td_spi.h/cpp`, `config.h/cpp`, `ctp_loader.h/cpp`, `main.cpp`). The 2025-05-30 security audit fixed 17 CRITICAL/HIGH/MEDIUM issues (safe_copy, zero_password_field, atomic flags, noexcept cleanup, DLL path validation, etc.).
- **Uncommitted change:** `ctp_gateway.cpp` has a working-tree modification that reduces `option_dispatch_loop()` `wait_for` timeout from 200ms to 20ms (improving latency but not yet committed). This plan treats that change as part of the baseline and will supersede it with the full async RingBuffer refactor in TASK-8.
- **Existing tests:** Zero C++ unit tests exist for the CTP gateway module. The project has a working C++ test framework at `tests/cpp/CMakeLists.txt` using GoogleTest, covering `tyche` core (ring_buffer, message, types, etc.). The CTP gateway `CMakeLists.txt` builds only the executable target with no test target.
- **Greeks engine:** `src/modules/greeks_engine/greeks.py` implements `handle_compute_greeks` as a synchronous job handler (round-robin via `request_event`). It will need adaptation to consume async `send_event` ticks instead.
- **RingBuffer:** `src/tyche/cpp/engine/ring_buffer.h` provides a lock-free MPSC queue with `try_push`, `pop`, and `push_overwrite` — ready for use in the option dispatch path.
- **TycheModule API:** `src/tyche/cpp/module.h` exposes `send_event()`, `request_event()`, `_register_handler()`, `_register_job_handler()`, `_register_producer()`. The gateway currently registers `"send_quote"` (SEND) and `"request_compute_greeks"` (REQUEST).
- **No open CRITICAL items** in `docs/impl/ctp_gateway_cpp_latency_optimization.md` (it is an analysis doc, not an impl log).

## Scope

Implement Phases 1-4 of the design spec: CTP API abstraction layer for testability, RAII resource management, QuoteTick POD for zero-allocation hot path, hash-set option detection, RingBuffer-based async option dispatch, QuoteValidator abnormal tick filtering, stale tick detection, structured logging, and metrics counters with a `gateway_status` job handler. Adapt `greeks_engine.py` to consume async option events. Establish C++ unit test coverage >=80% for new code. Phase 5 (SHM, micro-batching, CPU affinity) is explicitly deferred.

---

## Tasks

### TASK-0: Baseline verification + CMake test scaffolding

**What:** Run the existing C++ test suite to confirm baseline is green. Add a `ctp_gateway_tests` test target to `src/modules/ctp_gateway_cpp/CMakeLists.txt` that compiles GoogleTest-based tests from a new `tests/` subdirectory under the module. Create a stub `test_baseline.cpp` that links against the module's internal headers and passes a trivial assertion.

**Why:** We need a clean baseline and working CMake infrastructure before any C++ code changes. Without test scaffolding, subsequent tasks cannot follow TDD (RED/GREEN).

**Expected result:** `ctest --test-dir build/cpp` (or equivalent) shows all pre-existing tyche tests green. A new `ctp_gateway_tests` target compiles and runs `test_baseline.cpp` successfully. No regressions in existing tests.

**Files touched:** `src/modules/ctp_gateway_cpp/CMakeLists.txt`, `src/modules/ctp_gateway_cpp/tests/test_baseline.cpp` (new).

**Estimated LOC:** ≤40 CMake + ≤20 test.

**Dependencies:** none.

---

### TASK-1: QuoteTick POD and conversions

**What:** Define `quote_tick.h` — a POD struct with fixed-size char arrays and primitive fields mirroring `CThostFtdcDepthMarketDataField`. Add `depth_to_tick()` in `md_spi.cpp` to fill it directly from the CTP callback. Add `tick_to_payload()` in `ctp_gateway.cpp` to convert `QuoteTick` to `tyche::Payload` only at the ZMQ send boundary. Update `on_quote_received()` signature to accept `const QuoteTick&`.

**Why:** Eliminates ~20 heap allocations per tick (Payload + string + any construction) on the hot path. The design spec identifies this as the single biggest latency win before queue/transport changes.

**Expected result:** `md_spi.cpp` no longer calls `depth_to_payload()` in `OnRtnDepthMarketData`. A unit test `test_quote_tick.cpp` verifies `depth_to_tick` field-by-field accuracy and `tick_to_payload` round-trip. Benchmark: `sizeof(QuoteTick)` is known and stable.

**Files touched:** `src/modules/ctp_gateway_cpp/src/quote_tick.h` (new), `src/modules/ctp_gateway_cpp/src/md_spi.h`, `src/modules/ctp_gateway_cpp/src/md_spi.cpp`, `src/modules/ctp_gateway_cpp/src/ctp_gateway.h`, `src/modules/ctp_gateway_cpp/src/ctp_gateway.cpp`, `src/modules/ctp_gateway_cpp/tests/test_quote_tick.cpp` (new).

**Estimated LOC:** ≤60 source + ≤80 test.

**Dependencies:** TASK-0.

---

### TASK-2: QuoteValidator abnormal tick filter

**What:** Add `quote_validator.h` with a `QuoteValidator` class. Implement `validate(const QuoteTick& tick, const QuoteTick& prev)` that checks: (a) price jump >10% outside limit-up/limit-down bounds, (b) timestamp regression, (c) volume decrease (unless trading day changed). In `on_quote_received()`, call the validator before routing; log and drop invalid ticks.

**Why:** Prevents abnormal CTP data (e.g., test environment injected prices, corrupted packets) from propagating to downstream engines. The design spec references MTS v3's `CheckMarketDataAbnormal()`.

**Expected result:** Unit test `test_quote_validator.cpp` covers: normal tick passes, price jump beyond limits rejected, timestamp regression rejected, volume decrease on same day rejected, cross-day volume decrease allowed. Invalid ticks are dropped and logged.

**Files touched:** `src/modules/ctp_gateway_cpp/src/quote_validator.h` (new), `src/modules/ctp_gateway_cpp/src/ctp_gateway.cpp`, `src/modules/ctp_gateway_cpp/tests/test_quote_validator.cpp` (new).

**Estimated LOC:** ≤50 source + ≤100 test.

**Dependencies:** TASK-1.

---

### TASK-3: CTP API abstraction layer (interfaces + adapters)

**What:** Define `ICtpMdApi` and `ICtpTdApi` interfaces in `ictp_api.h` with virtual methods for `RegisterFront`, `RegisterSpi`, `Init`, `Join`, `Release`, `SubscribeMarketData`, `ReqUserLogin`, etc. Implement `CtpMdApiAdapter` and `CtpTdApiAdapter` in `ctp_api_adapter.h` as thin wrappers around real CTP API pointers. Implement `MockMdApi` and `MockTdApi` in `mock_ctp_api.h` for testing (record calls, allow injection of synthetic responses).

**Why:** Decouples SPI logic from CTP SDK dependency, enabling offline unit tests. The design spec §3.1 identifies this as the foundation for testability.

**Expected result:** `md_spi.h` and `td_spi.h` compile against `ICtpMdApi*` / `ICtpTdApi*` instead of raw CTP pointers. Unit test `test_mock_md_api.cpp` verifies that `MockMdApi` records `SubscribeMarketData` calls and can inject `OnFrontConnected` behavior.

**Files touched:** `src/modules/ctp_gateway_cpp/src/ictp_api.h` (new), `src/modules/ctp_gateway_cpp/src/ctp_api_adapter.h` (new), `src/modules/ctp_gateway_cpp/src/mock_ctp_api.h` (new), `src/modules/ctp_gateway_cpp/src/md_spi.h`, `src/modules/ctp_gateway_cpp/src/td_spi.h`, `src/modules/ctp_gateway_cpp/tests/test_mock_md_api.cpp` (new).

**Estimated LOC:** ≤120 source + ≤80 test.

**Dependencies:** TASK-0.

---

### TASK-4: Refactor MdSpi/TdSpi to use abstraction + fake API tests

**What:** Update `MdSpiImpl` constructor to accept `ICtpMdApi*`. Update `TdSpiImpl` constructor to accept `ICtpTdApi*`. Replace all direct `md_api_->` / `td_api_->` calls with interface calls. Write `test_md_spi_logic.cpp` using `MockMdApi` to test: `OnFrontConnected` triggers `do_login`, `OnRspUserLogin` success triggers `do_subscribe`, `OnRtnDepthMarketData` invokes the quote callback with correct fields. Write `test_td_spi_logic.cpp` similarly.

**Why:** Validates that the abstraction layer actually enables testing. Confirms SPI behavior without requiring a live CTP connection.

**Expected result:** `md_spi.cpp` and `td_spi.cpp` compile with no direct `CThostFtdcMdApi` references outside the adapter. Tests pass without CTP SDK loaded.

**Files touched:** `src/modules/ctp_gateway_cpp/src/md_spi.h`, `src/modules/ctp_gateway_cpp/src/md_spi.cpp`, `src/modules/ctp_gateway_cpp/src/td_spi.h`, `src/modules/ctp_gateway_cpp/src/td_spi.cpp`, `src/modules/ctp_gateway_cpp/tests/test_md_spi_logic.cpp` (new), `src/modules/ctp_gateway_cpp/tests/test_td_spi_logic.cpp` (new).

**Estimated LOC:** ≤60 source + ≤120 test.

**Dependencies:** TASK-3.

---

### TASK-5: RAII wrappers (DllHandle, CtpApiPtr) and loader return type

**What:** Add `dll_handle.h` with `DllHandle` RAII class (move-only, calls `FreeLibrary`/`dlclose` in destructor). Add `ctp_api_raii.h` with `MdApiPtr` (`unique_ptr<CThostFtdcMdApi, MdApiDeleter>`) and `TdApiPtr`. Change `CtpLoader::create_md_api` and `create_td_api` to return `std::pair<DllHandle, CThostFtdcMdApi*>` (and TD equivalent) so the DLL handle lifetime is tied to the gateway.

**Why:** Fixes the DLL handle leak (never `FreeLibrary`'d) and eliminates manual `cleanup_ctp()` logic. The design spec §3.2 and §4.4 describe this.

**Expected result:** `CtpGateway` holds a `DllHandle md_dll_` and `DllHandle td_dll_`. `cleanup_ctp()` is simplified or removed. Unit test `test_dll_handle.cpp` verifies RAII release on scope exit. Unit test `test_ctp_loader.cpp` verifies path validation and pair return type.

**Files touched:** `src/modules/ctp_gateway_cpp/src/dll_handle.h` (new), `src/modules/ctp_gateway_cpp/src/ctp_api_raii.h` (new), `src/modules/ctp_gateway_cpp/src/ctp_loader.h`, `src/modules/ctp_gateway_cpp/src/ctp_loader.cpp`, `src/modules/ctp_gateway_cpp/src/ctp_gateway.h`, `src/modules/ctp_gateway_cpp/src/ctp_gateway.cpp`, `src/modules/ctp_gateway_cpp/tests/test_dll_handle.cpp` (new), `src/modules/ctp_gateway_cpp/tests/test_ctp_loader.cpp` (new).

**Estimated LOC:** ≤80 source + ≤100 test.

**Dependencies:** TASK-0. Can run in parallel with TASK-3/TASK-4 after TASK-0.

---

### TASK-6: Gateway resource management refactor with RAII

**What:** Replace raw `CThostFtdcMdApi* md_api_` and `CThostFtdcTraderApi* td_api_` with `MdApiPtr` and `TdApiPtr`. Replace `cleanup_done_` atomic and manual `cleanup_ctp()` with RAII destruction order (SPI reset, Join, Release, then DLL handle destruction). Ensure `stop()` sequence remains correct: signal stop, join dispatch thread, then let RAII handle CTP cleanup.

**Why:** Exception-safe resource cleanup on any exit path. Eliminates ~40 lines of manual cleanup and the `cleanup_done_` flag. The design spec §3.2 targets this.

**Expected result:** `ctp_gateway.cpp` no longer contains `cleanup_ctp()` with manual `Release()` calls. `CtpGateway` destructor safely cleans up even if `stop()` was not called. Unit test `test_gateway_lifecycle.cpp` verifies start/stop idempotency and no crashes on early destruction.

**Files touched:** `src/modules/ctp_gateway_cpp/src/ctp_gateway.h`, `src/modules/ctp_gateway_cpp/src/ctp_gateway.cpp`, `src/modules/ctp_gateway_cpp/tests/test_gateway_lifecycle.cpp` (new).

**Estimated LOC:** ≤80 source + ≤80 test.

**Dependencies:** TASK-5 (RAII wrappers must exist).

---

### TASK-7: Hash-set option detection and QuoteTick routing

**What:** Replace `std::vector<std::string> option_instruments_` + `std::binary_search` with `std::unordered_set<std::string> option_instrument_set_`. In `resolve_instruments()`, populate the set. In `on_quote_received()`, use `option_instrument_set_.count(instrument_id) > 0` for O(1) lookup. Use `std::string_view` from `QuoteTick::instrument_id` to avoid string construction where possible.

**Why:** `binary_search` is O(log n) with string comparisons; hash set is O(1). The design spec §5.2 identifies this as a throughput improvement.

**Expected result:** `on_quote_received()` routing latency is reduced. Unit test `test_quote_routing.cpp` verifies: futures pass through to `send_event`, options are routed to the queue, unknown instruments are treated as futures (safe fallback).

**Files touched:** `src/modules/ctp_gateway_cpp/src/ctp_gateway.h`, `src/modules/ctp_gateway_cpp/src/ctp_gateway.cpp`, `src/modules/ctp_gateway_cpp/tests/test_quote_routing.cpp` (new).

**Estimated LOC:** ≤40 source + ≤80 test.

**Dependencies:** TASK-1 (QuoteTick must exist).

---

### TASK-8: RingBuffer option queue and asynchronous compute_greeks dispatch

**What:** Replace `std::queue<tyche::Payload> option_queue_` + `mutex` + `condition_variable` with `tyche::RingBuffer<QuoteTick> option_ring_buffer_` (capacity 65536). Rewrite `option_dispatch_loop()` to `pop()` from the RingBuffer in a tight loop; when a tick is available, call `send_event("compute_greeks", tick_to_payload(tick))` asynchronously instead of `request_event`. Remove the 20ms/200ms `wait_for` timeout entirely — `pop()` is non-blocking and returns `std::nullopt` when empty. Add a short `std::this_thread::yield()` or `sleep_for(1ms)` only when empty to avoid busy-spinning. Change the producer registration from `"request_compute_greeks"` to `"send_compute_greeks"`.

**Why:** Eliminates the 10s synchronous blocking and the 20ms poll latency. The design spec §3.3 and §5.1 target this as the highest-impact performance change. RingBuffer provides ~50ns enqueue vs ~5us for mutex queue.

**Expected result:** Option dispatch thread no longer blocks on `request_event`. Unit test `test_option_dispatch.cpp` verifies: ticks are enqueued and dequeued in order, queue-full behavior uses `push_overwrite` (drop oldest), thread stops cleanly on `ctp_running_ = false`, no `request_event` calls remain in the dispatch path.

**Files touched:** `src/modules/ctp_gateway_cpp/src/ctp_gateway.h`, `src/modules/ctp_gateway_cpp/src/ctp_gateway.cpp`, `src/modules/ctp_gateway_cpp/tests/test_option_dispatch.cpp` (new).

**Estimated LOC:** ≤80 source + ≤100 test.

**Dependencies:** TASK-1 (QuoteTick), TASK-7 (hash-set routing).

---

### TASK-9: Tick stale detection

**What:** Add `std::atomic<std::chrono::steady_clock::time_point> last_tick_time_` to `MdSpiImpl` (or `CtpGateway`). In `OnRtnDepthMarketData`, update it. In `option_dispatch_loop()`, every 30 seconds check `std::chrono::steady_clock::now() - last_tick_time_`; if >30s, set `tick_stale_` atomic flag and log a warning. Register a `gateway_status` job handler (see TASK-11) that includes `last_tick_age_ms`. Add a `reconnect_count_` atomic incremented in `OnFrontDisconnected`.

**Why:** Detects CTP front-end silent failures where the connection is alive but no data flows. The design spec §4.1 requires this.

**Expected result:** If no tick arrives for 30s, a warning is logged and `tick_stale_` is true. Unit test `test_stale_detection.cpp` uses `MockMdApi` to simulate ticks and disconnects, verifying stale flag and reconnect counter.

**Files touched:** `src/modules/ctp_gateway_cpp/src/md_spi.h`, `src/modules/ctp_gateway_cpp/src/md_spi.cpp`, `src/modules/ctp_gateway_cpp/src/ctp_gateway.h`, `src/modules/ctp_gateway_cpp/src/ctp_gateway.cpp`, `src/modules/ctp_gateway_cpp/tests/test_stale_detection.cpp` (new).

**Estimated LOC:** ≤50 source + ≤80 test.

**Dependencies:** TASK-4 (MdSpi testable with MockMdApi).

---

### TASK-10: Structured logging macros

**What:** Add `gateway_log.h` with macros `LOG_INFO`, `LOG_WARN`, `LOG_ERROR` that prefix `[ISO8600-ts][LEVEL][CtpGateway] ` to `std::cout`/`std::cerr`. Replace all `std::cout`/`std::cerr` logging in `ctp_gateway.cpp`, `md_spi.cpp`, `td_spi.cpp`, `ctp_loader.cpp` with the macros. Keep the same message content; only the prefix format changes.

**Why:** Enables automated log parsing and monitoring. The design spec §7.1 identifies this as an observability requirement.

**Expected result:** All gateway logs have a consistent structured prefix. No raw `std::cout`/`std::cerr` remains in the module source. Unit test `test_gateway_log.cpp` verifies macro output format (capture stdout/stderr).

**Files touched:** `src/modules/ctp_gateway_cpp/src/gateway_log.h` (new), `src/modules/ctp_gateway_cpp/src/ctp_gateway.cpp`, `src/modules/ctp_gateway_cpp/src/md_spi.cpp`, `src/modules/ctp_gateway_cpp/src/td_spi.cpp`, `src/modules/ctp_gateway_cpp/src/ctp_loader.cpp`, `src/modules/ctp_gateway_cpp/tests/test_gateway_log.cpp` (new).

**Estimated LOC:** ≤40 source + ≤60 test.

**Dependencies:** none. Can run in parallel with most tasks.

---

### TASK-11: Metrics counters and gateway_status job

**What:** Add atomic counters to `CtpGateway`: `ticks_received_`, `ticks_sent_`, `option_dropped_`, `option_errors_`. Increment them at the appropriate points in `on_quote_received()` and `option_dispatch_loop()`. Register a `_register_job_handler("gateway_status", ...)` that returns a `Payload` with: `status`, `instruments_count`, `option_queue_depth`, `reconnect_count`, `ticks_received`, `ticks_sent`, `option_dropped`, `option_errors`, `tick_stale`, `uptime_secs`.

**Why:** Provides real-time operational visibility into gateway health. The design spec §7.2 and §7.3 define these metrics.

**Expected result:** Admin/TUI can query gateway status via the job handler. Unit test `test_gateway_status.cpp` verifies the handler returns correct counts and all expected fields.

**Files touched:** `src/modules/ctp_gateway_cpp/src/ctp_gateway.h`, `src/modules/ctp_gateway_cpp/src/ctp_gateway.cpp`, `src/modules/ctp_gateway_cpp/tests/test_gateway_status.cpp` (new).

**Estimated LOC:** ≤60 source + ≤80 test.

**Dependencies:** TASK-8 (async dispatch loop structure final), TASK-9 (stale flag).

---

### TASK-12: greeks_engine event handler adaptation

**What:** Modify `src/modules/greeks_engine/greeks.py`: add `on_compute_greeks(self, payload)` event handler (consumer pattern) that performs the same work as `handle_compute_greeks` but does not return a response payload. Keep `handle_compute_greeks` for backward compatibility during transition (or remove if the gateway no longer uses `request_event`). Update `_register_handler` call for `on_compute_greeks` in the constructor. Ensure the payload format from `tick_to_payload()` is compatible.

**Why:** The gateway's async `send_event("compute_greeks", ...)` requires a consumer on the greeks_engine side. The design spec §3.3 and §4.3 describe this coupling.

**Expected result:** `greeks_engine.py` receives option ticks via `on_compute_greeks` and computes/publishes Greeks without a request-response round-trip. Unit test `tests/unit/test_greeks_engine.py` verifies `on_compute_greeks` produces the same output as `handle_compute_greeks` for identical input.

**Files touched:** `src/modules/greeks_engine/greeks.py`, `tests/unit/test_greeks_engine.py` (modify/add).

**Estimated LOC:** ≤40 source + ≤60 test.

**Dependencies:** TASK-8 (gateway must send async events).

---

### TASK-13: C++ unit tests and CMake integration

**What:** Ensure all new test files from TASK-1 through TASK-11 are compiled into the `ctp_gateway_tests` target added in TASK-0. Verify total line coverage of new C++ code is >=80% using `gcov`/`llvm-cov` if available, or manual inspection if not. Fix any compilation issues from the accumulated changes. Add `tests/cpp/CMakeLists.txt` integration if the module tests should also be runnable from the top-level test directory.

**Why:** The design spec §6.1 mandates >=80% coverage. This task is the integration gate for all preceding C++ test work.

**Expected result:** `cmake --build build --target ctp_gateway_tests && ctest --test-dir build -R ctp_gateway` passes. Coverage report shows >=80% for `quote_tick.h`, `quote_validator.h`, `ictp_api.h`, `ctp_api_adapter.h`, `mock_ctp_api.h`, `dll_handle.h`, `ctp_api_raii.h`, `gateway_log.h`, and modified gateway/loader/SPI files.

**Files touched:** `src/modules/ctp_gateway_cpp/CMakeLists.txt`, `src/modules/ctp_gateway_cpp/tests/` (all test files from prior tasks).

**Estimated LOC:** ≤40 CMake + test integration only.

**Dependencies:** TASK-0 through TASK-11 (all C++ tasks must be complete).

---

### TASK-14: Final verification

**What:** Run the full project test suite: `pytest tests/ -v` for Python, `ctest` for C++. Perform a manual integration smoke test: start TycheEngine, start static_data, start ctp_gateway_cpp (with OpenCTP or mock), verify quote events flow to a test consumer. Verify `gateway_status` job returns correct JSON. Verify no `request_event("compute_greeks")` calls remain in the gateway. Verify no raw `std::cout` logging remains.

**Why:** End-to-end validation that all pieces work together. Catches integration issues that unit tests miss (e.g., payload format mismatch between C++ and Python).

**Expected result:** All tests pass. Integration smoke test confirms: futures broadcast as `quote` events, options dispatch as `compute_greeks` events, `greeks_engine` consumes and publishes `greeks_update`, `gateway_status` job responds correctly.

**Files touched:** none (verification only). Output recorded in impl log.

**Estimated LOC:** 0.

**Dependencies:** TASK-12 (Python side adapted), TASK-13 (C++ tests integrated).

---

## Verification

### Commands

```bash
# C++ baseline and module tests
cmake -B build/cpp -S tests/cpp
cmake --build build/cpp --target tyche_tests
cmake --build build/cpp --target ctp_gateway_tests  # from module CMakeLists.txt
ctest --test-dir build/cpp -V

# Python tests
pytest tests/ -v

# Coverage (if gcov available)
ctest --test-dir build/cpp -T Coverage
```

### Success criteria

1. All pre-existing `tyche_tests` pass (no regression).
2. All `ctp_gateway_tests` pass (>=80% line coverage on new C++ code).
3. All Python `pytest` tests pass (no regression in `greeks_engine` or other modules).
4. `grep -r "request_event.*compute_greeks" src/modules/ctp_gateway_cpp/` returns no hits.
5. `grep -r "std::cout << \"\[" src/modules/ctp_gateway_cpp/` returns no hits (all logging via macros).
6. `grep -r "std::binary_search" src/modules/ctp_gateway_cpp/` returns no hits (replaced by hash set).
7. `grep -r "std::queue<tyche::Payload>" src/modules/ctp_gateway_cpp/` returns no hits (replaced by RingBuffer).
8. Integration smoke test confirms end-to-end event flow (recorded in impl log Task Log).

---

## Dependencies

```
TASK-0 (scaffolding)
  │
  ├──► TASK-1 (QuoteTick)
  │      │
  │      ├──► TASK-2 (QuoteValidator)
  │      ├──► TASK-7 (hash-set routing)
  │      │      │
  │      │      └──► TASK-8 (RingBuffer async dispatch)
  │      │             │
  │      │             ├──► TASK-11 (metrics + status job)
  │      │             │      │
        │             │      └──► TASK-14 (final verification)
  │      │             │
  │      │             └──► TASK-12 (greeks_engine adaptation)
  │      │                    │
  │      │                    └──► TASK-14
  │      │
  ├──► TASK-3 (abstraction interfaces)
  │      │
  │      └──► TASK-4 (MdSpi/TdSpi refactor)
  │             │
  │             └──► TASK-9 (stale detection)
  │                    │
  │                    └──► TASK-11
  │
  ├──► TASK-5 (RAII wrappers)
  │      │
  │      └──► TASK-6 (gateway RAII refactor)
  │             │
  │             └──► TASK-14
  │
  └──► TASK-10 (structured logging) ──► (independent, can merge anytime)
```

**Suggested execution order:**

```
Wave 1 (independent after TASK-0):
  TASK-1, TASK-3, TASK-5, TASK-10

Wave 2 (depends on Wave 1):
  TASK-2, TASK-4, TASK-6, TASK-7

Wave 3 (depends on Wave 2):
  TASK-8, TASK-9

Wave 4 (depends on Wave 3):
  TASK-11, TASK-12

Wave 5 (final gate):
  TASK-13, TASK-14
```

**Parallelizable pairs:**
- TASK-1 + TASK-3 + TASK-5 + TASK-10 (all independent after TASK-0)
- TASK-2 + TASK-4 + TASK-6 + TASK-7 (all independent after Wave 1)
- TASK-8 + TASK-9 (independent after Wave 2)
- TASK-11 + TASK-12 (independent after Wave 3)
