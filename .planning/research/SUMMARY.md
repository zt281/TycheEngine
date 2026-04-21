# Project Research Summary

**Project:** TycheEngine — Event Persistence Layer
**Domain:** Distributed trading system event persistence with ClickHouse
**Researched:** 2026-04-21
**Confidence:** HIGH

## Executive Summary

The goal is to build a unified event persistence layer for TycheEngine that replaces the current JSONL-based recording with a queryable, scalable ClickHouse backend. All inter-module events — market data (quotes, trades, bars), order flow (submits, fills, updates), and internal engine events — will be durably logged to a single ClickHouse table with sub-second ingestion latency.

The recommended approach is a Producer-Consumer pattern: a `PersistenceModule` subscribes to all engine events via ZMQ, enqueues them to a thread-safe buffer, and a background ingestion worker batches and flushes to ClickHouse. This avoids blocking ZMQ recv threads while maximizing ClickHouse's batch-optimized performance. A `QueryAPI` provides filtered reads (by time, instrument, event type), and a `ReplayEngine` re-emits historical events through the engine for backtesting.

The primary risks are: (1) blocking ZMQ threads with synchronous DB writes, (2) ClickHouse "Too many parts" errors from undersized batches, and (3) data loss from unflushed batches during crashes. All three are addressable through proper threading, batch sizing, and graceful shutdown handling.

## Key Findings

### Recommended Stack

**Core technologies:**
- **ClickHouse 24.x+**: Columnar storage optimized for time-series; 100K+ rows/sec ingestion; excellent compression for repeated values (instrument_id, event_type)
- **clickhouse-connect 0.7.0+**: Official ClickHouse Inc Python client; HTTP interface, async support, connection pooling, strong type conversion
- **msgpack** (existing): Preserve for event payload serialization in ClickHouse

**Development tooling:**
- Docker (`clickhouse/clickhouse-server:24`) for local dev and CI
- `clickhouse-connect` async client for non-blocking ingestion from ZMQ threads

### Expected Features

