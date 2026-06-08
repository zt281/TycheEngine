# Domain Pitfalls: Adding Database Persistence to an Event-Driven Trading Engine

**Domain:** Event-driven trading engine (TycheEngine) — adding pluggable ClickHouse/SQLite persistence module
**Researched:** 2026-05-14
**Confidence:** HIGH (multiple authoritative sources verified)

---

## Performance Pitfalls

### P1: Blocking the Event Loop with Synchronous DB Writes
**What goes wrong:** The `PersistenceModule` receives events via `TycheModule._event_receiver()` which runs in a daemon thread. If the handler (`on_*`) performs synchronous DB I/O (e.g., `client.execute()` or `sqlite3` insert), it blocks that thread. Under high load, the module's event receiver thread stalls, causing the SUB socket's ZMQ receive buffer to back up. With `RCVHWM=10000`, messages drop silently once the buffer fills.

**Why it happens:**
- Python `sqlite3` has no async API — all operations are blocking
- `clickhouse-driver` is synchronous TCP; `clickhouse-connect` uses `urllib3` (blocking HTTP)
- The `TycheModule._dispatch()` calls handlers synchronously with no timeout or offloading

**Consequences:**
- Event latency spikes proportional to DB write latency
- Silent message drops at the ZMQ socket level (not logged as module drops)
- Heartbeat thread continues running, so engine thinks module is healthy
- Other modules' events may be delayed if engine's XPUB socket buffers fill

**Prevention:**
1. **Dedicated writer thread with bounded queue:** The persistence module should spawn a separate `threading.Thread` that owns the DB connection. Events are placed on a `queue.Queue(maxsize=N)` from the ZMQ receiver thread. The writer thread dequeues and batches.
2. **Never do DB I/O in `on_*` handlers:** Use `on_*` only to enqueue to the internal buffer. All DB operations happen in the writer thread.
3. **For SQLite specifically:** The single writer thread pattern is mandatory — SQLite WAL allows only one writer at a time. Multiple threads attempting writes will hit `SQLITE_BUSY`.

**Detection warning signs:**
- `TycheEngine` admin query shows module is registered but event counts stall
- ZMQ `RCVHWM` drops not visible in module-level metrics
- Latency increases correlate with DB write batch flushes

**Assigned phase:** Phase 1 (Core persistence module skeleton) — the threading model must be designed correctly from the start.

---

### P2: Buffer Overflow and Data Loss Under High Load
**What goes wrong:** Events arrive faster than the DB backend can write them. The internal buffer (between ZMQ receiver and DB writer) grows until it hits capacity, then new events are dropped. In trading systems, this typically happens during market open (burst of order book updates) or during backtests (synthetic high-frequency events).

**Why it happens:**
- No backpressure from persistence module to engine
- ZMQ's fire-and-forget pub/sub has no flow control
- Default `queue.Queue()` is unbounded — if used, it grows until OOM
- Bounded queue with `put(block=False)` silently drops without logging

**Consequences:**
- Gaps in event history — replay becomes impossible
- Audit trail is incomplete — compliance risk
- OOM crash if unbounded queue is used (entire engine process killed)

**Prevention:**
1. **Always use bounded queues:** `queue.Queue(maxsize=10000)` or similar, sized to ~10 seconds of peak throughput.
2. **Log every drop:** When `put()` returns `False` or raises `queue.Full`, log at WARNING with event type and count.
3. **Expose metrics:** Add `buffer_size`, `buffer_capacity`, `dropped_count` to the module's admin/status response.
4. **Consider backpressure signal:** If buffer > 80% for sustained period, the module could emit a `persistence_backpressure` event that other modules (or the engine) can subscribe to for throttling.

**Detection warning signs:**
- `dropped_count` metric increasing
- Memory usage growing linearly during bursts (unbounded queue)
- Buffer size consistently near capacity

**Assigned phase:** Phase 1 (Core persistence module skeleton) — buffer design is foundational.

---

### P3: Per-Event DB Round-Trip
**What goes wrong:** Writing each event as a separate `INSERT` statement. Even with async inserts, this creates excessive network overhead and CPU context switching.

