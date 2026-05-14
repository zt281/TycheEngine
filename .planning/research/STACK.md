# Technology Stack: Database Persistence Module

**Project:** TycheEngine v1.0 Persistence Module
**Researched:** 2026-05-14
**Confidence:** HIGH (verified via PyPI API, official docs, community benchmarks)

---

## Stack Overview

The persistence module adds database-backed event storage to TycheEngine. It is a write-only module (reads deferred to v2) that subscribes to engine events via the existing `TycheModule` pub/sub system and persists them in batches.

| Layer | Technology | Version | Why |
|-------|-----------|---------|-----|
| **ClickHouse driver** | `clickhouse-connect` | `>=0.7.0,<1.0.0` | Official HTTP driver; thread-safe with `autogenerate_session_id=False`; built-in compression; batch insert API |
| **SQLite driver** | `sqlite3` (stdlib) | built-in | Zero-config fallback; no extra dependency; `executemany` for batching |
| **Batch buffering** | In-memory list + timer thread | custom | Dual-threshold (size + time) flush; keeps engine dispatch path non-blocking |
| **Schema definition** | DDL SQL strings | custom | No ORM needed; single events table per backend; schema migrations out of scope |

---

## Database Drivers

### ClickHouse: `clickhouse-connect` (Official)

**Selected version constraint:** `>=0.7.0,<1.0.0`

**Rationale:**
- The project requires Python 3.9+ (per `pyproject.toml`). `clickhouse-connect` 1.0.0 (released April 2026) **dropped Python 3.9 support entirely** (requires Python 3.10+). The 0.7.x through 0.15.x series all support Python 3.9.
- The existing `pyproject.toml` already specifies `clickhouse-connect>=0.7.0` under `[project.optional-dependencies] persistence`.
- `clickhouse-connect` is the official ClickHouse Inc. driver. It uses HTTP (port 8123) which is more firewall-friendly and proxy-compatible than the native TCP protocol used by `clickhouse-driver`.

**Core dependencies (auto-installed):**
- `certifi`
- `urllib3>=1.26`
- `pytz`
- `zstandard`
- `lz4`

**Batch insert API:**
```python
import clickhouse_connect

client = clickhouse_connect.get_client(
    host='localhost',
    port=8123,
    username='default',
    password='',
    autogenerate_session_id=False,  # REQUIRED for thread safety
)

# Batch insert with list of tuples
client.insert(
    'events',
    data=[(ts, sender, event, payload_json), ...],
    column_names=['timestamp', 'sender', 'event_type', 'payload'],
)
```

**Thread safety:** The `clickhouse-connect` client is thread-safe **only when `autogenerate_session_id=False`**. With the default session ID, concurrent queries raise `ProgrammingError`. The persistence module runs in a single background thread (the event receiver thread from `TycheModule`), so thread safety is manageable, but setting this flag is mandatory for correctness.

**Connection pooling:** Built-in via `urllib3`. The default pool manager is sufficient for a single-module, single-threaded write workload. For higher concurrency, a custom pool manager can be passed:
```python
from clickhouse_connect.driver import httputil
pool_mgr = httputil.get_pool_manager(maxsize=10, num_pools=4)
client = clickhouse_connect.get_client(..., pool_mgr=pool_mgr)
```

**Why NOT `clickhouse-driver`:**
- Community-maintained (not official)
- Uses native TCP protocol (port 9000) — often blocked by firewalls
- **NOT thread-safe** — single connection is synchronous; requires manual pooling
- No built-in connection pooling
- Smaller ecosystem; `clickhouse-connect` is the converged standard

### SQLite: `sqlite3` (stdlib)

**No extra dependency needed.** Python's standard library `sqlite3` module is sufficient.

**Batch insert API:**
```python
import sqlite3

conn = sqlite3.connect('tyche_events.db')
conn.execute('PRAGMA journal_mode=WAL')      # Better concurrency
conn.execute('PRAGMA synchronous=NORMAL')    # Speed/safety balance

# executemany is 50-100x faster than individual execute() calls
conn.executemany(
    "INSERT INTO events (timestamp, sender, event_type, payload) VALUES (?, ?, ?, ?)",
    batch_data,
)
conn.commit()
```

