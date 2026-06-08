# Architecture Patterns: Persistence Module Integration

**Domain:** TycheEngine — ZeroMQ-based event broker for trading systems
**Researched:** 2026-05-14
**Confidence:** HIGH (based on direct codebase analysis)

---

## Integration Points

The persistence module integrates with TycheEngine at **four distinct points**, all leveraging existing module infrastructure:

### 1. Module Registration (TycheModule Base Class)

`PersistenceModule` inherits from `TycheModule` and uses the existing registration handshake:

- `on_*` methods auto-discovered by `_discover_and_register_handlers()`
- Module sends `REGISTER` via REQ socket, receives ACK with XPUB/XSUB port assignments
- No engine-side changes needed — persistence module is just another subscriber

**Key decision:** The module declares `on_{event}` handlers for every event type it wants to persist. By default, it subscribes to ALL events (using `InterfacePattern.ON` for each event constant in `events.py`). Configurable filtering narrows this to a subset.

### 2. Event Subscription (SUB Socket)

The module receives events through the same XPUB/SUB path as all other modules:

```
Engine XPUB ──► PersistenceModule SUB socket ──► _event_receiver thread ──► _dispatch()
```

The `_event_receiver` thread (already in `TycheModule`) calls `_dispatch()`, which routes to the module's `on_*` handler. The handler receives the deserialized `Message.payload` dict.

**Critical insight:** The handler runs in the `_event_receiver` thread. If the handler blocks on a DB write, the entire event receiver stalls. This is why DB writes **must** be offloaded.

### 3. Engine Topic Queues (Optional Tap Point)

The engine already maintains `_topic_queues: Dict[str, TopicQueue]` — per-topic queues that all events pass through in `_enqueue_from_xsub()`. An alternative integration would tap into these queues directly in the engine process, bypassing the ZMQ subscription path entirely.

**Recommendation:** Use the standard module subscription path (ZMQ SUB socket) rather than engine-internal tapping. Reasons:
- No engine code modifications needed
- Persistence module can run in a separate process (isolation from engine)
- Follows the same pattern as all other modules
- Engine-internal tapping would couple persistence to engine thread model and require careful lock coordination

### 4. Admin Queries (Read-Only, Future)

The engine's admin ROUTER socket (`_admin_worker`) currently supports `STATUS`, `MODULES`, `QUEUES`, `STATS` queries. Persistence module metrics (buffer depth, batch size, DB lag) could be exposed here in a future milestone. Not needed for v1.

---

## New Components

### Component 1: `PersistenceModule` (Module)

**Location:** `src/tyche/persistence/module.py`

**Responsibility:** TycheModule subclass that subscribes to events and writes them to a database backend.

**Key design decisions:**

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Event subscription | All events by default, filter configurable | Easiest to use; filtering is opt-in |
| Handler pattern | Single `on_event` handler for all topics, or per-topic `on_quote`, `on_trade`, etc. | Per-topic handlers are more explicit and allow per-event-type routing logic |
| Durability level | `ASYNC_FLUSH` (module declares this via `DurabilityLevel.ASYNC_FLUSH`) | Matches existing convention; persistence module itself does not need sync guarantees |

**Interface:**

```python
class PersistenceModule(TycheModule):
    def __init__(
        self,
        engine_endpoint: Endpoint,
        backend: PersistenceBackend,
        event_filter: Optional[set[str]] = None,  # None = all events
        batch_size: int = 100,
        flush_interval_ms: float = 100.0,
        module_id: Optional[str] = None,
    ):
        ...

    # Per-event-type handlers (auto-discovered)
    def on_quote(self, payload: dict) -> None: ...
    def on_trade(self, payload: dict) -> None: ...
    # ... etc for all events in events.py

    def start(self) -> None:
        # Connect backend, start flush thread
        ...

    def stop(self) -> None:
        # Signal flush thread, drain buffer, close backend
        ...
```

### Component 2: `PersistenceBackend` (Abstract Base)

**Location:** `src/tyche/persistence/backend.py`

**Responsibility:** Abstract interface for database operations. Decouples `PersistenceModule` from specific database implementations.

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List

class PersistenceBackend(ABC):
    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def write_batch(self, records: List[Dict[str, Any]]) -> None:
        """Write a batch of records atomically."""
        ...

    @abstractmethod
    def ensure_schema(self) -> None:
        """Create tables if they don't exist."""
        ...
