# Feature Landscape: Database Persistence Module

**Domain:** Event-driven trading engine persistence
**Researched:** 2026-05-14
**Confidence:** HIGH (well-established patterns; ClickHouse and SQLite are mature)

---

## Table Stakes (Must-Have)

Features users expect. Missing = module feels incomplete or unreliable.

### Ingestion

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Subscribe to engine events via `TycheModule` | Follows engine convention; no custom socket code | Low | Use `on_*` handlers, auto-discovered by base class |
| Batch/buffered writes | Per-event DB round-trip would bottleneck dispatch path | Medium | Buffer in memory, flush by size or time threshold |
| Graceful flush on `stop()` | Data loss on shutdown is unacceptable | Low | Drain buffer in `stop()` before closing DB connection |
| Async write path | Must not block the event receiver thread | Medium | Background thread or async queue for DB writes |

### Filtering

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Configurable event type filtering | Not all events need persistence (e.g., heartbeats) | Low | Whitelist or blacklist of event names; default = all |
| Durability-level awareness | Respect `DurabilityLevel.BEST_EFFORT` vs `SYNC_FLUSH` | Medium | Engine already has `DurabilityLevel` enum; persistence should honor it |

### Schema & Storage

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Unified event table schema | All events share core columns: timestamp, event, sender, payload | Low | Payload as JSON/msgpack blob; event-specific columns deferred |
| ClickHouse backend | Columnar storage, high throughput, time-series optimized | Medium | Primary production target; use `clickhouse-connect` or `clickhouse-driver` |
| SQLite backend | Zero-config local dev/test fallback | Low | WAL mode + `synchronous=NORMAL` for throughput; stdlib only |
| Automatic table creation | Schema setup on first connect | Low | `CREATE TABLE IF NOT EXISTS` in backend `start()` |

### Error Handling

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| DB connection failure handling | Module must not crash the engine if DB is down | Medium | Log error, buffer events, retry with backoff; do not raise in event handler |
| Write failure retry | Transient DB errors should not drop events | Medium | Exponential backoff, max retries, then log and drop (metrics) |

---

## Differentiators (Nice-to-Have)

Features that make a persistence module excellent. Not expected, but valued.

### Ingestion

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Dual-write (both backends simultaneously) | Write to ClickHouse AND SQLite for redundancy/backup | Medium | Useful for audit trails; SQLite as local WAL backup |
| Compression before insert | Reduce network I/O and storage for large payloads | Low | msgpack payload is already compact; consider zstd for JSON |

### Buffering

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Configurable buffer policy (size vs time) | Tune for latency vs throughput trade-off | Low | `buffer_size` (events) + `flush_interval_ms` (time) |
| Backpressure signal to engine | When buffer is full, signal upstream to slow down | High | Requires engine support; out of scope for v1 |
| Disk-spill buffer on memory pressure | Avoid OOM under burst load | High | Write overflow to temp file, replay on recovery |

### Filtering

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Payload-field filtering | Persist only events where payload matches criteria | Medium | e.g., `symbol == "AAPL"` — requires schema awareness |
| Sampling (persist 1 in N events) | Reduce volume for high-frequency events | Low | Configurable sampling rate per event type |

### Schema & Storage

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Event-type-specific tables | Separate tables per event type for query efficiency | Medium | `events_quote`, `events_trade` vs single `events` table |
| Partitioning by date (ClickHouse) | Fast time-range queries, efficient TTL | Low | ClickHouse `PARTITION BY toYYYYMMDD(timestamp)` |
| TTL / automatic data expiration | Old events auto-deleted per retention policy | Low | ClickHouse `TTL timestamp + INTERVAL 90 DAY` |
| Materialized views for aggregates | Pre-computed rollups (e.g., events per minute) | Medium | ClickHouse feature; reduces query load |

### Observability

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Metrics export (events written, buffer depth, drop count) | Operational visibility | Low | Counters updated during flush; expose via admin query or logging |
| Health check endpoint | Know if persistence is keeping up | Low | Boolean: buffer depth < threshold AND last flush < interval |