**Why it happens:**
- Naive implementation calls `execute("INSERT ...")` for every event
- Developer assumes async insert settings make this efficient
- ClickHouse's `async_insert` buffers at the server, but each query still has client/server round-trip overhead

**Consequences:**
- Throughput capped at ~100-1000 events/sec regardless of hardware
- ClickHouse creates too many parts → `TOO_MANY_PARTS` error
- SQLite single-row inserts are ~50x slower than batch inserts

**Prevention:**
1. **Batch by size AND time:** Flush when batch reaches N rows OR M seconds have elapsed since last flush (whichever comes first).
2. **Recommended thresholds:**
   - ClickHouse: 10,000 rows or 5 seconds
   - SQLite: 100 rows or 1 second (SQLite is faster with smaller batches due to transaction overhead)
3. **Use parameterized multi-row inserts:** `INSERT INTO t (a,b) VALUES (?,?), (?,?), ...` for SQLite; bulk insert API for ClickHouse.

**Detection warning signs:**
- `system.query_log` shows `avg(written_rows) < 1000` per insert (ClickHouse)
- CPU usage high but throughput low
- `TOO_MANY_PARTS` errors in ClickHouse logs

**Assigned phase:** Phase 2 (Batching and buffering logic) — must be implemented before any performance testing.

---

## Reliability Pitfalls

### P4: Error Handling That Silently Drops Events
**What goes wrong:** A DB write fails (connection lost, disk full, syntax error) but the exception is caught, logged, and the event is discarded. The system continues running but events are permanently lost.

**Why it happens:**
- `try/except` around `execute()` logs the error but does not retry or save the failed batch
- No distinction between transient errors (network timeout) and permanent errors (syntax error)
- Events are removed from the buffer before write confirmation

**Consequences:**
- Silent data loss — hardest bug to detect
- Replay produces different results than live run
- Audit gaps discovered days or weeks later

**Prevention:**
1. **Confirm before dequeue:** Only remove events from the buffer after the DB confirms the write succeeded.
2. **Classify errors:**
   - **Transient** (retry): connection timeout, `SQLITE_BUSY`, `TOO_MANY_PARTS`
   - **Permanent** (dead letter): syntax error, schema mismatch, constraint violation
3. **Retry with backoff:** For transient errors, retry up to 3 times with exponential backoff. If all retries fail, write to a local dead-letter file (JSONL) for later replay.
4. **Circuit breaker:** After N consecutive failures, stop attempting DB writes and buffer to disk instead. This prevents hammering a failed DB.

**Detection warning signs:**
- Log shows DB errors but `dropped_count` does not increase (events lost silently)
- Dead letter file exists and is non-empty
- Circuit breaker has tripped (module status shows `db_healthy=False`)

**Assigned phase:** Phase 2 (Batching and buffering logic) — error handling must be designed alongside batching.

---

### P5: Memory Leaks from Unbounded Buffers
**What goes wrong:** The internal buffer (a Python `list` or `deque` holding events before batch flush) grows without bound during a DB slowdown or outage. Even after the DB recovers, the retained memory may not be released to the OS due to Python's memory allocator behavior.

**Why it happens:**
- `list` and `deque` over-allocate during growth and never shrink
- Python's pymalloc holds freed memory in arenas for reuse
- During burst traffic, the buffer temporarily grows large; after draining, the process RSS remains elevated
- Long-running trading engines (weeks/months) accumulate this bloat

**Consequences:**
- Gradual memory growth → OOM kill after days/weeks
- False positive in memory monitoring alerts
- Engine restart required to reclaim memory (loses in-flight events)

**Prevention:**
1. **Use bounded buffers:** `collections.deque(maxlen=N)` automatically drops oldest when full. This is safer than unbounded growth.
2. **Periodic buffer replacement:** After a large drain, replace the buffer list with a new empty one: `self._buffer = []`. The old list becomes eligible for GC.
3. **Monitor RSS vs buffer size:** If `process_memory >> buffer_size * avg_event_size`, investigate fragmentation.
4. **Cap total memory:** Set a hard limit (e.g., 500MB) on the persistence module's buffer. If exceeded, drop new events and alert.