```

### Component 3: `ClickHouseBackend` (Concrete Backend)

**Location:** `src/tyche/persistence/backends/clickhouse.py`

**Responsibility:** ClickHouse-specific implementation using `clickhouse-connect`.

**Key characteristics:**
- Connects via HTTP interface (port 8123) or native (port 9000)
- Uses `clickhouse_connect.get_client()` for connection pooling
- Batch inserts via `client.insert()` with columnar data format
- Schema: single `events` table with MergeTree engine, ordered by `(event_type, timestamp)`

**Connection parameters:**
```python
ClickHouseBackend(
    host="localhost",
    port=8123,  # HTTP
    database="tyche",
    username="default",
    password="",
)
```

### Component 4: `SQLiteBackend` (Concrete Backend)

**Location:** `src/tyche/persistence/backends/sqlite.py`

**Responsibility:** SQLite implementation using stdlib `sqlite3`. Zero-config fallback for dev/test.

**Key characteristics:**
- `sqlite3.connect()` with `check_same_thread=False` (module manages its own thread safety)
- `executemany()` for batch inserts
- WAL mode (`PRAGMA journal_mode=WAL`) for better concurrent read performance
- Schema: single `events` table

### Component 5: `WriteBuffer` (Buffer/Batch Manager)

**Location:** `src/tyche/persistence/buffer.py`

**Responsibility:** Thread-safe in-memory buffer that accumulates records and flushes them in batches.

**Design:**
- Two internal buffers: `active` (being written to by handlers) and `pending` (being flushed by background thread)
- Lock-free swap using `threading.Lock` on buffer reference swap only
- Background flush thread wakes on: (a) batch size reached, (b) flush interval elapsed, (c) stop() called

```python
class WriteBuffer:
    def __init__(self, batch_size: int, flush_interval_ms: float):
        self.batch_size = batch_size
        self.flush_interval_ms = flush_interval_ms
        self._active: List[Dict[str, Any]] = []
        self._pending: Optional[List[Dict[str, Any]]] = None
        self._lock = threading.Lock()
        self._flush_event = threading.Event()
        self._flush_thread: Optional[threading.Thread] = None

    def append(self, record: Dict[str, Any]) -> None:
        with self._lock:
            self._active.append(record)
            should_flush = len(self._active) >= self.batch_size
        if should_flush:
            self._flush_event.set()

    def _swap_and_flush(self) -> Optional[List[Dict[str, Any]]]:
        with self._lock:
            if not self._active:
                return None
            self._pending = self._active
            self._active = []
            return self._pending
```

### Component 6: `RecordBuilder` (Schema Mapper)

**Location:** `src/tyche/persistence/record.py`

**Responsibility:** Convert incoming event payloads into normalized database records.

```python
@dataclass
class EventRecord:
    timestamp: float          # nanosecond-precision float (time.time_ns() / 1e9)
    event_type: str           # e.g., "quote", "trade", "order_submit"
    sender: str               # module_id of sender
    payload_json: str         # JSON-serialized payload (for flexible schema)
    # Optional typed columns for common fields
    instrument_id: Optional[str] = None
    price: Optional[float] = None
    quantity: Optional[float] = None
```

---

## Modified Components

**None for v1.** The persistence module is a pure add-on that uses existing `TycheModule` infrastructure without modifying engine, module base, types, or message code.

**Future modifications (v2+):**
- `TycheEngine._admin_worker`: Add persistence metrics to admin queries
- `TycheEngine._enqueue_from_xsub`: Optional engine-side persistence tap for lower latency
- `DurabilityLevel` handling: Engine could respect `SYNC_FLUSH` by waiting for persistence ACK before egress

---

## Data Flow

### Full Data Flow: Event to Database

```
+-------------+     PUB      +------------------+     XSUB      +------------------+
| Any Module  |─────────────►|  TycheEngine     │─────────────►│ _enqueue_from_   |
| (producer)  │  [topic,msg] │  _event_proxy_   │              │ xsub()           |
+-------------+              │  worker          │              +------------------+
                             +------------------+                     │
                                                                       │ enqueue
                                                                       ▼
                                                              +------------------+
                                                              │ _topic_queues    │
                                                              │ [topic]          │
                                                              +------------------+
                                                                       │
                                                                       │ _egress_wakeup.put
                                                                       ▼
