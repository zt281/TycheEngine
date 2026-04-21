# Architecture Research

**Domain:** Event persistence for distributed trading systems
**Researched:** 2026-04-21
**Confidence:** HIGH

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    TycheEngine Event Bus                     │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │ Gateway │  │ Strategy│  │   OMS   │  │  Risk   │        │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘        │
│       │            │            │            │              │
│       └────────────┴────────────┴────────────┘              │
│                         │ XPUB/XSUB                         │
├─────────────────────────┬───────────────────────────────────┤
│       PersistenceModule │                                   │
│  ┌──────────────────────┴─────────────────────┐              │
│  │         Event Buffer (queue.Queue)          │              │
│  │  ┌─────────────┐      ┌─────────────────┐   │              │
│  │  │  Batch      │─────▶│  Ingestion      │   │              │
│  │  │  Collector  │      │  Worker (thread)│   │              │
│  │  └─────────────┘      └────────┬────────┘   │              │
│  └────────────────────────────────┼────────────┘              │
├───────────────────────────────────┼───────────────────────────┤
│           ClickHouse              │                           │
│  ┌────────────────────────────────┴─────────────────────┐    │
│  │              events table (MergeTree)                 │    │
│  │  (timestamp, event_type, instrument_id, payload...)   │    │
│  └───────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| PersistenceModule | Subscribes to all engine events, buffers, batches, sends to backend | TycheModule subclass with background ingestion thread |
| EventBuffer | Holds events between receive and batch flush | `queue.Queue` or `deque` with size limit |
| BatchCollector | Accumulates events until batch size or timeout reached | Timer + size threshold logic |
| IngestionWorker | Sends batches to ClickHouse asynchronously | `clickhouse-connect` async client in background thread |
| QueryAPI | Reads events back with filtering | SQL builder + `clickhouse-connect` query methods |
| ReplayEngine | Reads time-ordered events and re-publishes | Uses QueryAPI + TycheModule event publishing |

## Recommended Project Structure

```
src/modules/trading/persistence/
├── __init__.py
├── backend.py          # Abstract PersistenceBackend
├── clickhouse_backend.py # ClickHouse implementation
├── jsonl_backend.py    # JSONL fallback (refactored from DataRecorderModule)
├── schema.py           # Table definitions, DDL
├── query.py            # Query builder, filters
├── recorder.py         # PersistenceModule (replaces DataRecorderModule)
├── replay.py           # ClickHouseReplay (replaces ReplayModule)
└── metrics.py          # Operational health tracking
```

### Structure Rationale

- **`backend.py`:** Single interface so all storage implementations are swappable
- **`clickhouse_backend.py`:** ClickHouse-specific batching, connection, error handling
- **`schema.py`:** Centralized DDL — table creation, migrations, indices
- **`query.py`:** Encapsulates SQL generation; makes testing easier
- **`recorder.py`:** TycheModule that plugs into the event bus

## Architectural Patterns

### Pattern 1: Producer-Consumer with Bounded Buffer

**What:** Events are produced by the engine's XPUB socket and consumed by a background thread that batches and flushes to ClickHouse.
**When to use:** Always — ZMQ recv happens on a daemon thread; we must not block it.
**Trade-offs:** Adds latency (batch window) but prevents overwhelming ClickHouse with small inserts.

### Pattern 2: Backend Abstraction (Strategy Pattern)

**What:** `PersistenceBackend` interface with `insert_batch()`, `query()`, `health()` methods. Implementations: `ClickHouseBackend`, `JsonlBackend`, `SqliteBackend`.
**When to use:** When the same code must run in dev (JSONL), test (SQLite), and prod (ClickHouse).
**Trade-offs:** Slight overhead of abstraction; pays off in testability and deployment flexibility.

### Pattern 3: Single Wide Table

**What:** One `events` table with common columns (`timestamp`, `event_type`, `instrument_id`, `module_id`) and a `payload` column (msgpack bytes or JSON string) for event-specific data.
**When to use:** When event types share few fields and schema evolution is frequent.
**Trade-offs:** Less efficient filtering on payload fields; simpler schema management than per-type tables.

**Alternative:** Partially normalized — common columns + type-specific columns as Nullable.

## Data Flow

### Ingestion Flow

```
[Engine XPUB] --(event)--> [PersistenceModule SUB]
                                    │
                                    v
                            [Event Buffer Queue]
                                    │
                                    v
                            [Batch Collector]
                              (size / timeout)
                                    │
                                    v
                            [ClickHouse INSERT]
```

### Query Flow

```
[ReplayModule / CLI / Strategy]
            │
            v
    [QueryAPI.build_query()]
            │
            v
    [ClickHouse SELECT]
            │
            v
    [Deserialize rows -> Messages]
            │
            v
    [Publish via engine / return to caller]
```

### Key Data Flows

1. **Real-time ingestion:** Events flow from engine to ClickHouse within the batch window (target: <1s latency)
2. **Historical replay:** Query by date+instrument, sort by timestamp, emit through engine at original or accelerated pace
3. **Health monitoring:** Background thread reports ingestion lag and batch statistics

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| <1M events/day | Single ClickHouse node, default MergeTree, daily partitions |
| 1M-100M events/day | Optimize batch size (10K-50K rows), add `instrument_id` to ORDER BY, hourly partitions |
| 100M+ events/day | Consider sharding by instrument, Kafka as ingestion buffer, dedicated ClickHouse cluster |

### Scaling Priorities

1. **First bottleneck:** Batch size too small → too many INSERTs → ClickHouse merge queue backs up
2. **Second bottleneck:** Single PARTITION key (date only) → too many parts → query slowdown

## Anti-Patterns

### Anti-Pattern 1: Synchronous INSERT from ZMQ Thread

**What people do:** Call `client.insert()` directly from the event handler callback.
**Why it's wrong:** Blocks the ZMQ SUB socket recv loop; missed events, backpressure cascades to engine.
**Do this instead:** Enqueue to a thread-safe buffer; background worker does the INSERT.

### Anti-Pattern 2: One Table Per Event Type

**What people do:** `events_quote`, `events_trade`, `events_fill` tables.
**Why it's wrong:** Schema explosion, hard to query across types, harder to maintain.
**Do this instead:** Single table with `event_type` column and Nullable type-specific fields.

### Anti-Pattern 3: String Payload Only

**What people do:** Store entire event as JSON string in one `payload` column.
**Why it's wrong:** Cannot filter or aggregate on payload fields without parsing every row.
**Do this instead:** Extract common fields to columns (instrument_id, order_id, price, quantity); keep full payload for reconstruction.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| ClickHouse | HTTP (8123) or native (9000) | HTTP via `clickhouse-connect` is simpler and works through proxies |
| Docker | Local dev / CI | `clickhouse/clickhouse-server:24` image, ephemeral for tests |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| PersistenceModule ↔ ClickHouse | HTTP INSERT / SELECT | Batched inserts, async where possible |
| QueryAPI ↔ ReplayModule | Direct method calls | QueryAPI is library code, not a separate process |
| PersistenceModule ↔ Engine | ZMQ SUB (events in) | Subscribes to all relevant topics |

## Sources

- ClickHouse MergeTree engine docs: https://clickhouse.com/docs/en/engines/table-engines/mergetree-family/mergetree
- clickhouse-connect async examples: https://github.com/ClickHouse/clickhouse-connect
- TycheEngine codebase: `src/tyche/engine.py` (XPUB/XSUB proxy), `src/tyche/module.py` (event subscription)

---
*Architecture research for: Event persistence with ClickHouse*
*Researched: 2026-04-21*
