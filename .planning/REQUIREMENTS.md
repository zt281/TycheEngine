# Requirements: TycheEngine Event Persistence Layer

**Defined:** 2026-04-21
**Core Value:** All events flowing through TycheEngine are durably persisted to ClickHouse with sub-second latency, queryable by instrument, time range, event type, and module.

## v1 Requirements

### Persistence Backend

- [ ] **BACK-01**: Abstract `PersistenceBackend` interface exists with `insert_batch()`, `query()`, `health()`, and `close()` methods
- [ ] **BACK-02**: `ClickHouseBackend` implements the interface using `clickhouse-connect` with connection pooling
- [ ] **BACK-03**: `JsonlBackend` implements the interface for dev/test fallback (refactored from existing `DataRecorderModule`)
- [ ] **BACK-04**: Backend selection is config-driven via `persistence.backend` setting ("clickhouse" | "jsonl")
- [ ] **BACK-05**: ClickHouse connection parameters are configurable (host, port, database, user, password, secure)

### Schema

- [ ] **SCHM-01**: `events` table created with MergeTree engine, partitioned by date, ordered by `(timestamp, instrument_id, event_type)`
- [ ] **SCHM-02**: Common columns defined: `timestamp` (DateTime64(3)), `event_type` (LowCardinality(String)), `instrument_id` (LowCardinality(String)), `module_id` (String), `payload` (String)
- [ ] **SCHM-03**: Schema initialization is idempotent (CREATE TABLE IF NOT EXISTS)
- [ ] **SCHM-04**: Schema version is tracked to support future migrations

### Event Ingestion

- [ ] **INGT-01**: `PersistenceModule` (TycheModule) subscribes to all engine events without blocking the ZMQ recv thread
- [ ] **INGT-02**: Events are enqueued to a thread-safe buffer with a configurable max size
- [ ] **INGT-03**: Background ingestion worker accumulates events into batches (configurable size, default 5000 rows)
- [ ] **INGT-04**: Batch flush triggered by size threshold OR timeout (configurable, default 1 second)
- [ ] **INGT-05**: Graceful shutdown flushes any pending batch before stopping
- [ ] **INGT-06**: On ClickHouse connection failure, worker retries with exponential backoff (max 30s) without dropping buffered events
- [ ] **INGT-07**: Buffer overflow policy is configurable (drop oldest, drop newest, or block)
- [ ] **INGT-08**: Ingestion latency p99 < 1000ms under normal load

### Query API

- [ ] **QRY-01**: Query by time range (`start_ts`, `end_ts`) returns events in ascending timestamp order
- [ ] **QRY-02**: Query by `event_type` filter (single type or list of types)
- [ ] **QRY-03**: Query by `instrument_id` filter (single instrument or list)
- [ ] **QRY-04**: Query by `module_id` filter
- [ ] **QRY-05**: Query supports pagination (`limit`, `offset`) for large result sets
- [ ] **QRY-06**: Query returns deserialized event payloads as Python dicts

### Replay Engine

- [ ] **RPLY-01**: `ClickHouseReplay` module reads historical events from ClickHouse by date range and instrument
- [ ] **RPLY-02**: Events are replayed in strict timestamp ascending order
- [ ] **RPLY-03**: Replay supports speed multiplier (0 = as-fast-as-possible, 1 = real-time, N = Nx speed)
- [ ] **RPLY-04**: Replay publishes events through the engine's event system so strategies receive them identically to live data
- [ ] **RPLY-05**: Replay advances the simulated clock between events

### Operational Health

- [ ] **HLTH-01**: Ingestion worker reports batch size, flush count, and average latency
- [ ] **HLTH-02**: Buffer depth is exposed (current size / max size)
- [ ] **HLTH-03**: Connection health is tracked (connected, disconnected, retrying)
- [ ] **HLTH-04**: Health metrics are accessible via logging; optionally published as engine events

## v2 Requirements

### Retention

- **RETN-01**: ClickHouse TTL auto-drops partitions older than configurable retention period
- **RETN-02**: Compression settings tuned per column (CODEC for payload, delta for timestamps)

### Analytics

- **ANLY-01**: Materialized view for OHLCV bar aggregation from tick data
- **ANLY-02**: Daily summary table with event counts per instrument and type

### Scale

- **SCAL-01**: Kafka ingestion buffer for burst handling beyond single ClickHouse node
- **SCAL-02**: Distributed ClickHouse tables for horizontal scaling

## Out of Scope

| Feature | Reason |
|---------|--------|
| Multi-region ClickHouse replication | Single-node sufficient for v1; trading systems typically run in one region |
| Real-time streaming analytics (materialized views) | Deferred to v2; ad-hoc SQL queries sufficient for v1 validation |
| Compression at rest beyond ClickHouse defaults | Not a priority; default LZ4 is adequate for initial volumes |
| Event sourcing / command sourcing | We persist events for audit and replay, not state reconstruction |
| GUI for querying events | CLI and programmatic API only for v1 |
| SQLite backend | JSONL is sufficient for dev fallback; SQLite adds complexity without benefit |
| Write-ahead log (WAL) for crash recovery | Documented at-most-1s loss window is acceptable for v1 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| BACK-01 | Phase 1 | Pending |
| BACK-02 | Phase 1 | Pending |
| BACK-03 | Phase 1 | Pending |
| BACK-04 | Phase 4 | Pending |
| BACK-05 | Phase 1 | Pending |
| SCHM-01 | Phase 1 | Pending |
| SCHM-02 | Phase 1 | Pending |
| SCHM-03 | Phase 1 | Pending |
| SCHM-04 | Phase 1 | Pending |
| INGT-01 | Phase 2 | Pending |
| INGT-02 | Phase 2 | Pending |
| INGT-03 | Phase 2 | Pending |
| INGT-04 | Phase 2 | Pending |
| INGT-05 | Phase 2 | Pending |
| INGT-06 | Phase 2 | Pending |
| INGT-07 | Phase 2 | Pending |
| INGT-08 | Phase 2 | Pending |
| QRY-01 | Phase 3 | Pending |
| QRY-02 | Phase 3 | Pending |
| QRY-03 | Phase 3 | Pending |
| QRY-04 | Phase 3 | Pending |
| QRY-05 | Phase 3 | Pending |
| QRY-06 | Phase 3 | Pending |
| RPLY-01 | Phase 3 | Pending |
| RPLY-02 | Phase 3 | Pending |
| RPLY-03 | Phase 3 | Pending |
| RPLY-04 | Phase 3 | Pending |
| RPLY-05 | Phase 3 | Pending |
| HLTH-01 | Phase 4 | Pending |
| HLTH-02 | Phase 4 | Pending |
| HLTH-03 | Phase 4 | Pending |
| HLTH-04 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 29 total
- Mapped to phases: 29
- Unmapped: 0

---
*Requirements defined: 2026-04-21*
*Last updated: 2026-04-21 after initial definition*