+-------------+     SUB      +------------------+     XPUB      +------------------+
| Persistence │◄─────────────│  TycheEngine     │◄─────────────│ _event_egress_   |
| Module      │  [topic,msg] │                  │              │ worker           |
| _event_recv │              +------------------+              +------------------+
+-------------+                     ▲
       │                            │
       │ deserialize                │
       ▼                            │
+-------------+                     │
| _dispatch() │                     │
| on_quote()  │──► WriteBuffer      │
| on_trade()  │    .append(record)  │
+-------------+                     │
       │                            │
       │ swap buffers under lock    │
       ▼                            │
+-------------+                     │
| _flush_     │──► backend.write_  │
| thread      │    batch(records)   │
+-------------+                     │
       │                            │
       │ INSERT / executemany       │
       ▼                            │
+-------------+                     │
| ClickHouse  │                     │
| or SQLite   │─────────────────────┘
+-------------+
```

### Record Lifecycle

1. **Receive:** `_event_receiver` thread gets `[topic, serialized_msg]` from SUB socket
2. **Deserialize:** `deserialize(frames[1])` -> `Message` object
3. **Dispatch:** `_dispatch()` routes to `on_{event_type}(payload)` handler
4. **Build record:** `RecordBuilder.from_message(msg)` creates `EventRecord`
5. **Buffer:** `WriteBuffer.append(record)` adds to active buffer
6. **Swap (under lock):** Flush thread swaps active/pending buffers
7. **Write:** `backend.write_batch(pending_records)` executes batch insert
8. **Ack (implicit):** Buffer cleared; if write fails, records are lost (ASYNC_FLUSH semantics)

---

## Threading Model

### Threads in PersistenceModule

The module inherits 3 threads from `TycheModule._start_workers()`:

| Thread | Source | Purpose | Persistence Impact |
|--------|--------|---------|-------------------|
| `event_recv` | `TycheModule` | Receives events from XPUB | Calls `on_*` handlers — **must not block** |
| `heartbeat_send` | `TycheModule` | Sends heartbeats to engine | Unchanged |
| `job_recv` | `TycheModule` | Receives job responses | Not used by persistence module |

**New thread added by PersistenceModule:**

| Thread | Source | Purpose |
|--------|--------|---------|
| `persist_flush` | `WriteBuffer` | Periodically swaps buffers and writes batches to backend |

### Thread Safety Rules

1. **Event receiver thread** (ZMQ SUB socket reader) calls `on_*` handlers.
   - Handler must return quickly (< 1ms target)
   - Handler appends to `WriteBuffer._active` under a short lock
   - **Never** do DB I/O in the event receiver thread

2. **Flush thread** (background) does all DB I/O.
   - Swaps buffer references under lock (O(1))
   - Releases lock immediately after swap
   - Calls `backend.write_batch()` with the swapped-out pending buffer
   - Handles retry logic for transient DB errors

3. **Backend connection** is owned exclusively by the flush thread.
   - No other thread touches the DB connection
   - This eliminates need for connection pooling in v1

### Concurrency Diagram

```
Event Receiver Thread          Flush Thread
─────────────────────         ─────────────
on_quote(payload):
  record = build_record(...)
  buffer.append(record)  ──►  [sleeping]
       │                           │
       │ acquire _lock             │ wake on _flush_event
       │ _active.append(record)    │
       │ release _lock             │
       │ [check batch_size]        │
       │ _flush_event.set()  ─────►│ _swap_and_flush()
       │                           │   acquire _lock
       │                           │   swap _active / _pending
       │                           │   release _lock
       │                           │ backend.write_batch(_pending)
       │                           │ [clear _pending]
       │                           │ _flush_event.clear()
