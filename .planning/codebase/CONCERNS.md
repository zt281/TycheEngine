# Codebase Concerns

**Analysis Date:** 2026-04-28

## Tech Debt

### CTP Gateway Mock Dependency in Tests
- **Issue:** CTP gateway tests rely on heavy `sys.modules` manipulation and `unittest.mock.MagicMock` to mock `openctp_ctp` before import. This is fragile and caused a real bug where `MagicMock.__call__` raised `StopIteration` when SPI classes inherited from `MagicMock` instead of `object`.
- **Files:** `tests/unit/test_ctp_gateway.py`, `tests/unit/test_ctp_gateway_enhanced.py`
- **Impact:** Test suite can fail non-deterministically depending on import order. The fix (setting `CThostFtdcMdSpi = object`) is a workaround, not a solution.
- **Fix approach:** Extract CTP API interactions behind a thin adapter/bridge interface that can be mocked cleanly without `sys.modules` manipulation. Consider using `pytest-mock` fixtures or dependency injection.

### Broad Exception Handling
- **Issue:** Widespread use of bare `except Exception:` (or `except Exception as e:` with only logging) across the codebase. This swallows unexpected errors and makes debugging difficult.
- **Files:**
  - `src/tyche/engine.py` (lines 151, 154, 192, 292, 328, 331, 360, 364, 367, 397, 400, 454)
  - `src/tyche/module.py` (lines 249, 279, 294, 390)
  - `src/modules/trading/gateway/ctp/gateway.py` (lines 684, 703, 773, 780, 1045, 1051, 1078)
  - `src/modules/trading/persistence/clickhouse_backend.py` (lines 84, 134, 200, 214, 228)
  - `src/modules/trading/persistence/jsonl_backend.py` (line 138)
  - `src/modules/trading/persistence/schema.py` (lines 83, 104)
  - `src/modules/trading/risk/rules.py` (line 184)
- **Impact:** Silent failures in production, lost error context, potential data corruption if exceptions are swallowed during critical operations.
- **Fix approach:** Replace with specific exception types. For ZMQ operations, catch `zmq.error.ZMQError`. For I/O, catch `OSError`. Add structured error propagation rather than just logging.

### Assert Statements in Production Code
- **Issue:** `assert` is used in `TycheEngine` and `TycheModule` for runtime checks (e.g., `assert self.context is not None`). These are removed when Python runs with `-O`.
- **Files:**
  - `src/tyche/engine.py` (lines 138, 262, 302, 338, 384)
  - `src/tyche/module.py` (lines 206, 260, 267)
- **Impact:** In production with `-O`, these checks vanish, potentially leading to `AttributeError` on `None` objects instead of clear early failures.
- **Fix approach:** Replace all `assert` statements with explicit `if ...: raise RuntimeError(...)` checks.

### No Custom Exception Hierarchy
- **Issue:** The codebase has zero custom exception classes. All errors are raised as generic `ValueError`, `RuntimeError`, or swallowed.
- **Files:** All source files
- **Impact:** Callers cannot distinguish between recoverable and fatal errors. Risk rules catching `Exception` may mask programming errors.
- **Fix approach:** Create a `TycheError` base exception and subclasses like `GatewayError`, `RiskError`, `PersistenceError`, `SerializationError`.

## Security Considerations

### CTP Password in Plain Text
- **Risk:** CTP gateway stores trading passwords as plain strings in memory and passes them through CLI arguments and config files.
- **Files:**
  - `src/modules/trading/gateway/ctp/gateway.py` (line 179: `self._password = password`)
  - `src/modules/trading/gateway/ctp/config.py` (lines 27-31, 75-76)
  - `src/modules/trading/gateway/ctp/gateway_main.py` (line 34: `--password` CLI arg)
- **Current mitigation:** None. Passwords are stored as regular Python strings.
- **Recommendations:**
  - Accept passwords via environment variables or secure credential stores only.
  - Use `getpass.getpass()` for interactive input.
  - Consider using `str` subclasses that clear memory on deletion (limited in Python but better than nothing).
  - Never log passwords (verify no logging of `password` field).

### ClickHouse Password in Plain Text
- **Risk:** ClickHouse backend stores database password as a plain string.
- **Files:** `src/modules/trading/persistence/clickhouse_backend.py` (line 52: `self._password = password`)
- **Current mitigation:** None.
- **Recommendations:** Same as CTP passwords -- use environment variables or a secrets manager.

### No Input Validation on ZMQ Messages
- **Risk:** The engine's `_process_registration` and `_process_admin_query` methods deserialize arbitrary msgpack data without schema validation.
- **Files:** `src/tyche/engine.py` (lines 159-193, 405-455)
- **Current mitigation:** `try/except` blocks catch deserialization errors.
- **Recommendations:** Add payload schema validation (e.g., using `pydantic` or `marshmallow`) for all incoming messages to prevent malformed payloads from crashing workers.

## Performance Bottlenecks