**Key PRAGMAs for performance:**
| PRAGMA | Effect | Recommendation |
|--------|--------|----------------|
| `journal_mode=WAL` | Write-Ahead Logging | Always enable; better read concurrency |
| `synchronous=NORMAL` | Sync less aggressively | Good balance; use OFF only if crash durability is acceptable |
| `cache_size=-64000` | 64MB page cache | Helps with large transactions |

---

## Connection Management

### ClickHouse Connection

| Aspect | Approach |
|--------|----------|
| **When to connect** | In `PersistenceModule.start()` — after successful engine registration |
| **When to disconnect** | In `PersistenceModule.stop()` — after final buffer flush |
| **Connection reuse** | Single `Client` instance held for module lifetime |
| **Thread safety flag** | `autogenerate_session_id=False` mandatory |
| **Health check** | Lightweight `SELECT 1` query before each batch flush |
| **Reconnection** | On failure, retry with exponential backoff; drop events after max retries |

### SQLite Connection

| Aspect | Approach |
|--------|----------|
| **When to connect** | In `PersistenceModule.start()` |
| **Connection mode** | Single connection held open for module lifetime |
| **Thread safety** | SQLite connections should not be shared across threads. Since the persistence module uses the `TycheModule` event receiver thread for all DB operations, a single connection per module instance is safe. |
| **PRAGMA setup** | Apply WAL + NORMAL sync on connection open |

### Backend Selection Strategy

The module should accept a configuration dict:
```python
{
    "backend": "clickhouse",  # or "sqlite"
    "clickhouse": {
        "host": "localhost",
        "port": 8123,
        "username": "default",
        "password": "",
        "database": "tyche",
    },
    "sqlite": {
        "path": "tyche_events.db",
    },
}
```

Default to SQLite if no config provided (zero-config dev mode).

---

## Batch Insert Strategy

### Why Batching Is Critical

ClickHouse performance degrades severely with small inserts. The official recommendation is **minimum 100,000 rows per INSERT**, ideally 500,000+. Even SQLite benefits enormously from batching (`executemany` is 50-100x faster than per-row `execute`).

Since TycheEngine events arrive individually via ZeroMQ, the persistence module must buffer them in memory and flush in batches.

### Dual-Threshold Flush Pattern

```python
BATCH_SIZE = 1000       # Rows: conservative default (tune up for production)
FLUSH_INTERVAL = 5.0    # Seconds: flush even if batch not full
```

**Rationale for 1,000 row default:** The engine's event volume in early deployments is unknown. A 1,000-row default provides a balance between latency (max 5 seconds) and throughput. Users can tune `BATCH_SIZE` upward to 100,000+ for high-volume production. The flush interval ensures events do not sit indefinitely in the buffer during low-volume periods.

**Why NOT 100,000 as default:** The persistence module is a `TycheModule` subscribing to all events. In a quiet dev environment, it might take hours to accumulate 100,000 events. The 5-second time threshold ensures bounded latency regardless of volume.

### Buffer Implementation

- In-memory `list` of row tuples
- Append on each event (O(1) amortized)
- Lock with `threading.Lock` (the event receiver thread and a background flush timer thread both access the buffer)
- On flush: swap buffer under lock, then write outside lock to avoid blocking event reception

### Graceful Shutdown

On `stop()`:
1. Signal flush timer thread to exit
2. Acquire buffer lock
3. Flush any remaining rows
4. Close database connection
5. Call `super().stop()` for engine disconnection

---

## Schema Tools

### Decision: No ORM, No Migration Framework

**Rationale:**
- The milestone scope explicitly excludes schema migration management ("Initial schema setup only, no versioning")
- Only ONE table is needed (`events`)
- Using SQLAlchemy or an ORM adds unnecessary dependencies and abstraction overhead
- Raw DDL strings are simpler, faster, and fully sufficient