```

---

## Buffer/Batch Architecture

### Design Goals

| Goal | Approach |
|------|----------|
| Minimize DB round-trips | Batch inserts (default 100 records) |
| Bounded memory | Buffer size limit with DROP_OLDEST backpressure |
| Low latency | Flush interval (default 100ms) ensures data is not held indefinitely |
| Graceful shutdown | `stop()` signals flush thread, waits for drain |

### Buffer States

```
┌─────────────────┐     swap under lock     ┌─────────────────┐
│   _active       │  ─────────────────────► │   _pending       │
│  (growing)      │                         │  (being flushed) │
│  [R, W by       │  ◄───────────────────── │  [R by flush     │
│   recv thread]  │     new empty list      │   thread only]   │
└─────────────────┘                         └─────────────────┘
```

### Flush Triggers

1. **Size trigger:** `len(_active) >= batch_size` -> immediate flush
2. **Time trigger:** `flush_interval_ms` elapsed since last flush -> flush even if buffer is small
3. **Stop trigger:** `stop()` called -> flush whatever remains, then exit

### Backpressure Strategy

When the buffer exceeds `max_buffer_size` (default: `batch_size * 10`):

- **Default:** `DROP_OLDEST` — discard oldest records to make room
- **Rationale:** For persistence, recent data is more valuable than old data in an overload scenario
- **Alternative (configurable):** `BLOCK_PRODUCER` — block the event receiver thread (increases dispatch latency)

**Important:** Backpressure at the persistence buffer is independent of engine-side `TopicQueue` backpressure. The engine may drop messages before they ever reach the persistence module.

### Error Handling in Flush Thread

| Error Type | Handling |
|-----------|----------|
| Transient DB error (connection lost, timeout) | Retry with exponential backoff (max 3 retries), then log and drop batch |
| Permanent DB error (auth failed, schema mismatch) | Log CRITICAL, stop flush thread, module stays alive but stops persisting |
| Buffer full + drop oldest | Log WARNING with count of dropped records |

---

## Schema Design

### Unified Events Table (Both Backends)

A single table design is preferred over per-event-type tables for v1. Reasons:
- Simpler schema management (no migration needed for new event types)
- Event payloads vary widely; JSON column handles flexibility
- Future query interface can parse JSON for typed access

#### ClickHouse Schema

```sql
CREATE TABLE IF NOT EXISTS tyche.events (
    timestamp DateTime64(9),           -- nanosecond precision
    event_type LowCardinality(String),  -- enum-like compression
    sender LowCardinality(String),      -- module_id
    payload_json String,                -- JSON-serialized payload
    instrument_id Nullable(String),     -- extracted from payload if present
    price Nullable(Float64),            -- extracted from payload if present
    quantity Nullable(Float64)          -- extracted from payload if present
)
ENGINE = MergeTree()
ORDER BY (event_type, timestamp)
PARTITION BY toYYYYMMDD(timestamp)
TTL toDateTime(timestamp) + INTERVAL 90 DAY;  -- auto-cleanup old data
```

**Why MergeTree:** ClickHouse's default table engine for time-series data. Excellent compression, fast range queries, automatic partitioning.

**Why `DateTime64(9)`:** Nanosecond precision needed for high-frequency trading event ordering.

**Why `LowCardinality`:** Event types and sender IDs have low cardinality; ClickHouse compresses these efficiently.

**Why `ORDER BY (event_type, timestamp)`:** Queries will typically filter by event type first, then time range.

#### SQLite Schema

```sql
CREATE TABLE IF NOT EXISTS events (
    timestamp REAL,              -- seconds since epoch (float)
    event_type TEXT NOT NULL,
    sender TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    instrument_id TEXT,
    price REAL,
    quantity REAL
);

CREATE INDEX IF NOT EXISTS idx_events_type_time
    ON events(event_type, timestamp);
```

**Why `REAL` for timestamp:** SQLite has no native `DateTime64`; `REAL` (IEEE 754 double) provides ~microsecond precision for timestamps near 2026, which is sufficient for dev/testing.

**Why no partitioning:** SQLite does not support table partitioning. For large datasets, manual table rotation or VACUUM is needed.

### Record Builder: Payload Extraction

The `RecordBuilder` extracts common fields from payloads for typed columns:

```python
class RecordBuilder:
    COMMON_FIELDS = {
        "instrument_id": ["instrument_id", "symbol", "ticker", "inst"],
        "price": ["price", "last_price", "bid", "ask"],
        "quantity": ["quantity", "qty", "volume", "size"],
    }

    @classmethod
    def from_message(cls, msg: Message) -> EventRecord:
        payload = msg.payload
        return EventRecord(
            timestamp=time.time_ns() / 1e9,
            event_type=msg.event,
            sender=msg.sender,
            payload_json=json.dumps(payload, default=str),
            instrument_id=cls._extract(payload, "instrument_id"),
            price=cls._extract_float(payload, "price"),
            quantity=cls._extract_float(payload, "quantity"),
        )