**Detection warning signs:**
- RSS grows over days while buffer size is stable
- `dropped_count` spikes during recovery from DB outage
- Process killed by OOM killer

**Assigned phase:** Phase 2 (Batching and buffering logic) — buffer implementation detail.

---

### P6: Shutdown Data Loss (Buffer Not Flushed)
**What goes wrong:** When the engine or module shuts down (graceful stop, SIGTERM, or crash), events sitting in the internal buffer are lost because they were never written to the DB.

**Why it happens:**
- `stop()` sets `_running = False` and joins threads with a 2-second timeout
- The writer thread may be in the middle of a long batch insert and does not complete
- No explicit flush of the pending buffer before socket teardown
- SIGTERM handler not installed; Python's default just raises `KeyboardInterrupt`

**Consequences:**
- Events from the last N seconds before shutdown are permanently lost
- In trading, this could be the final order fills, position updates, or risk events
- Replay from the DB is incomplete for that session

**Prevention:**
1. **Graceful shutdown sequence in `stop()`:**
   a. Set `_running = False` (stops accepting new events from ZMQ)
   b. Signal the writer thread to flush remaining buffer
   c. Wait for writer thread to complete (with a longer timeout, e.g., 30s)
   d. Close DB connection
   e. Close ZMQ sockets
2. **SIGTERM handler:** Register a signal handler that calls `module.stop()` with flush.
3. **Shutdown checkpoint:** Write a special `shutdown` event to the DB with timestamp and remaining buffer count. This makes it obvious during replay that data may be missing.
4. **WAL for SQLite:** SQLite's WAL mode ensures committed transactions survive crash. But uncommitted buffered events still need the flush above.

**Detection warning signs:**
- Gap in event timestamps at shutdown time
- `shutdown` checkpoint event missing from DB
- Log shows "Writer thread did not exit cleanly" warnings

**Assigned phase:** Phase 3 (Module lifecycle and integration) — shutdown behavior is part of lifecycle design.

---

## ClickHouse-Specific Pitfalls

### P7: Async Insert Misconfiguration
**What goes wrong:** Using ClickHouse's `async_insert=1` without understanding the durability/throughput tradeoff. Either data is lost on server crash (`wait_for_async_insert=0`) or latency is unacceptable (`wait_for_async_insert=1` with default timeouts).

**Why it happens:**
- `wait_for_async_insert=0` (default in some drivers): client gets ACK immediately after server buffers the data. If the server crashes before flush to disk, data is lost.
- `wait_for_async_insert=1`: client blocks until data is written to a MergeTree table part. With default `async_insert_busy_timeout_ms=200`, this can add 200ms+ latency per batch.
- `async_insert_use_adaptive_busy_timeout=1` (default since ClickHouse 24.3) overrides manual timeout settings, making behavior non-deterministic.

**Consequences:**
- With `wait_for_async_insert=0`: silent data loss on ClickHouse server restart
- With `wait_for_async_insert=1`: throughput drops because each batch blocks until server-side flush
- Adaptive timeout makes latency unpredictable — bad for trading systems requiring deterministic behavior

**Prevention:**
1. **For trading events (financial records):** Use `wait_for_async_insert=1` with explicit `async_insert_busy_timeout_ms=5000` (5s max wait). Set `async_insert_use_adaptive_busy_timeout=0` for deterministic behavior.
2. **For metrics/telemetry:** `wait_for_async_insert=0` is acceptable if small data loss is tolerable.
3. **Prefer client-side batching:** Buffer to 10,000+ rows in the module, then do a single synchronous `INSERT`. This gives durability without relying on server-side async insert mechanics.
4. **Monitor `system.asynchronous_insert_log`:** Verify actual flush behavior matches expectations.

**Detection warning signs:**
- Events acknowledged by module but missing from DB after server restart
- Batch flush latency varies wildly (adaptive timeout interference)
- `system.asynchronous_insert_log` shows high rejection rates

**Assigned phase:** Phase 4 (ClickHouse backend implementation) — configuration is backend-specific.

---

