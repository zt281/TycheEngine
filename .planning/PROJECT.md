# TycheEngine

## What This Is

A high-performance distributed event-driven trading engine built on ZeroMQ. TycheEngine provides the core broker, module lifecycle, heartbeat protocol, and message routing. Trading modules plug into the engine and communicate via pub/sub and request/response patterns. This milestone adds database persistence so all events can be recorded for replay, audit, and analysis.

## Core Value

All events flowing through TycheEngine can be persisted to a database for replay, audit, and analysis — with zero configuration for local development (SQLite) and production-grade throughput (ClickHouse).

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

## Current Milestone: v1.0 Persistence Module

**Goal:** A pluggable database persistence module that subscribes to TycheEngine message queue events and writes them to ClickHouse (with SQLite fallback), fully tested and registerable with the engine.

**Target features:**
- ClickHouse backend for high-throughput event persistence
- SQLite fallback backend for local/dev use
- Module integrates with TycheEngine's pub/sub system via `TycheModule` base class
- Configurable event filtering (which event types to persist)
- Batch/buffered writes for efficiency
- Unit and integration tests

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] A `PersistenceModule` that subscribes to engine events and writes them to a database backend
- [ ] ClickHouse backend for high-throughput production deployments
- [ ] SQLite backend for local development and testing (zero-config fallback)
- [ ] Configurable event type filtering (subscribe to all or subset)
- [ ] Batch/buffered writes for efficiency (not per-event DB round-trip)
- [ ] Clean module lifecycle: `start()` connects DB, `stop()` flushes buffer and closes gracefully
- [ ] Unit tests with mocked DB connections verifying write logic
- [ ] Integration tests proving real DB writes for events, market data, and order/position snapshots

### Out of Scope

| Feature | Reason |
|---------|--------|
| Schema migration management | Initial schema setup only, no versioning |
| Query/read interface for persisted data | Write-only for this milestone; reads come later |
| Real-time analytics on persisted data | Defer to v2 |
| Multi-database replication or clustering | Single database instance per module |
| GUI or CLI for browsing persisted events | Engine admin queries sufficient for now |
| Trading modules (gateway, OMS, risk, portfolio) | Separate milestone after persistence is solid |

## Context

TycheEngine is a ZeroMQ-based event broker for trading systems. It supports module registration, heartbeat monitoring, event pub/sub via XPUB/XSUB, and job routing. The engine already has `TycheModule` (in `src/tyche/module.py`) which handles socket setup and event discovery.

Key files in the existing codebase:
- `src/tyche/engine.py` — `TycheEngine` broker
- `src/tyche/module.py` — `TycheModule` base class with registration, pub/sub, heartbeat
- `src/tyche/types.py` — `Interface`, `InterfacePattern`, `ModuleInfo`, `MessageType`
- `src/tyche/events.py` — event name constants
- `src/tyche/message.py` — `Message` serialization with MessagePack
- `src/tyche/heartbeat.py` — heartbeat monitoring
- `src/tyche/cpp/` — C++ type bindings
- `src/tyche/rust/` — Rust extension bindings

## Constraints

- **Tech stack**: Python 3.9+, ZeroMQ, msgpack, pytest. ClickHouse driver + sqlite3 (stdlib).
- **Module location**: `src/tyche/persistence/` (new package)
- **Test runtime**: Unit tests < 5 seconds; integration tests may take longer for DB setup
- **Module pattern**: All modules inherit from `TycheModule`, use `on_*` for consumers, `send_*` for producers

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| ClickHouse primary, SQLite fallback | ClickHouse for columnar analytics throughput; SQLite for zero-config dev/test | — Pending |
| Subscribe to all events by default, filter configurable | Easiest to use; filtering is opt-in optimization | — Pending |
| Buffer/batch writes | Per-event DB round-trip would bottleneck the engine's dispatch path | — Pending |
| Use `TycheModule` base class | Avoid re-implementing socket boilerplate; follows engine conventions | — Pending |
| Persistence before trading modules | Events need a place to go before trading logic generates them | — Pending |

---
*Last updated: 2026-05-14 after milestone v1.0 started*