### ClickHouse Schema

```sql
CREATE TABLE IF NOT EXISTS events (
    timestamp DateTime64(6),
    sender String,
    event_type LowCardinality(String),
    payload String  -- JSON as string
) ENGINE = MergeTree()
ORDER BY (event_type, timestamp)
```

**Why `MergeTree`:** Default ClickHouse table engine; optimized for time-series append-only workloads.
**Why `LowCardinality(String)` for event_type:** Event types are from a small, fixed set (see `events.py`). `LowCardinality` provides compression and query speedup.
**Why `DateTime64(6)`:** Microsecond precision for event timestamps.

### SQLite Schema

```sql
CREATE TABLE IF NOT EXISTS events (
    timestamp REAL,           -- Unix timestamp with fractional seconds
    sender TEXT,
    event_type TEXT,
    payload TEXT              -- JSON as string
);
CREATE INDEX IF NOT EXISTS idx_events_type_time ON events (event_type, timestamp);
```

**Why `REAL` for timestamp:** SQLite has no native DateTime type. `REAL` (Julian day) or `INTEGER` (Unix epoch) are the conventions. `REAL` preserves sub-second precision.

---

## Dependencies to Add

### Production Dependencies

| Package | Version Constraint | Purpose | Install |
|---------|-------------------|---------|---------|
| `clickhouse-connect` | `>=0.7.0,<1.0.0` | ClickHouse HTTP driver | `pip install clickhouse-connect` |

**Note on version pinning:** `<1.0.0` is required because `clickhouse-connect` 1.0.0 (April 2026) dropped Python 3.9 support. The project specifies `requires-python = ">=3.9"`. The 0.7.x through 0.15.x series all support Python 3.9. When the project upgrades to Python 3.10+, the constraint can be relaxed.

**Core transitive dependencies (no action needed):**
- `certifi`, `urllib3>=1.26`, `pytz`, `zstandard`, `lz4` — all installed automatically with `clickhouse-connect`

### Optional Dependencies (already in pyproject.toml)

The `pyproject.toml` already has a `persistence` extra:
```toml
[project.optional-dependencies]
persistence = [
    "clickhouse-connect>=0.7.0",
]
```

**Recommendation:** Update the constraint to `"clickhouse-connect>=0.7.0,<1.0.0"` to prevent accidental installation of the Python 3.10-only 1.0.0 release.

### Dev/Test Dependencies

No new dev dependencies needed. Existing test stack is sufficient:
- `pytest>=7.4.0` — unit and integration tests
- `pytest-timeout>=2.2.0` — prevent hung DB tests
- `pytest-cov>=4.1.0` — coverage reporting