```

This is best-effort extraction. Unknown event types still get persisted with `payload_json` containing everything.

---

## Suggested Build Order

The build order respects dependencies: backends and buffer are independent and can be built first; the module integrates them; tests validate everything.

### Phase 1: Foundation (No ZMQ/Engine Needed)

**Task 1.1: `RecordBuilder` and `EventRecord`**
- Define `EventRecord` dataclass
- Implement `RecordBuilder.from_message()`
- Unit test: verify record fields, JSON serialization, common field extraction

**Task 1.2: `PersistenceBackend` ABC + `SQLiteBackend`**
- Define `PersistenceBackend` abstract base class
- Implement `SQLiteBackend` with `sqlite3`
- Unit test: connect, `ensure_schema()`, `write_batch()`, disconnect
- No ZMQ, no engine — pure DB tests

**Task 1.3: `ClickHouseBackend`**
- Implement `ClickHouseBackend` with `clickhouse-connect`
- Unit test: same as SQLite (requires running ClickHouse container)
- Mark as `slow` or `integration` test

**Task 1.4: `WriteBuffer`**
- Implement buffer with swap-and-flush pattern
- Unit test: append, swap, size trigger, time trigger, concurrent append/swap
- Mock backend for testing (verify `write_batch` called with correct records)

### Phase 2: Module Integration (Needs Engine)

**Task 2.1: `PersistenceModule` skeleton**
- Subclass `TycheModule`
- Implement `on_*` handlers for all events in `events.py`
- Wire `WriteBuffer` + backend into handlers
- Unit test: instantiate, verify handlers registered, verify interfaces

**Task 2.2: `PersistenceModule` lifecycle**
- Override `start()` to connect backend and start flush thread
- Override `stop()` to signal flush, drain buffer, disconnect backend
- Unit test: start/stop sequence, verify no thread leaks

**Task 2.3: Integration test — full pipeline**
- Spin up `TycheEngine`
- Register `PersistenceModule` with `SQLiteBackend`
- Send events from a test producer module
- Stop engine, query SQLite, verify all events persisted
- Integration test: ~10-20 seconds (engine startup + event flow + DB query)

### Phase 3: Configuration and Polish

**Task 3.1: Configurable event filtering**
- Add `event_filter: Optional[set[str]]` parameter
- Only register `on_*` handlers for filtered events
- Default: all events

**Task 3.2: Configurable batch/flush parameters**
- Expose `batch_size`, `flush_interval_ms`, `max_buffer_size` in constructor
- Validate parameters (batch_size > 0, flush_interval_ms > 0)

**Task 3.3: Error handling and logging**
- Log buffer drops at WARNING
- Log DB errors at ERROR with retry count
- Log flush metrics at DEBUG (records/sec, batch size, DB latency)

### Dependency Graph

```
Task 1.1 (RecordBuilder)
    │
    ▼
Task 1.2 (SQLiteBackend) ──► Task 1.3 (ClickHouseBackend)
    │                              │
    ▼                              ▼
Task 1.4 (WriteBuffer) ◄───────────┘
    │
    ▼
Task 2.1 (PersistenceModule skeleton)
    │
    ▼
Task 2.2 (Lifecycle)
    │
    ▼
Task 2.3 (Integration test)
    │
    ▼
Task 3.1 (Filtering) ──► Task 3.2 (Config) ──► Task 3.3 (Logging)
```

**Parallelizable tasks:** 1.1, 1.2, and 1.4 can be worked in parallel (1.4 mocks the backend). 1.3 depends on 1.2 (shares test patterns). All Phase 2 tasks are sequential. Phase 3 tasks are sequential but independent of each other after 2.3.

---

## Sources

- Direct codebase analysis: `src/tyche/engine.py`, `src/tyche/module.py`, `src/tyche/types.py`, `src/tyche/message.py`, `src/tyche/events.py`, `src/tyche/heartbeat.py`
- Design spec: `docs/design/unified_queue_design_v1.md`
- Codebase analysis: `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STACK.md`, `.planning/codebase/INTEGRATIONS.md`, `.planning/codebase/CONCERNS.md`
- Project context: `.planning/PROJECT.md`, `.planning/STATE.md`
- ClickHouse docker config: `docker/clickhouse-compose.yml`
- Dependencies: `pyproject.toml`