### Replay

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Event replay via pub/sub | Re-emit persisted events for backtesting | High | Read from DB, deserialize, re-publish via `send_event` |
| Time-range replay | Replay events between two timestamps | Medium | Query with `WHERE timestamp BETWEEN`, emit in order |

---

## Anti-Features (Avoid)

Features that seem useful but cause operational or architectural problems.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Synchronous DB writes in event handler** | Blocks the ZeroMQ receive thread, causing backpressure and dropped messages | Always buffer + async flush; never call DB from `_dispatch` |
| **Guaranteed ordering across all event types** | Forces single-writer serialization, destroying throughput; most trading events are independent per symbol | Order within a partition key (e.g., `symbol`); accept global best-effort ordering |
| **Schema migrations / versioning** | Adds complexity far beyond v1 scope; initial schema is sufficient | Document schema, recreate tables if needed; defer to v2 |
| **Query/read interface in persistence module** | Violates single responsibility; queries need indexes, caching, API design | Separate read module or use DB client directly; persistence is write-only |
| **Two-phase commit across engine + DB** | Distributed transactions are complex, slow, and unnecessary for append-only logs | At-least-once delivery + idempotent writes; accept small duplication |
| **Persisting every message type by default** | Heartbeats, registration ACKs, and admin queries create noise and bloat | Default to all, but provide easy filtering; exclude `heartbeat` and `register` by default |
| **Unbounded in-memory buffer** | OOM under burst load or DB outage | Fixed-size buffer with drop-oldest or block policy; make limit explicit |
| **Retrying forever on DB failure** | Memory growth, blocked buffer, no visibility into persistent failure | Max retries + circuit breaker pattern; log drops, emit metric |
| **Using broker message IDs for deduplication** | Message IDs can change on redelivery in some brokers; not reliable | Use business keys (`sender` + `timestamp` + `event`) or accept at-least-once |
| **Individual `INSERT` per event (SQLite)** | 100x slower than batched `executemany()` | Batch inserts; SQLite WAL + `executemany()` achieves ~30K TPS |
| **ClickHouse `sync_flush` for every event** | Destroys throughput; ClickHouse is optimized for batch inserts | Use `async_insert=1` server-side or client-side batching |
| **Dynamic table creation per event type** | Table explosion, schema drift, operational nightmare | Single `events` table with `event_type` column, or explicit schema per known type |

---

## Feature Categories

### Ingestion
- Subscribe via `TycheModule` (`on_*` handlers)
- Deserialize `Message` from msgpack
- Extract timestamp, sender, event, payload
- Route to appropriate backend

### Buffering
- In-memory queue (`collections.deque` or `queue.Queue`)
- Batch by count + time dual trigger
- Background flush thread
- Graceful drain on shutdown

### Filtering
- Event name whitelist/blacklist
- Durability level gate (`BEST_EFFORT` skip, `ASYNC_FLUSH` buffer, `SYNC_FLUSH` wait)
- Optional: payload field predicates (v2)

### Schema
- Core columns: `timestamp`, `event_type`, `sender`, `payload` (blob), `msg_type`, `correlation_id`
- ClickHouse: `MergeTree` engine, `ORDER BY (event_type, timestamp)`, `PARTITION BY toYYYYMMDD(timestamp)`
- SQLite: `INTEGER PRIMARY KEY AUTOINCREMENT`, `REAL` timestamp, `BLOB` payload, WAL mode

### Error Handling
- Connection retry with exponential backoff
- Write failure: retry N times, then drop + log + metric
- Buffer full: drop oldest (configurable) or block
- Circuit breaker: stop trying after sustained failures, periodic probe

---

## Dependencies on Existing Engine