### P8: ClickHouse "Too Many Parts" Error
**What goes wrong:** Small batch sizes or high insert frequency cause ClickHouse to create more data parts than the background merge process can consolidate. The server rejects new inserts with `TOO_MANY_PARTS`.

**Why it happens:**
- Each `INSERT` creates at least one data part on disk
- Default threshold: 300 active parts per partition triggers the error
- Trading events with `toYYYYMMDD()` partitioning create one partition per day, but if batch sizes are small (<1000 rows), parts accumulate faster than merges
- High-frequency events (ticks, order book updates) exacerbate the problem

**Consequences:**
- Insert failures cascade into buffer overflow and event drops
- Module enters retry loop, worsening the problem
- ClickHouse server CPU/memory spikes from merge backlog

**Prevention:**
1. **Minimum batch size:** 10,000 rows per insert. Target 100,000 for high-throughput scenarios.
2. **Partition key choice:** Use `toYYYYMM(event_time)` instead of `toYYYYMMDD()` to reduce partition cardinality. For sub-day granularity, use `toStartOfHour()` only if necessary.
3. **Monitor parts count:**
   ```sql
   SELECT partition, count() FROM system.parts WHERE table='events' AND active=1 GROUP BY partition
   ```
4. **Server-side tuning** (if self-hosted): Increase `background_pool_size` and `background_merges_mutations_concurrency_ratio`.

**Detection warning signs:**
- `TOO_MANY_PARTS` exceptions in module logs
- `system.parts` shows >100 active parts per partition
- Insert latency increases as merge queue backs up

**Assigned phase:** Phase 4 (ClickHouse backend implementation) — schema and batch sizing decisions.

---

### P9: ClickHouse Connection Limits and Pool Exhaustion
**What goes wrong:** The module creates a new connection per batch insert or fails to close connections properly. ClickHouse server reaches `max_connections` (default 4096) and rejects new connections.

**Why it happens:**
- `clickhouse-connect` uses urllib3 connection pools. Default pool size is 8 connections per host. If multiple modules or threads share a pool, contention occurs.
- `clickhouse-driver` has no built-in connection pool. Each `Client()` creates a new TCP connection.
- Connection leaks from unhandled exceptions leaving sockets in CLOSE_WAIT state.

**Consequences:**
- Intermittent `ConnectionError` exceptions
- Module retries fail because no connections available
- Other services (Grafana, admin tools) cannot connect to ClickHouse

**Prevention:**
1. **Use a single client instance per module:** `clickhouse-connect` client is thread-safe and reuses HTTP connections.
2. **Configure pool size explicitly:**
   ```python
   from clickhouse_connect.driver import httputil
   pool_mgr = httputil.get_pool_manager(maxsize=4, num_pools=1)
   client = clickhouse_connect.get_client(..., pool_mgr=pool_mgr)
   ```
3. **Close client on shutdown:** Call `client.close()` in the module's `stop()` method.
4. **Set connection timeouts:** `connect_timeout=10`, `send_receive_timeout=30` to prevent hung connections.

**Detection warning signs:**
- `ConnectionError` or `TimeoutError` in logs
- `system.metrics` shows `HTTPConnection` or `TCPConnection` near `max_connections`
- `lsof` shows many sockets in CLOSE_WAIT state

**Assigned phase:** Phase 4 (ClickHouse backend implementation) — connection management is backend-specific.

---

## SQLite-Specific Pitfalls

### P10: SQLite "Database Is Locked" with Concurrent Writers
**What goes wrong:** Multiple threads or processes attempt to write to the SQLite database simultaneously. One holds the write lock; others get `sqlite3.OperationalError: database is locked`.

**Why it happens:**
- SQLite WAL mode allows concurrent reads but only **one writer at a time**
- The persistence module's writer thread is the only intended writer, but:
  - Test code may create separate connections
  - Admin/debug tools may open the DB file
  - Multiple module instances (if misconfigured) may write to the same file
- Default `timeout=5.0` seconds is often too short under burst load

**Consequences:**
- Transient write failures that retry logic may or may not recover
- If retry fails, events go to dead letter or are dropped
- Test flakiness — tests pass individually but fail in parallel