### JSONL Backend Full-Table Scan
- **Problem:** `JsonlBackend.query()` scans ALL JSONL files recursively for every query, loading every line into memory.
- **Files:** `src/modules/trading/persistence/jsonl_backend.py` (lines 102-137)
- **Cause:** No indexing, no partitioning beyond date. Every query is O(total_rows).
- **Improvement path:** Add file-level metadata (min/max timestamp per file) to skip files. For production, migrate to ClickHouse or SQLite with proper indexing.

### CTP Event Queue Unbounded Growth
- **Problem:** The CTP gateway uses an unbounded `queue.Queue` to bridge SPI callbacks to the dispatcher thread. Under high market data load or if the dispatcher is slow, the queue grows without bound.
- **Files:** `src/modules/trading/gateway/ctp/gateway.py` (line 197: `self._event_queue: queue.Queue[Tuple[str, Any]] = queue.Queue()`)
- **Cause:** No `maxsize` on the queue, no backpressure mechanism.
- **Improvement path:** Set a `maxsize` and drop old events (quote data is time-sensitive) or apply backpressure to the SPI thread.

### ZMQ Context Sharing
- **Problem:** Each `TycheModule` creates its own `zmq.Context`. The ZMQ guide recommends one context per process.
- **Files:** `src/tyche/module.py` (line 129: `self.context = zmq.Context()`)
- **Cause:** Modules are designed to run in separate processes, but when used in the same process (testing), this creates multiple contexts.
- **Improvement path:** Use `zmq.Context.instance()` for singleton behavior or document that modules must run in separate processes.

### Heartbeat Sleep Loop Inefficiency
- **Problem:** `TycheModule._send_heartbeats()` uses a busy-sleep loop (`for _ in range(int(HEARTBEAT_INTERVAL * 10)): time.sleep(0.1)`) instead of a single `Event.wait()`.
- **Files:** `src/tyche/module.py` (lines 397-400)
- **Cause:** Legacy code from signal handling fix.
- **Improvement path:** Replace with `self._stop_event.wait(HEARTBEAT_INTERVAL)`.

## Fragile Areas

### CTP Exchange Inference
- **Files:** `src/modules/trading/gateway/ctp/gateway.py` (lines 46-112, `_infer_exchange()`)
- **Why fragile:** The `EXCHANGE_MAP` is a hardcoded dictionary of instrument prefixes. New instruments or exchanges require code changes. The prefix matching logic tries multiple lengths which is error-prone (e.g., "ao" vs "a" ambiguity).
- **Safe modification:** Add comprehensive tests for edge cases. Consider making the exchange map configurable.
- **Test coverage:** Only basic unit tests exist; no property tests for exchange inference.

### CTP Order Ref Counter
- **Files:** `src/modules/trading/gateway/ctp/gateway.py` (lines 202-206, 234-237, 422-426)
- **Why fragile:** The order ref counter is seeded from CTP's `MaxOrderRef` but falls back to zero. In multi-process or restart scenarios, order ref collisions are possible.
- **Safe modification:** Use a UUID-based approach or persist the counter across restarts.
- **Test coverage:** No tests for counter collision scenarios.

### Simulated Gateway `time.sleep()` in `submit_order`
- **Files:** `src/modules/trading/gateway/simulated.py` (line 100: `time.sleep(self._fill_latency)`)
- **Why fragile:** Blocking sleep in the order submission path blocks the calling thread. In a high-frequency scenario, this serializes all orders.
- **Safe modification:** Use async/delayed execution or a thread pool for simulated fills.

### Position.apply_fill Flip Logic
- **Files:** `src/modules/trading/models/position.py` (lines 66-91)
- **Why fragile:** The position flip logic (closing a long and opening a short in one fill) is complex and untested for edge cases like exact-size closes.
- **Safe modification:** Add property tests and boundary tests for all quantity combinations.
- **Test coverage:** Basic unit tests exist but no exhaustive coverage.

## Scaling Limits

### Engine Single-Threaded Event Proxy
- **Current capacity:** The XPUB/XSUB proxy in `TycheEngine._event_proxy_worker()` uses a single-threaded `zmq.Poller` loop.
- **Limit:** Throughput tests show ~1000-5000 msg/s. Under heavy load with many modules, this becomes a bottleneck.
- **Scaling path:** Consider using `zmq.proxy()` (native C implementation) instead of a Python poller loop. The current manual proxy was likely written for control; benchmark against `zmq.proxy()`.

### In-Memory Order Store
- **Current capacity:** `OrderStore` keeps all orders in a `Dict` in memory.
- **Limit:** No eviction policy. Long-running systems will accumulate unlimited orders.
- **Scaling path:** Add configurable retention (e.g., keep only last N days of orders). Archive old orders to persistence backend.

### Heartbeat Manager Global Lock
- **Current capacity:** `HeartbeatManager.tick_all()` holds a lock while ticking all monitors.
- **Limit:** With thousands of modules, this could block heartbeat updates.
- **Scaling path:** Shard monitors by module ID prefix or use lock-free data structures.

## Dependencies at Risk