For integration tests, use:
- `pytest` fixtures with mocked `clickhouse_connect.get_client()` for unit tests
- A real SQLite file for integration tests (zero external infrastructure)
- Optional: Docker-based ClickHouse for CI integration tests (out of scope for this milestone's test requirements)

---

## Dependencies to Avoid

| Package | Why Avoid |
|---------|-----------|
| `clickhouse-driver` | Not official; native TCP (firewall-unfriendly); NOT thread-safe; no built-in pooling. The ecosystem has converged on `clickhouse-connect`. |
| `clickhouse-pool` | Unnecessary. `clickhouse-connect` has built-in `urllib3` pooling. The persistence module is single-threaded for DB writes. |
| `SQLAlchemy` + `clickhouse-sqlalchemy` | Overkill for a single table with no migrations. Adds heavy dependency chain. |
| `pandas` | Not needed for the persistence module. The module receives raw events and inserts row tuples. `pandas` is an optional extra of `clickhouse-connect` but not required for `client.insert()` with list data. |
| `numpy` | Same as above — not needed for simple batch inserts. |
| `alembic` / any migration tool | Out of scope per PROJECT.md: "Schema migration management — Initial schema setup only, no versioning" |
| `asyncio` / `aiohttp` | The existing `TycheModule` architecture is threading-based. Adding async would require rearchitecting the module base. The sync `clickhouse-connect` client is sufficient. |

---

## Integration Notes

### Module Architecture

```
TycheModule (base)
    |
    +-- PersistenceModule
            |
            +-- _buffer: list[Row]           # In-memory batch buffer
            +-- _buffer_lock: threading.Lock
            +-- _flush_timer: threading.Thread
            +-- _backend: Backend (protocol)
            |
            +-- ClickHouseBackend
            |       +-- _client: clickhouse_connect.Client
            |
            +-- SQLiteBackend
                    +-- _conn: sqlite3.Connection
```

### Event Flow

1. Engine publishes event via XPUB
2. `PersistenceModule._event_receiver()` receives the event (in background thread)
3. `_dispatch()` calls `on_quote()`, `on_trade()`, etc. — all routed to a single `on_event()` handler
4. `on_event()` appends row tuple to `_buffer` (under lock)
5. If `len(_buffer) >= BATCH_SIZE`, trigger flush
6. `_flush_timer` thread wakes every `FLUSH_INTERVAL` seconds and triggers flush
7. Flush: swap buffer under lock, then call `backend.insert_batch(rows)` outside lock
8. Backend converts rows to driver-specific format and executes batch insert

### Configuration Integration

The module should accept config via constructor (consistent with `TycheModule` pattern):
```python
class PersistenceModule(TycheModule):
    def __init__(
        self,
        engine_endpoint: Endpoint,
        module_id: Optional[str] = None,
        config: Optional[dict] = None,
    ):
        super().__init__(engine_endpoint, module_id)
        self._config = config or {}
        # ...
```

### Error Handling Strategy

| Scenario | Behavior |
|----------|----------|
| ClickHouse unreachable on start | Log error; fallback to SQLite if configured; otherwise module starts but logs warning |
| ClickHouse insert fails mid-run | Retry 3x with exponential backoff; on final failure, drop batch and log error. Do NOT block the event receiver thread. |
| SQLite insert fails | Retry once; on failure, log error and continue. SQLite is local — failures are typically disk-full or locked. |
| Buffer exceeds max size | Drop oldest rows (circular buffer) or block appender. Recommendation: drop oldest with warning log to prevent unbounded memory growth. |

### Testing Strategy

| Test Type | Approach |
|-----------|----------|
| Unit tests | Mock `clickhouse_connect.get_client()`; verify `client.insert()` called with correct data |
| SQLite integration | Real `sqlite3.connect(':memory:')` or temp file; verify round-trip insert/query |
| ClickHouse integration | Mock or optional Docker fixture; skip if ClickHouse not available (`pytest.skip`) |
| Buffer flush | Inject events, verify flush at size threshold and time threshold |
| Graceful shutdown | Verify all buffered events flushed before `stop()` returns |

---

## Sources

- [ClickHouse Python Integration Docs](https://clickhouse.com/docs/integrations/python) — Official driver documentation
- [clickhouse-connect PyPI](https://pypi.org/project/clickhouse-connect/) — Version metadata verified via PyPI API
- [clickhouse-connect vs clickhouse-driver comparison](https://www.tinybird.co/blog/clickhouse-python-example) — Community comparison
- [ClickHouse Python drivers — Altinity KB](https://kb.altinity.com/altinity-kb-integrations/clickhouse_python_drivers/) — Driver feature comparison
- [ClickHouse batch insert best practices](https://oneuptime.com/blog/post/2026-03-31-clickhouse-batch-inserts/view) — Batch size recommendations
- [ClickHouse connection pooling in Python](https://oneuptime.com/blog/post/2026-03-31-clickhouse-connection-pool-python/view) — Thread safety and pooling patterns
- [SQLite executemany performance](https://sqlite.org/forum/info/f832398c19d30a4a) — Community benchmarks
- [PyPI API queries](https://pypi.org/pypi/clickhouse-connect/json) — Version and dependency verification (conducted 2026-05-14)