**Prevention:**
1. **Single writer thread:** Only one thread ever holds the SQLite connection. All writes go through this thread.
2. **Use `BEGIN IMMEDIATE`:** Acquire the write lock at transaction start, not at first write. This prevents upgrade deadlocks.
   ```python
   conn.execute("BEGIN IMMEDIATE")
   # ... inserts ...
   conn.commit()
   ```
3. **Set `busy_timeout` high:** `PRAGMA busy_timeout=10000` (10 seconds) for production.
4. **Isolate test databases:** Each test gets its own temp file. Never share a SQLite file across parallel tests.
5. **Connection check:** On startup, verify no other process holds a write lock by attempting `BEGIN IMMEDIATE` and rolling back.

**Detection warning signs:**
- `sqlite3.OperationalError: database is locked` in logs
- Write latency spikes to 5-10 seconds (waiting for lock)
- Tests fail intermittently with database lock errors

**Assigned phase:** Phase 5 (SQLite backend implementation) — concurrency model is SQLite-specific.

---

### P11: SQLite WAL File Growth and Checkpoint Starvation
**What goes wrong:** The `-wal` file grows unbounded because checkpoints cannot run. This happens when:
- Long-running readers (e.g., a SELECT query in a test or admin tool) hold a snapshot, blocking checkpoint
- The writer thread never issues `PRAGMA wal_checkpoint(TRUNCATE)` or `PASSIVE`
- High write rate with infrequent commits

**Why it happens:**
- WAL checkpoints need to transition from SHARED to EXCLUSIVE lock
- Any active reader blocks this transition
- Default `wal_autocheckpoint=1000` (pages) may be too infrequent for high write rates
- The `-wal` file can grow to many GBs, consuming disk space and slowing reads

**Consequences:**
- Disk space exhaustion
- Read performance degrades (must scan large WAL)
- Recovery time after crash increases (must replay large WAL)

**Prevention:**
1. **Periodic checkpointing:** After every N commits or M minutes, issue `PRAGMA wal_checkpoint(PASSIVE)`. If it returns `SQLITE_BUSY`, retry later — do not block the writer thread.
2. **Avoid long-running readers in production:** Admin queries should use `PRAGMA busy_timeout` and short transactions.
3. **Monitor WAL file size:** Alert if `-wal` file exceeds 1GB.
4. **Set `wal_autocheckpoint` appropriately:** For event ingestion, `PRAGMA wal_autocheckpoint=100` (smaller, more frequent checkpoints) may be better than default.

**Detection warning signs:**
- `-wal` file size growing continuously
- Read queries slowing down over time
- Disk usage alerts

**Assigned phase:** Phase 5 (SQLite backend implementation) — WAL management is SQLite-specific.

---

### P12: SQLite Schema Rigidity (No ALTER COLUMN)
**What goes wrong:** SQLite has limited `ALTER TABLE` support — no `DROP COLUMN`, `ALTER COLUMN`, or `RENAME COLUMN` in older versions. If the event schema evolves (new fields added), migrating the SQLite backend is painful.

**Why it happens:**
- SQLite added `DROP COLUMN` in 3.35.0 (2021), but Python's bundled sqlite3 may use older versions on some systems
- No native column type modification
- The persistence module stores events with a JSON/text payload column, but if structured columns are used, schema changes require table recreation

**Consequences:**
- Schema migration requires creating a new table, copying data, dropping old table, renaming — complex and error-prone
- Tests with existing DB files fail after schema changes
- Dev/prod schema divergence

**Prevention:**
1. **Store event payload as JSON/text:** Use a single `payload TEXT` column (or `BLOB` for msgpack) rather than one column per event field. This makes the schema event-type-agnostic.
2. **Minimal structured columns:** Only `timestamp`, `event_type`, `sender`, `module_id` as dedicated columns. Everything else in payload.
3. **Version the schema:** Store a `schema_version` table. On connect, check version and apply migrations programmatically.
4. **Recreate on version mismatch:** For dev/testing, if schema version doesn't match, drop and recreate tables.

**Detection warning signs:**
- `OperationalError: no such column` after code update
- Migration scripts fail on SQLite but work on ClickHouse
- Dev database files must be manually deleted after schema changes

