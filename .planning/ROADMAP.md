# Roadmap: TycheEngine Event Persistence Layer

**Created:** 2026-04-21
**Phases:** 4
**v1 Requirements:** 29 mapped
**Granularity:** Standard

---

## Phase 1: Schema & Backend Foundation

**Goal:** Establish the database schema and persistence backend abstraction so all storage implementations are swappable and testable.

**Requirements:**
BACK-01, BACK-02, BACK-03, BACK-05, SCHM-01, SCHM-02, SCHM-03, SCHM-04

**Success Criteria:**
1. `PersistenceBackend` abstract class exists with `insert_batch()`, `query()`, `health()`, `close()`
2. `ClickHouseBackend` connects to ClickHouse, creates tables, and can execute INSERT/SELECT
3. `JsonlBackend` passes the same interface tests (refactored from existing code)
4. ClickHouse `events` table created with correct schema, partitioning, and ordering
5. Schema creation is idempotent and versioned
6. Docker Compose file for local ClickHouse dev/CI
7. Unit tests for both backends with mocked ClickHouse; integration tests with Docker ClickHouse

**Plans:** 3 plans

Plans:
- [ ] `01-01-PLAN.md` — Core abstractions: PersistenceBackend ABC, InsertResult/QueryResult dataclasses, SchemaManager with idempotent DDL
- [ ] `01-02-PLAN.md` — Backend implementations: ClickHouseBackend with connection pooling, JsonlBackend refactored from DataRecorderModule, package __init__.py
- [ ] `01-03-PLAN.md` — Dev/CI infrastructure: Docker Compose for ClickHouse, pyproject.toml dependency update, integration tests with real ClickHouse

**UI hint:** no

---

## Phase 2: Event Ingestion

**Goal:** Build the non-blocking event ingestion pipeline that captures all engine events and durably persists them to ClickHouse without impacting event dispatch latency.

**Requirements:**
INGT-01, INGT-02, INGT-03, INGT-04, INGT-05, INGT-06, INGT-07, INGT-08

**Success Criteria:**
1. `PersistenceModule` (TycheModule) subscribes to all engine events via ZMQ SUB without blocking
2. Events are enqueued to a thread-safe buffer with configurable max size
3. Background ingestion worker batches events and flushes to ClickHouse
4. Batch flush triggered by size (default 5000) OR timeout (default 1s)
5. Graceful shutdown (SIGTERM) flushes pending batch
6. On ClickHouse connection failure, exponential backoff retry (max 30s) preserves buffered events
7. Buffer overflow policy configurable (drop-oldest, drop-newest, block)
8. Ingestion p99 latency < 1000ms verified under load test
9. No events dropped during 10K event burst test

**Depends on:** Phase 1

**UI hint:** no

---

## Phase 3: Query API & Replay Engine

**Goal:** Enable reading persisted events back with flexible filtering and replaying them through the engine for backtesting.

**Requirements:**
QRY-01, QRY-02, QRY-03, QRY-04, QRY-05, QRY-06, RPLY-01, RPLY-02, RPLY-03, RPLY-04, RPLY-05

**Success Criteria:**
1. `QueryAPI` supports filtering by time range, event type, instrument ID, module ID
2. Query results support pagination (limit/offset)
3. Query returns deserialized Python dicts from msgpack payload strings
4. `ClickHouseReplay` module reads historical events by date range and instrument
5. Replay emits events in strict timestamp ascending order
6. Replay supports speed multiplier (0, 1, Nx)
7. Replayed events are published through engine XPUB so strategies receive them identically to live
8. Simulated clock advances between replayed events
9. Backtest with replay produces identical results to historical live run

**Depends on:** Phase 2

**UI hint:** no

---

## Phase 4: Operational Health & Migration

**Goal:** Production-ready operational visibility, config-driven backend selection, and migration path from JSONL.

**Requirements:**
BACK-04, HLTH-01, HLTH-02, HLTH-03, HLTH-04

**Success Criteria:**
1. Config-driven backend selection works (JSONL dev / ClickHouse prod via config file)
2. Ingestion worker logs batch size, flush count, average latency
3. Buffer depth exposed (current / max)
4. Connection health tracked and logged (connected / disconnected / retrying)
5. Health metrics optionally published as engine events
6. JSONL recorder deprecated with warning; migration guide documented
7. All existing tests pass; new tests achieve >=90% coverage for persistence module
8. Full test suite passes with both JSONL and ClickHouse backends

**Depends on:** Phase 2 (can run in parallel with Phase 3)

**UI hint:** no

---

## Phase Dependencies

```
Phase 1 --> Phase 2 --> Phase 3
              |
              --> Phase 4 (parallel with Phase 3)
```

## Requirement Coverage

| Phase | Requirements | Count |
|-------|-------------|-------|
| Phase 1 | BACK-01..05, SCHM-01..04 | 8 |
| Phase 2 | INGT-01..08 | 8 |
| Phase 3 | QRY-01..06, RPLY-01..05 | 11 |
| Phase 4 | BACK-04, HLTH-01..04 | 5 |
| **Total** | | **32** |

*Note: BACK-04 appears in Phase 4 because config-driven selection requires both backends to be implemented first.*

---
*Roadmap created: 2026-04-21*
*Last updated: 2026-04-21 after planning Phase 1*
