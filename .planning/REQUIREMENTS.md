# Requirements: TycheEngine v1.0 Persistence Module

**Defined:** 2026-05-14
**Core Value:** All events flowing through TycheEngine can be persisted to a database for replay, audit, and analysis

## v1 Requirements

### Persistence Module Core

- [ ] **PERSIST-01**: `PersistenceModule` inherits from `TycheModule` and auto-registers with the engine
- [ ] **PERSIST-02**: `PersistenceModule` subscribes to configurable event types (default: all)
- [ ] **PERSIST-03**: `PersistenceModule` buffers incoming events in memory before writing
- [ ] **PERSIST-04**: `PersistenceModule` flushes buffer on `stop()` or when buffer size threshold is reached
- [ ] **PERSIST-05**: `PersistenceModule` handles backpressure by dropping oldest buffered events when buffer is full
- [ ] **PERSIST-06**: `PersistenceModule` publishes persistence health metrics (buffer size, dropped count, write latency)

### Database Backends

- [ ] **DB-01**: SQLite backend for zero-config local development and testing
- [ ] **DB-02**: SQLite backend creates tables on first connection (events, market_data, orders, positions)
- [ ] **DB-03**: ClickHouse backend for high-throughput production deployments
- [ ] **DB-04**: ClickHouse backend creates tables on first connection with appropriate engine (MergeTree)
- [ ] **DB-05**: Backend selection is configurable via constructor parameter (`sqlite` or `clickhouse`)
- [ ] **DB-06**: Both backends share the same write interface (polymorphic `Backend` protocol)
- [ ] **DB-07**: SQLite connection string is configurable (defaults to `tyche_events.db`)
- [ ] **DB-08**: ClickHouse host, port, database, user, password are configurable

### Event Storage Schema

- [ ] **SCHEMA-01**: Events table stores: event_type, sender, timestamp, payload (JSON), topic
- [ ] **SCHEMA-02**: Market data table stores: instrument_id, exchange, bid/ask prices, volume, timestamp
- [ ] **SCHEMA-03**: Orders table stores: order_id, instrument, direction, price, volume, status, timestamp
- [ ] **SCHEMA-04**: Positions table stores: instrument, direction, quantity, avg_price, timestamp
- [ ] **SCHEMA-05**: Schema supports event replay by timestamp range query (prepared for v2)

### Configuration

- [ ] **CONFIG-01**: Event filter list is configurable (which event types to persist, default all)
- [ ] **CONFIG-02**: Buffer size threshold is configurable (default 1000 events)
- [ ] **CONFIG-03**: Flush interval is configurable (default 5 seconds)
- [ ] **CONFIG-04**: Backend-specific config (connection params) is passed through to backend constructor

### Tests

- [ ] **TEST-01**: Unit test: PersistenceModule registers correct interfaces with engine
- [ ] **TEST-02**: Unit test: SQLite backend writes events and they can be read back
- [ ] **TEST-03**: Unit test: Buffer flushes when size threshold is reached
- [ ] **TEST-04**: Unit test: Buffer drops oldest events when full (backpressure)
- [ ] **TEST-05**: Unit test: Event filtering only persists subscribed event types
- [ ] **TEST-06**: Unit test: ClickHouse backend writes events (mocked connection)
- [ ] **TEST-07**: Integration test: PersistenceModule + SQLite end-to-end with real engine
- [ ] **TEST-08**: Integration test: Multiple event types persisted in correct tables

## v2 Requirements (Deferred)

(None — deferred to next milestone)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Schema migration management | Initial schema only; migrations come later |
| Query/read interface for persisted data | Write-only milestone; reads in v2 |
| Real-time analytics on persisted data | Separate concern; requires read interface first |
| Multi-database replication | Single instance per module for now |
| GUI/CLI for browsing events | Admin queries sufficient |
| Trading modules | Separate milestone after persistence |
| MessagePack binary storage | JSON text is sufficient and debuggable |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PERSIST-01 | Phase 1 | Pending |
| PERSIST-02 | Phase 1 | Pending |
| PERSIST-03 | Phase 1 | Pending |
| PERSIST-04 | Phase 1 | Pending |
| PERSIST-05 | Phase 1 | Pending |
| PERSIST-06 | Phase 2 | Pending |
| DB-01 | Phase 1 | Pending |
| DB-02 | Phase 1 | Pending |
| DB-03 | Phase 2 | Pending |
| DB-04 | Phase 2 | Pending |
| DB-05 | Phase 1 | Pending |
| DB-06 | Phase 1 | Pending |
| DB-07 | Phase 1 | Pending |
| DB-08 | Phase 2 | Pending |
| SCHEMA-01 | Phase 1 | Pending |
| SCHEMA-02 | Phase 1 | Pending |
| SCHEMA-03 | Phase 1 | Pending |
| SCHEMA-04 | Phase 1 | Pending |
| SCHEMA-05 | Phase 1 | Pending |
| CONFIG-01 | Phase 2 | Pending |
| CONFIG-02 | Phase 1 | Pending |
| CONFIG-03 | Phase 1 | Pending |
| CONFIG-04 | Phase 2 | Pending |
| TEST-01 | Phase 1 | Pending |
| TEST-02 | Phase 1 | Pending |
| TEST-03 | Phase 1 | Pending |
| TEST-04 | Phase 1 | Pending |
| TEST-05 | Phase 2 | Pending |
| TEST-06 | Phase 2 | Pending |
| TEST-07 | Phase 2 | Pending |
| TEST-08 | Phase 2 | Pending |

**Coverage:**
- v1 requirements: 28 total
- Mapped to phases: 28
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-14*
*Last updated: 2026-05-14 after milestone v1.0 started*