**Assigned phase:** Phase 5 (SQLite backend implementation) — schema design decision.

---

## Integration Pitfalls

### P13: Schema Drift Between ClickHouse and SQLite Backends
**What goes wrong:** The ClickHouse and SQLite backends use different schemas, data types, or column names. Code that works with one backend fails or produces different results with the other.

**Why it happens:**
- ClickHouse uses `DateTime`, `Float64`, `String`, `Array` types
- SQLite uses `INTEGER`, `REAL`, `TEXT`, `BLOB` — no native array or datetime types
- ClickHouse supports `DEFAULT` expressions and `MATERIALIZED` columns; SQLite does not
- Column names with ClickHouse keywords (e.g., `index`, `table`) need quoting differently
- The abstract backend interface does not fully hide these differences

**Consequences:**
- Integration tests pass with SQLite but production fails with ClickHouse
- Event serialization/deserialization round-trips produce different values
- Query code for replay/analysis must be written twice

**Prevention:**
1. **Abstract schema definition:** Define the event table schema in a backend-agnostic way (Python dataclass or dict), then translate to backend-specific DDL.
   ```python
   EVENT_TABLE_SCHEMA = {
       "timestamp": {"ch": "DateTime64(3)", "sqlite": "REAL"},
       "event_type": {"ch": "LowCardinality(String)", "sqlite": "TEXT"},
       "payload": {"ch": "String", "sqlite": "TEXT"},
   }
   ```
2. **Shared serialization:** Use the same `msgpack` serialization for the `payload` column in both backends. This ensures the stored bytes are identical.
3. **Backend-agnostic test fixtures:** Run the same test suite against both backends. Parameterize tests with `@pytest.mark.parametrize("backend", [ClickHouseBackend, SQLiteBackend])`.
4. **DDL generation:** Each backend implements `create_table_sql()` that translates the abstract schema. Never hand-write DDL for both.

**Detection warning signs:**
- ClickHouse integration tests fail while SQLite passes (or vice versa)
- `payload` deserialized from SQLite differs from ClickHouse
- Column type mismatches in error messages

**Assigned phase:** Phase 1 (Core persistence module skeleton) — the abstract backend interface must be designed to prevent drift.

---

### P14: TycheModule Lifecycle Mismatch
**What goes wrong:** The persistence module's lifecycle does not align with `TycheModule`'s `start()`/`stop()` contract. The module registers with the engine before the DB connection is ready, or stops accepting events before flushing the buffer.

**Why it happens:**
- `TycheModule.start()` calls `_start_workers()` which calls `_register()` before DB connection is established
- If DB connection fails, the module is registered with the engine but cannot persist events
- `stop()` joins threads with 2-second timeout, which may be insufficient for a large buffer flush
- The engine's heartbeat monitoring may mark the module as dead during a long DB flush

**Consequences:**
- Module appears healthy to engine but silently drops events
- Shutdown loses buffered events
- Module gets unregistered by heartbeat timeout during slow flush

**Prevention:**
1. **Connect DB before registration:** In `start()`, establish the DB connection first. Only register with the engine after confirming the connection is alive (e.g., `SELECT 1`).
2. **Failed DB = failed start:** If DB connection fails, `start()` should raise an exception or return `False`. The module should not register with the engine in a degraded state.
3. **Extend stop timeout:** Override `stop()` to use a longer join timeout (30s) for the writer thread, or implement a cooperative shutdown where the writer signals completion.
4. **Heartbeat during flush:** The writer thread should not block the heartbeat thread. Ensure heartbeat and writer are separate threads.

**Detection warning signs:**
- Module registered but no events in DB
- `stop()` logs "Writer thread did not exit cleanly"
- Heartbeat timeout during shutdown

**Assigned phase:** Phase 3 (Module lifecycle and integration) — lifecycle is integration-specific.

---

### P15: Event Filtering Done in DB Writer Instead of ZMQ Subscription
**What goes wrong:** The persistence module subscribes to ALL events via ZMQ, then filters which ones to persist in the Python handler. This wastes CPU, network, and buffer space on events that will be discarded.