| Engine Feature | How Persistence Uses It | Dependency Strength |
|----------------|------------------------|---------------------|
| `TycheModule` base class | Inherit for ZMQ socket setup, registration, heartbeat | Hard — module must subclass this |
| `on_*` handler discovery | Auto-subscribe to events via method naming convention | Hard — follows v3 pattern |
| `Message` serialization | Deserialize msgpack frames to `Message` objects | Hard — uses `deserialize()` from `message.py` |
| `DurabilityLevel` enum | Gate persistence by message durability level | Soft — can ignore initially, enhance later |
| `InterfacePattern.ON` | Subscribe to events as a consumer | Hard — registered at module start |
| Engine pub/sub (XPUB/XSUB) | Receive all published events | Hard — core to function |
| Admin query endpoint | Expose persistence metrics via engine admin | Soft — can log instead |
| Topic queues / backpressure | Future: signal buffer state to engine | Soft — v2 enhancement |

### Dependency Graph

```
PersistenceModule (TycheModule)
  ├── on_event(msg)  [engine dispatches via _dispatch()]
  │     ├── filter by event_type
  │     ├── filter by durability
  │     └── enqueue to buffer
  ├── flush_thread
  │     ├── drain buffer
  │     ├── batch events
  │     └── backend.write_batch()
  ├── start()
  │     ├── super().start()  [registers with engine]
  │     └── backend.connect()
  └── stop()
        ├── backend.flush()
        ├── backend.close()
        └── super().stop()

Backend (abstract)
  ├── ClickHouseBackend
  │     └── clickhouse-connect / clickhouse-driver
  └── SQLiteBackend
        └── sqlite3 (stdlib)
```

---

## MVP Recommendation

Prioritize for v1.0:

1. **Table stakes: `TycheModule` subclass with `on_event` handler** — follows engine convention
2. **Table stakes: In-memory buffer with background flush thread** — size + time triggers
3. **Table stakes: ClickHouse backend with batch `INSERT`** — `MergeTree`, basic schema
4. **Table stakes: SQLite backend with WAL mode** — zero-config dev fallback
5. **Table stakes: Graceful flush on `stop()`** — no data loss on shutdown
6. **Table stakes: Event type filtering (whitelist)** — exclude heartbeats, include trading events
7. **Differentiator: Configurable buffer size + flush interval** — operational tunability

Defer to v2:
- **Replay capability** — needs read path, time-range queries, re-emission logic
- **Event-type-specific tables** — can migrate from unified table later
- **Backpressure signaling** — requires engine changes
- **Disk-spill buffer** — complex, only needed under extreme load
- **Payload-field filtering** — needs query engine over payload
- **Materialized views / TTL** — ClickHouse-specific ops, not core to persistence

---

## Sources

- [Event-Driven Architecture in Practice: What Actually Goes Wrong](https://dev.to/refaatalktifan/event-driven-architecture-in-practice-what-actually-goes-wrong-pno) — Event storms, idempotency pitfalls
- [ClickHouse Async INSERT Guide](https://clickhouse.com/blog/asynchronous-data-inserts-in-clickhouse) — Server-side batching patterns
- [ClickHouse Python Client Comparison](https://www.tinybird.co/blog/clickhouse-python-example) — `clickhouse-connect` vs `clickhouse-driver`
- [SQLite WAL Mode Performance](https://travishorn.com/a-hands-on-exploration-of-sqlite-for-production/) — WAL benchmarks, 33K TPS with `synchronous=NORMAL`
- [Event Sourcing Common Issues](https://docs.eventsourcingdb.io/best-practices/common-issues/) — Schema evolution, snapshot strategies
- [Backpressure & Flow Control in Distributed Systems](https://codelit.io/blog/backpressure-flow-control-distributed-systems) — Queue depth, reactive streams
- [Sisyphus Webhook System](https://github.com/ndoherty-xyz/sisyphus) — Circuit breaker, DLQ, fairness patterns in production
- [Event-Driven Architecture Patterns 2025](https://wojciechowski.app/en/articles/event-driven-architecture-patterns-2025) — CQRS, saga, outbox patterns
- [ClickHouse Native Async Python Client Design](https://clickhouse.com/blog/python-async-native-client) — 2025 async client architecture
- [SQLite Python Tutorial WAL 2026](https://tech-insider.org/sqlite-python-tutorial-fts5-wal-mode-2026/) — WAL mode configuration best practices
