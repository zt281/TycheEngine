# Research Summary: TycheEngine Persistence Module

**Milestone:** v1.0 Persistence Module
**Researched:** 2026-05-14
**Sources:** STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md

---

## Stack Recommendation

- **ClickHouse driver:** `clickhouse-connect >=0.7.0,<1.0.0` (official HTTP driver; v1.0.0+ drops Python 3.9 support)
- **SQLite:** stdlib `sqlite3` — no extra dependency. Enable WAL mode + `synchronous=NORMAL`
- **Batch strategy:** Dual-threshold flush: `BATCH_SIZE` (default 1,000 rows) OR `FLUSH_INTERVAL` (default 5 seconds)
- **Thread safety:** `autogenerate_session_id=False` mandatory for `clickhouse-connect` thread safety
- **Avoid:** `clickhouse-driver` (unofficial, not thread-safe), `SQLAlchemy` (overkill), async libraries (mismatch threading model)

## Feature Priorities

**Build first (table stakes):**
1. `TycheModule` subclass with `on_*` event handlers
2. In-memory buffer with background flush thread
3. `Backend` ABC with `connect()` / `insert_batch()` / `close()`
4. SQLite backend (zero-config, testable immediately)
5. ClickHouse backend (production target)
6. Graceful shutdown with buffer flush

**Defer to later:**
- Configurable event filtering (v1.1)
- Metrics export / health publishing (v1.1)
- Read/replay interface (v2.0)
- ClickHouse partitioning / TTL (v1.1)

## Architecture Overview

The persistence module is a pure `TycheModule` subclass. Zero engine modifications needed.

```
ZMQ Event Receiver Thread
    |
    v
 on_* handler (fast, non-blocking)
    |
    v
 WriteBuffer (active/pending swap under lock)
    |
    v
 Background Flush Thread
    |
    +---> SQLiteBackend (executemany)
    +---> ClickHouseBackend (client.insert)
```

**Critical rule:** DB I/O NEVER happens in the ZMQ receiver thread. Always on the dedicated writer thread.

## Top 5 Pitfalls to Avoid

| # | Pitfall | Prevention |
|---|---------|------------|
| 1 | **Blocking the event loop** — synchronous DB writes in `on_*` stall all dispatch | Offload to background thread; handlers only enqueue |
| 2 | **Shutdown data loss** — buffer not flushed before module stops | Flush in `stop()` before closing DB; extend join timeout if needed |
| 3 | **ClickHouse "too many parts"** — small batches create excessive parts | Batch size >= 1,000 rows; use `async_insert=1` |
| 4 | **SQLite single-writer contention** — concurrent writes hit `SQLITE_BUSY` | Single dedicated writer thread; `BEGIN IMMEDIATE` |
| 5 | **Unbounded buffer growth** — memory exhaustion under backpressure | Bounded buffer with drop-oldest or block policy |

## Open Questions

1. **Peak event throughput** — affects buffer sizing and batch thresholds
2. **ClickHouse deployment model** — self-hosted vs. managed (affects connection strategy)
3. **Retention policy** — how long to keep events?
4. **Field naming conventions** — trading modules (future) may use different names than assumed

## Recommended Phase Structure

| Phase | Focus | Deliverables |
|-------|-------|--------------|
| 1 | **Foundation** | `Backend` ABC, `SQLiteBackend`, `ClickHouseBackend`, `WriteBuffer`, unit tests |
| 2 | **Module Integration** | `PersistenceModule` subclass, engine wiring, integration tests |
| 3 | **Config + Filtering** | Event filtering, batch params, retry/backoff, error handling |
| 4 | **Backend Hardening** | Production tuning: CH partitioning, SQLite WAL, perf tests |

---
*Synthesized: 2026-05-14*