**Why it happens:**
- `TycheModule._subscribe_to_interfaces()` subscribes to all handler topics
- If the module has `on_data`, `on_order`, etc., it receives all of them
- Filtering happens after deserialization and enqueue — too late
- The engine's XPUB socket still sends the events to this module

**Consequences:**
- Unnecessary network traffic between engine and persistence module
- Buffer space wasted on discarded events
- CPU wasted on deserialization of discarded events
- At high throughput, this overhead is significant

**Prevention:**
1. **Filter at subscription time:** Only subscribe to topics that match the configured filter. If the config says "persist only `trade` and `order` events", only register `on_trade` and `on_order` handlers.
2. **Dynamic re-subscription:** If the filter config changes at runtime, close and re-open the SUB socket with new subscriptions. (Note: ZMQ SUB subscriptions are cumulative; unsubscribing requires `setsockopt(zmq.UNSUBSCRIBE, topic)`).
3. **Engine-side filtering (future):** If the engine supports per-module topic filtering at the XPUB level, use it. This is the most efficient but requires engine changes.

**Detection warning signs:**
- High network throughput between engine and persistence module but low DB write rate
- Buffer drops occur on events that should be filtered out
- CPU usage high in `_event_receiver` but low in writer thread

**Assigned phase:** Phase 3 (Module lifecycle and integration) — subscription logic is part of module setup.

---

## Prevention Strategies Summary

| Pitfall | Primary Prevention | Secondary Prevention | Detection |
|---------|-------------------|----------------------|-----------|
| P1: Blocking event loop | Dedicated writer thread | Never DB I/O in `on_*` | Event counts stall, latency spikes |
| P2: Buffer overflow | Bounded queue with `maxsize` | Backpressure signal | `dropped_count` metric, memory growth |
| P3: Per-event round-trip | Batch by size AND time | Multi-row parameterized inserts | Low throughput, high CPU |
| P4: Silent error drops | Confirm before dequeue | Retry + dead letter + circuit breaker | Dead letter file non-empty |
| P5: Memory leaks | Bounded buffers, periodic replacement | Memory cap, monitor RSS | RSS >> buffer_size |
| P6: Shutdown data loss | Flush buffer before socket teardown | SIGTERM handler, shutdown checkpoint | Gap in timestamps at shutdown |
| P7: Async insert misconfig | Client-side batching preferred | Explicit timeout settings, adaptive=0 | Missing events after restart |
| P8: Too many parts | Batch >= 10K rows | Careful partition key choice | `TOO_MANY_PARTS` error |
| P9: Connection pool exhaustion | Single client instance | Explicit pool size, close on stop | Connection errors, CLOSE_WAIT sockets |
| P10: SQLite locked | Single writer thread | `BEGIN IMMEDIATE`, high `busy_timeout` | Lock errors, test flakiness |
| P11: WAL growth | Periodic `wal_checkpoint` | Monitor WAL size, avoid long readers | Growing `-wal` file |
| P12: SQLite schema rigidity | JSON payload column | Schema versioning | `no such column` errors |
| P13: Schema drift | Abstract schema definition | Shared msgpack payload, parameterized tests | Backend-specific test failures |
| P14: Lifecycle mismatch | DB connect before registration | Longer stop timeout, cooperative shutdown | Module registered but no DB writes |
| P15: Inefficient filtering | Filter at ZMQ subscription | Dynamic re-subscription | High network, low DB rate |

---

## Phase Assignments

### Phase 1: Core Persistence Module Skeleton
**Must address:** P1 (blocking event loop), P2 (buffer overflow), P13 (schema drift)
**Design decisions:**
- Threading model: ZMQ receiver thread + dedicated DB writer thread + bounded queue between them
- Abstract backend interface with schema translation
- Buffer size and capacity as constructor parameters

### Phase 2: Batching and Buffering Logic
**Must address:** P3 (per-event round-trip), P4 (silent error drops), P5 (memory leaks)
**Design decisions:**
- Batch flush triggers: size threshold + time threshold
- Error classification: transient vs permanent
- Retry with backoff, dead letter file, circuit breaker
- Buffer implementation: bounded `deque` with periodic replacement

