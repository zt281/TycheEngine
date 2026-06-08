# Roadmap: TycheEngine v1.0 Persistence Module

## Overview

A two-phase project to build a pluggable database persistence module for TycheEngine. Phase 1 delivers the core module with SQLite backend, schema, buffering, and backpressure — a complete, testable persistence pipeline. Phase 2 adds ClickHouse backend, event filtering, health metrics, and integration tests — production-grade throughput and observability.

## Phases

- [ ] **Phase 1: Core Persistence + SQLite Backend** — PersistenceModule as TycheModule subclass, SQLite backend, event schema, buffering, backpressure, and unit tests
- [ ] **Phase 2: ClickHouse Backend + Production Hardening** — ClickHouse backend, event filtering, health metrics, backend-specific config, and integration tests

## Phase Details

### Phase 1: Core Persistence + SQLite Backend
**Goal**: Users can persist TycheEngine events to SQLite with zero configuration — the module auto-registers, buffers events, handles backpressure, and flushes cleanly on shutdown.
**Depends on**: Nothing (first phase)
**Requirements**: PERSIST-01, PERSIST-02, PERSIST-03, PERSIST-04, PERSIST-05, DB-01, DB-02, DB-05, DB-06, DB-07, SCHEMA-01, SCHEMA-02, SCHEMA-03, SCHEMA-04, SCHEMA-05, CONFIG-02, CONFIG-03, TEST-01, TEST-02, TEST-03, TEST-04
**Success Criteria** (what must be TRUE):
  1. `PersistenceModule` auto-registers with `TycheEngine` as a `TycheModule` subclass and receives events via pub/sub
  2. Events are buffered in memory and written to SQLite in batches (not per-event round-trips)
  3. SQLite database auto-creates `events`, `market_data`, `orders`, and `positions` tables on first connection with correct schema
  4. Buffer flushes automatically when size threshold (1000 events) is reached or `flush_interval` (5s) elapses
  5. When buffer is full, oldest events are dropped to make room for new ones (backpressure), and dropped count is tracked
  6. On `stop()`, all buffered events flush to disk before the module shuts down gracefully
  7. Unit tests verify module registration, SQLite writes, buffer flush, and backpressure behavior
**Plans**: TBD

### Phase 2: ClickHouse Backend + Production Hardening
**Goal**: Users can switch to ClickHouse for production-grade throughput, filter which events to persist, and monitor persistence health via published metrics.
**Depends on**: Phase 1
**Requirements**: PERSIST-06, DB-03, DB-04, DB-08, CONFIG-01, CONFIG-04, TEST-05, TEST-06, TEST-07, TEST-08
**Success Criteria** (what must be TRUE):
  1. Backend selection is configurable (`sqlite` or `clickhouse`) via constructor parameter; both share the same `Backend` protocol interface
  2. ClickHouse backend connects to a configurable host/port and auto-creates MergeTree-engine tables matching the shared schema
  3. Event type filtering is configurable — only subscribed event types are persisted (default: all events)
  4. Backend-specific connection config (host, port, user, password for ClickHouse) passes through to the backend constructor
  5. `PersistenceModule` publishes health metrics (buffer size, dropped count, write latency) as engine events
  6. Unit tests verify event filtering logic and ClickHouse writes (with mocked connection)
  7. Integration tests verify end-to-end persistence with real SQLite and correct table routing for multiple event types
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Core Persistence + SQLite Backend | 0/TBD | Not started | - |
| 2. ClickHouse Backend + Production Hardening | 0/TBD | Not started | - |
