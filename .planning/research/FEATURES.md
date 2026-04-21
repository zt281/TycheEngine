# Feature Research

**Domain:** Event persistence for distributed trading systems
**Researched:** 2026-04-21
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Event ingestion | Core purpose — without this, system is useless | MEDIUM | Must not block event dispatch; async batching required |
| Time-range queries | "What happened between 9:30 and 10:00?" is the #1 query pattern | LOW | ClickHouse `ORDER BY (timestamp)` handles this natively |
| Event-type filtering | Users want only quotes, or only fills, not everything | LOW | Filter on `event_type` column |
| Instrument filtering | Per-symbol analysis is essential for trading | LOW | Filter on `instrument_id` column |
| Basic replay | Backtesting requires replaying historical events | MEDIUM | Order by timestamp, emit at original or accelerated pace |

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Operational metrics | Ingestion lag, drop counts, connection health — critical for production | MEDIUM | Separate metrics table or expose via admin socket |
| Config-driven backend selection | Switch between JSONL (dev), SQLite (test), ClickHouse (prod) without code changes | LOW | Abstract `PersistenceBackend` interface |
| Retention policies | Auto-drop old data to manage storage costs | LOW | ClickHouse TTL + partitioning |
| Multi-event-type single table | Simpler schema than per-type tables; leverages sparse columns | MEDIUM | One `events` table with Nullable columns for type-specific fields |
| At-least-once delivery | Events must not be lost during transient failures | MEDIUM | Ack-based batch commit or idempotent inserts |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Real-time materialized views | "I want live P&L from historical data" | Adds query complexity, maintenance burden, can lag | Ad-hoc SQL queries on raw events; materialized views only for v2+ |
| Event sourcing (rebuild state from events) | "It's the modern way" | Requires snapshotting, complex replay logic, overkill for trading where current state is in memory | Persist events for audit/replay, not for state reconstruction |
| Multi-region replication | "High availability" | Operational complexity exceeds benefit for single-user trading system | Single-node ClickHouse with regular backups |
| UPDATE/DELETE for corrections | "I need to fix bad data" | ClickHouse mutations are expensive and asynchronous | Insert corrected record with higher version; use ReplacingMergeTree |

## Feature Dependencies

```
[Event Ingestion]
    └──requires──> [Schema Definition]
                       └──requires──> [ClickHouse Connection]

[Replay Engine]
    └──requires──> [Event Ingestion]
    └──requires──> [Time-Range Queries]

[Operational Metrics]
    └──requires──> [Event Ingestion]
    └──enhances──> [Config-Driven Backend]

[Retention Policies]
    └──requires──> [Schema Definition]
```

### Dependency Notes

- **Replay requires ingestion:** Cannot replay what hasn't been persisted
- **Metrics enhance backend abstraction:** The same backend interface can expose health metrics
- **Retention requires schema:** TTL and partitioning are schema-level features

## MVP Definition

### Launch With (v1)

- [ ] **Event ingestion** — Batch async ingestion from all engine events to ClickHouse
- [ ] **Schema** — Single `events` table with time-series optimized columns
- [ ] **Query API** — Filter by time range, event type, instrument, module ID
- [ ] **Replay engine** — Read from ClickHouse, emit through engine with simulated clock
- [ ] **Backend abstraction** — Config-driven selection (JSONL dev, ClickHouse prod)

### Add After Validation (v1.x)

- [ ] **Operational metrics** — Ingestion lag, batch sizes, connection health
- [ ] **Retention policies** — TTL-based auto-cleanup by date partition
- [ ] **Bulk import/export** — Load historical data from CSV/Parquet

### Future Consideration (v2+)

- [ ] **Materialized views** — Pre-aggregated OHLCV bars, daily summaries
- [ ] **Multi-node ClickHouse** — Distributed tables for horizontal scaling
- [ ] **Kafka buffer** — Handle bursts beyond single ClickHouse node capacity

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Event ingestion | HIGH | MEDIUM | P1 |
| Schema design | HIGH | LOW | P1 |
| Query API | HIGH | LOW | P1 |
| Replay engine | HIGH | MEDIUM | P1 |
| Backend abstraction | MEDIUM | LOW | P1 |
| Operational metrics | MEDIUM | MEDIUM | P2 |
| Retention policies | MEDIUM | LOW | P2 |
| Materialized views | LOW | HIGH | P3 |
| Kafka buffer | LOW | HIGH | P3 |

## Competitor Feature Analysis

| Feature | QuestDB | TimescaleDB | InfluxDB | Our Approach (ClickHouse) |
|---------|---------|-------------|----------|---------------------------|
| Write throughput | Very high | High | Very high | Very high |
| SQL interface | Full SQL | Full SQL | Flux/InfluxQL | Full SQL |
| Python client maturity | Good | Excellent | Good | Excellent |
| Columnar compression | Good | Good | Good | Excellent |
| Operational complexity | Low | Low | Medium | Low |
| Open source license | AGPL | Apache 2.0 | MIT | Apache 2.0 |

ClickHouse chosen for: best compression, excellent Python ecosystem, Apache 2.0 license, and strong community in finance/trading.

## Sources

- ClickHouse time-series best practices: https://clickhouse.com/docs/en/guides/developer/time-series
- Comparison with TimescaleDB/InfluxDB: Community benchmarks and finance industry usage patterns
- TycheEngine existing codebase analysis: `DataRecorderModule`, `ReplayModule` in `.planning/codebase/`

---
*Feature research for: Event persistence with ClickHouse*
*Researched: 2026-04-21*