### openctp-ctp (CTP Binding)
- **Risk:** The `openctp-ctp` package is a Python binding to the CTP C++ API. It is platform-specific (Windows/Linux) and may lag behind CTP API updates.
- **Impact:** If the upstream CTP API changes (new fields, deprecated methods), the gateway breaks.
- **Migration plan:** Monitor OpenCTP releases. Consider abstracting CTP interactions behind an interface to allow swapping to alternative CTP bindings.

### msgpack Serialization
- **Risk:** Custom `_encode_decimal` and `_decode_decimal` hooks for `Decimal` serialization. If msgpack changes its extension API, serialization breaks.
- **Impact:** All inter-module communication depends on this.
- **Migration plan:** Add serialization version header to messages. Test against multiple msgpack versions.

## Missing Critical Features

### No Message Persistence / Recovery
- **Problem:** If the engine crashes, all in-flight messages and module registrations are lost. There is no WAL (Write-Ahead Log) or message replay.
- **Blocks:** Exactly-once delivery guarantees, crash recovery.

### No Circuit Breaker for Failed Gateways
- **Problem:** The CTP gateway has auto-reconnect with backoff, but no circuit breaker. If the broker is down for an extended period, the gateway keeps retrying indefinitely (or until max retries).
- **Blocks:** Graceful degradation during extended outages.

### No Rate Limiting on Event Publishing
- **Problem:** Modules can publish events as fast as they want. A misbehaving module could flood the event proxy.
- **Blocks:** DoS protection, fair resource sharing.

### No Configuration Hot-Reload
- **Problem:** All configuration is loaded at startup. Changing risk rules, instrument subscriptions, or gateway settings requires restart.
- **Blocks:** Dynamic trading system management.

## Test Coverage Gaps

### CTP Gateway Integration Tests
- **What's not tested:** Actual CTP connection (only mocked). Auto-reconnect under real network conditions. Position accumulation with multiple position records.
- **Files:** `src/modules/trading/gateway/ctp/gateway.py`
- **Risk:** The reconnect loop and SPI callback threading model have subtle race conditions that mocks cannot catch.
- **Priority:** High

### Engine Multi-Process Tests
- **What's not tested:** The slow integration tests (`test_engine_process_starts_and_stops`, `test_module_connects_to_engine_process`) are marked `@pytest.mark.slow` and may not run in CI.
- **Files:** `tests/integration/test_multiprocess.py`
- **Risk:** Process separation bugs (signal handling, socket cleanup across processes) go undetected.
- **Priority:** High

### Risk Rules Edge Cases
- **What's not tested:** `RateLimitRule` does not track orders per minute (only min interval). `MaxDailyLossRule` uses `daily_pnl` but there is no daily reset mechanism.
- **Files:** `src/modules/trading/risk/rules.py`
- **Risk:** Risk rules may have false negatives.
- **Priority:** Medium

### Serialization Round-Trips with Edge Cases
- **What's not tested:** `Message` serialization with nested `Decimal` values, large payloads, or special characters.
- **Files:** `src/tyche/message.py`
- **Risk:** Data corruption in inter-module communication.
- **Priority:** Medium

### OrderStore State Machine
- **What's not tested:** Invalid state transitions are logged but not tested exhaustively. Concurrent access to `OrderStore` is not stress-tested.
- **Files:** `src/modules/trading/oms/order_store.py`
- **Risk:** Race conditions in order status updates under load.
- **Priority:** Medium

## Architectural Constraints

### Threading-Only (No Asyncio)
- **Constraint:** The engine and modules were converted from asyncio to threading for multi-process support. This means CPU-bound work in handlers blocks the event loop.
- **Impact:** Strategies doing heavy computation will block message processing.
- **Mitigation:** Document that handlers must be non-blocking. Consider thread pools for handler execution.

### ZMQ Port Allocation
- **Constraint:** The engine allocates multiple ZMQ ports (registration, event pub, event sub, heartbeat, heartbeat receive, admin). Port conflicts are possible.
- **Impact:** Hard to run multiple engine instances on the same host.
- **Mitigation:** Add port discovery or dynamic port allocation with port-file communication.

### No Module Lifecycle Management
- **Constraint:** Modules register once and are expected to stay connected. There is no graceful shutdown protocol (modules just stop sending heartbeats and expire).
- **Impact:** Modules cannot signal "going away" to flush pending work.
- **Mitigation:** Add an explicit unregister/deregister message type.

## Process Concerns (from CLAUDE.md)

### TDD Rule: No `__init__.py` in tests/
- **Concern:** The project has `tests/unit/` and `tests/integration/` but pytest handles discovery without `__init__.py`. However, some imports use absolute paths that may break without proper package structure.
- **Files:** All test files
- **Risk:** Import errors in CI if PYTHONPATH is not set correctly.

### Coverage Regression Gate
- **Concern:** CLAUDE.md specifies coverage regression >2% blocks commit, but there is no CI configuration visible in the repo to enforce this.
- **Files:** `pyproject.toml` (has coverage config but no CI)
- **Risk:** Coverage requirements are not automatically enforced.

---

*Concerns audit: 2026-04-28*
