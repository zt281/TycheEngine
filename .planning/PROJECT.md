# TycheEngine — Event Persistence Layer

## What This Is

A unified event persistence backend for TycheEngine that durably logs all inter-module events — market data (quotes, trades, bars), order flow (submits, fills, updates), and internal engine events (heartbeats, registrations, state changes) — to ClickHouse. Replaces the ad-hoc JSONL recorder with a queryable, scalable columnar store that supports both real-time analytics and historical replay.

## Core Value

All events flowing through TycheEngine are durably persisted to ClickHouse with sub-second latency, queryable by instrument, time range, event type, and module — enabling backtesting, audit trails, and real-time analytics without losing data.

## Requirements

### Validated

- ✓ Basic event recording to JSONL files — `DataRecorderModule` writes date-partitioned JSONL
- ✓ Event replay from JSONL — `ReplayModule` reads and replays in timestamp order with simulated clock
- ✓ Core engine event system — XPUB/XSUB proxy, message serialization with msgpack
- ✓ Trading data models — Order, Fill, Quote, Trade, Bar, Position, Account with `to_dict()`/`from_dict()`
- ✓ CTP gateway with auto-reconnect — market data and order events are generated and published

### Active

- [ ] Unified event persistence abstraction that can route all engine events to a pluggable backend
- [ ] ClickHouse backend with optimized schema for time-series event data
- [ ] Event ingestion with batching, backpressure, and at-least-once delivery guarantees
- [ ] Query API for filtering events by instrument, time range, event type, module ID
- [ ] Replay engine that reads from ClickHouse instead of JSONL
- [ ] Migration path: JSONL recorder deprecated, config-driven backend selection
- [ ] Retention policies and table partitioning (by date, instrument)
- [ ] Operational health: ingestion lag metrics, connection status, dropped event counts

### Out of Scope

- Multi-region ClickHouse replication — single-node or single-cluster for v1
- Real-time streaming analytics (materialized views) — deferred to v2; v1 supports ad-hoc queries only
- Compression at rest beyond ClickHouse defaults — not a priority for v1
- Event sourcing / command sourcing — we persist events, not rebuild state from them
- GUI for querying events — CLI and programmatic API only for v1

## Context

TycheEngine is a high-performance distributed event-driven framework built on ZeroMQ. Modules (gateways, strategies, OMS, risk, portfolio) communicate via the engine's XPUB/XSUB event proxy. Currently, only market data events can be recorded to JSONL via `DataRecorderModule`, and only `ReplayModule` can read them back. There is no persistence for order flow, fills, or internal engine events. The JSONL format is not queryable and does not scale.

ClickHouse is chosen because:
- Columnar storage is ideal for time-series event data with many repeated values (instrument_id, event_type)
- High write throughput matches the event volume from market data tick streams
- SQL interface enables ad-hoc analytics without a separate query engine
- Python ecosystem has mature async clients (`clickhouse-connect`, `asynch`)

## Constraints

- **Tech stack:** Python 3.9+, ZeroMQ, msgpack, ClickHouse 24.x
- **Dependencies:** Add `clickhouse-connect>=0.7.0` as optional `[persistence]` extra
- **Compatibility:** Must not break existing `DataRecorderModule` / `ReplayModule` APIs — deprecate, don't remove
- **Performance:** Ingestion p99 latency < 100ms per batch; should not block event dispatch path
- **Testing:** Must work with ClickHouse running in Docker for CI; mock for unit tests

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| ClickHouse as backend | Columnar, high write throughput, SQL queryable, good Python client ecosystem | — Pending |
| Batch async ingestion | Avoids blocking ZMQ event threads; matches ClickHouse's batch-optimized design | — Pending |
| Single events table with event_type column | Simpler schema than per-event-type tables; leverages columnar compression for sparse fields | — Pending |
| `clickhouse-connect` over `asynch` | Simpler API, HTTP interface, built-in connection pooling, good documentation | — Pending |

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

---
*Last updated: 2026-04-21 after initialization*