**Must have (table stakes):**
- Event ingestion with batching and backpressure
- Time-range queries (the #1 query pattern for trading data)
- Event-type and instrument filtering
- Basic replay for backtesting

**Should have (competitive):**
- Operational metrics (ingestion lag, batch sizes, connection health)
- Config-driven backend selection (JSONL dev / ClickHouse prod)
- Retention policies via ClickHouse TTL

**Defer (v2+):**
- Materialized views for real-time analytics
- Kafka ingestion buffer for extreme scale
- Multi-node ClickHouse distributed tables

### Architecture Approach

**Major components:**
1. **PersistenceModule** — TycheModule that subscribes to all events, buffers, and hands off to ingestion worker
2. **BatchCollector + IngestionWorker** — Background thread that accumulates events and flushes batches to ClickHouse
3. **ClickHouseBackend** — Implements `PersistenceBackend` interface: `insert_batch()`, `query()`, `health()`
4. **QueryAPI** — SQL builder for filtered reads; used by ReplayEngine and CLI tools
5. **ReplayEngine** — Reads time-ordered events from ClickHouse and re-publishes through engine

**Data flow:**
- Ingestion: Engine XPUB → PersistenceModule SUB → Event Buffer → Batch Collector → ClickHouse INSERT
- Query: Request → QueryAPI.build_query() → ClickHouse SELECT → Deserialize → Return/Publish

### Critical Pitfalls

1. **Blocking ZMQ threads** — Always use queue-based handoff; never call INSERT from event handler
2. **Too many parts** — Batch to 1K-50K rows; use timeout flush for low-volume periods
3. **Schema drift** — Use explicit column lists in INSERTs; version schema; keep extensible payload column
4. **Unflushed batch on crash** — Implement SIGTERM handler for graceful flush; document at-most-1s data loss window
5. **Connection failures** — Exponential backoff retry; keep events in buffer during outage

## Implications for Roadmap

### Phase 1: Schema & Backend Foundation
**Rationale:** Everything else depends on the database schema and backend connection. Must be first.
**Delivers:** ClickHouse schema DDL, `PersistenceBackend` interface, `ClickHouseBackend` with connection pooling, Docker compose for dev/CI.
**Addresses:** Schema design (FEATURES), Backend abstraction (FEATURES)
**Avoids:** Schema drift pitfall (define schema upfront with versioning)

### Phase 2: Event Ingestion
**Rationale:** Core functionality — getting events into ClickHouse. Depends on Phase 1 backend.
**Delivers:** `PersistenceModule` (TycheModule), event buffer, batch collector, ingestion worker thread, graceful shutdown flush.
**Uses:** clickhouse-connect async client, Producer-Consumer pattern
**Implements:** EventBuffer, BatchCollector, IngestionWorker (ARCHITECTURE)
**Avoids:** Blocking ZMQ thread, Too many parts, Unflushed batch, Connection failure pitfalls

### Phase 3: Query API & Replay Engine
**Rationale:** Reading data back is the second half of the value proposition. Depends on Phase 2 having data to query.
**Delivers:** `QueryAPI` with filters (time, instrument, event_type, module_id), `ClickHouseReplay` module, CLI query tool.
**Uses:** ClickHouse SQL, time-range indexing
**Implements:** QueryAPI, ReplayEngine (ARCHITECTURE)

### Phase 4: Operational Health & Migration
**Rationale:** Production readiness and backward compatibility. Can be done in parallel with Phase 3.
**Delivers:** Health metrics table/signals, retention policies (TTL), migration path from JSONL recorder, config-driven backend selection.
**Addresses:** Operational metrics (FEATURES), Retention policies (FEATURES)

### Phase Ordering Rationale

- Schema must precede ingestion (cannot insert without a table)
- Ingestion must precede query/replay (cannot query what hasn't been inserted)
- Health/migration is independent of query/replay and can run in parallel with Phase 3
- Phase 2 is the highest-risk phase (threading, batching, backpressure) and should be the most thoroughly tested

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2:** ClickHouse batch sizing and backpressure strategies are workload-dependent; may need tuning
- **Phase 3:** Replay timing accuracy (simulated vs. real-time) may need domain-specific validation

Phases with standard patterns (skip research-phase):
- **Phase 1:** Well-documented schema design patterns for ClickHouse time-series
- **Phase 4:** Standard operational patterns (metrics, TTL)

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | ClickHouse + clickhouse-connect is well-established; user explicitly chose ClickHouse |
| Features | HIGH | Clear domain (event persistence); requirements are straightforward |
| Architecture | HIGH | Producer-Consumer + Backend Abstraction are standard, proven patterns |
| Pitfalls | HIGH | All 5 critical pitfalls are well-known in ClickHouse + ZMQ communities |

**Overall confidence:** HIGH

### Gaps to Address

- **Batch size tuning:** Optimal batch size depends on event size and volume; needs empirical testing during Phase 2 implementation
- **Payload encoding:** Decision between msgpack bytes in ClickHouse vs. JSON string — needs performance comparison during Phase 1
- **Replay timing:** Whether to preserve inter-event timing or allow accelerated replay — needs validation with actual backtesting use case

## Sources

### Primary (HIGH confidence)
- ClickHouse official docs: https://clickhouse.com/docs — HTTP interface, MergeTree engine, time-series best practices
- clickhouse-connect PyPI/docs: https://pypi.org/project/clickhouse-connect/ — Python client API, async examples
- ClickHouse production FAQ: https://clickhouse.com/docs/en/faq/operations/production — "Too many parts", batch sizing

### Secondary (MEDIUM confidence)
- ZeroMQ Guide (Paranoid Pirate pattern): https://zguide.zeromq.org/ — Threading model relevant to non-blocking ingestion
- TycheEngine codebase analysis (`.planning/codebase/`) — Existing DataRecorderModule, ReplayModule, engine threading

### Tertiary (LOW confidence)
- Community benchmarks: ClickHouse vs TimescaleDB vs InfluxDB for tick data — specific numbers vary by workload

---
*Research completed: 2026-04-21*
*Ready for roadmap: yes*