### Phase 3: Module Lifecycle and Integration
**Must address:** P6 (shutdown data loss), P14 (lifecycle mismatch), P15 (inefficient filtering)
**Design decisions:**
- `start()` connects DB before engine registration
- `stop()` flushes buffer with extended timeout before socket teardown
- SIGTERM handler for graceful shutdown
- Event filtering at subscription time, not in handler

### Phase 4: ClickHouse Backend Implementation
**Must address:** P7 (async insert), P8 (too many parts), P9 (connection limits)
**Design decisions:**
- Use `clickhouse-connect` with single client instance
- Client-side batching as primary strategy (async insert as fallback)
- Explicit connection pool sizing
- Partition key: `toYYYYMM(timestamp)` or `toYYYYMMDD(timestamp)`

### Phase 5: SQLite Backend Implementation
**Must address:** P10 (database locked), P11 (WAL growth), P12 (schema rigidity)
**Design decisions:**
- Single writer thread with `BEGIN IMMEDIATE`
- `PRAGMA busy_timeout=10000`
- Periodic `wal_checkpoint(PASSIVE)`
- JSON/text payload column for schema flexibility
- Per-test isolated database files

---

## Sources

- [ClickHouse Async Inserts Official Docs](https://clickhouse.com/docs/optimize/asynchronous-inserts) — HIGH confidence
- [ClickHouse Selecting an Insert Strategy](https://clickhouse.com/docs/best-practices/selecting-an-insert-strategy) — HIGH confidence
- [ClickHouse Common Getting Started Issues](https://clickhouse.com/blog/common-getting-started-issues-with-clickhouse) — HIGH confidence
- [Altinity Async Inserts Knowledge Base](https://kb.altinity.com/altinity-kb-queries-and-syntax/async-inserts/) — HIGH confidence
- [ClickHouse "Too Many Parts" Problem](https://bigdataboutique.com/blog/clickhouse-too-many-parts) — MEDIUM confidence
- [ClickHouse Python Drivers — Altinity](https://kb.altinity.com/altinity-kb-integrations/clickhouse_python_drivers/) — HIGH confidence
- [SQLite WAL Mode Official Docs](https://sqlite.org/wal.html) — HIGH confidence
- [SQLite WAL Mode & Concurrency](https://systeminternals.dev/sqlite/wal-mode/) — MEDIUM confidence
- [SkyPilot: Abusing SQLite for Concurrency](https://blog.skypilot.co/abusing-sqlite-to-handle-concurrency/) — MEDIUM confidence
- [SQLite Single-Writer Architecture](https://www.bugsink.com/blog/database-transactions/) — MEDIUM confidence
- [How to Prevent SQLite Database Is Locked](https://lab.abilian.com/Tech/Databases%20%26%20Persistence/sqlite/How%20to%20prevent%20the%20%22SQLite%20database%20is%20locked%22%20error/) — MEDIUM confidence
- [Python ThreadPoolExecutor Blocking I/O](https://dev.to/aaron_rose_0787cc8b4775a0/the-secret-life-of-python-the-executor-running-blocking-code-without-blocking-2nih) — MEDIUM confidence
- [Python Queue Memory Leak — bugs.python.org](https://bugs.python.org/issue43911) — HIGH confidence
- [n8n Unbounded EventEmitter Memory Leak](https://github.com/n8n-io/n8n/issues/28181) — MEDIUM confidence
- [Rust Unbounded Channel Memory Leak](https://github.com/zesterer/flume/issues/146) — MEDIUM confidence
- [Event-Driven Architecture Error Handling](https://www.geeksforgeeks.org/system-design/error-handling-in-event-driven-architecture/) — MEDIUM confidence
- [Prevent Data Loss in Event-Driven Systems](https://www.linkedin.com/posts/raul-junco_i-love-asynchronous-communication-its-scalable-activity-7344698918061957120-y33I) — LOW confidence
- [How to Avoid Losing Events on Shutdown](https://softwareengineering.stackexchange.com/questions/396415/how-to-avoid-losing-events-kept-in-memory-on-application-shutdown) — MEDIUM confidence
