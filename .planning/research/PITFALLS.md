# Pitfalls Research

**Domain:** Event persistence for distributed trading systems with ClickHouse
**Researched:** 2026-04-21
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: Blocking ZMQ Event Threads with Synchronous DB Writes

**What goes wrong:**
PersistenceModule's event handler calls ClickHouse INSERT directly. Each INSERT takes 10-100ms. The ZMQ SUB socket recv loop blocks, events queue up in ZMQ internal buffers, and eventually events are dropped.

**Why it happens:**
Developers forget that ZMQ socket callbacks run on the module's event receiver thread. Any blocking operation in the handler stalls the entire event stream.

**How to avoid:**
Use a `queue.Queue` to hand off events from the ZMQ thread to a dedicated ingestion thread. The handler does `queue.put_nowait()` (non-blocking); the ingestion thread does batching and INSERT.

**Warning signs:**
- Events appearing out of order in downstream modules
- "Missed heartbeat" warnings from engine
- Memory growth in the module process (ZMQ buffer accumulation)

**Phase to address:** Phase 1 (Event Ingestion)

---

### Pitfall 2: ClickHouse "Too Many Parts" Error

**What goes wrong:**
ClickHouse rejects INSERTs with "Too many parts" error. The merge queue is overwhelmed because inserts are too small or too frequent.

**Why it happens:**
ClickHouse MergeTree engine creates one part per INSERT. Default `parts_to_throw_insert` is 300. If you INSERT every event individually, you hit this limit in seconds.

**How to avoid:**
Batch inserts to 1,000-50,000 rows depending on event size. Use a timeout (e.g., 1 second) so low-volume periods still flush promptly.

**Warning signs:**
- `Too many parts (N). Merges are processing significantly slower than inserts` in ClickHouse logs
- INSERT failures increasing over time
- Query performance degrading

**Phase to address:** Phase 1 (Event Ingestion)

---

### Pitfall 3: Schema Drift Breaking Existing Data

**What goes wrong:**
Adding a new column to the events table changes the INSERT format. Old replay scripts or downstream consumers break because they expect a different column set.

**Why it happens:**
ClickHouse is schemaless-ish for new columns (they get defaults), but client code that does `SELECT *` or builds INSERT tuples manually breaks.

**How to avoid:**
- Always specify column list in INSERTs: `INSERT INTO events (col1, col2) VALUES`
- Version the schema; migration scripts in `schema.py`
- Use `payload` column (msgpack bytes) for extensibility — new event fields go in payload without schema changes

**Warning signs:**
- Tests pass locally but fail in CI (different ClickHouse version)
- Replay crashes on old data after deploying new code

**Phase to address:** Phase 1 (Schema Design)

---

### Pitfall 4: Data Loss on Module Crash Before Batch Flush

**What goes wrong:**
Module crashes with 500 events in the batch buffer. Those events are never persisted.

**Why it happens:**
Batching improves throughput but increases the window of un-persisted data. Without an acknowledgment mechanism, there's no way to recover.

**How to avoid:**
- Accept that at-least-once delivery requires tradeoffs; document the batch window (e.g., "up to 1s of data at risk")
- Add a signal handler that flushes the batch on SIGTERM
- For critical events (fills, order updates), consider a smaller batch size or immediate flush

**Warning signs:**
- Replay shows gaps in event sequence
- Backtest results differ from live runs

**Phase to address:** Phase 1 (Event Ingestion)

---

### Pitfall 5: ClickHouse Connection Failures Not Handled Gracefully

**What goes wrong:**
ClickHouse becomes temporarily unreachable. The ingestion thread crashes or drops all buffered events. No retry logic means data loss.

**Why it happens:**
Developers test against a stable local ClickHouse and don't account for network hiccups, ClickHouse restarts, or overload.

**How to avoid:**
- Implement exponential backoff retry on connection errors
- Keep events in the buffer during retry; only drop on buffer overflow
- Publish `persistence.health` events so operators know when ingestion is failing

**Warning signs:**
- Sudden drop in recorded event count
- `Connection refused` errors in logs without recovery
- Gap in data during known maintenance windows

**Phase to address:** Phase 1 (Event Ingestion)

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| JSON string payload only | No schema changes ever | Cannot query/aggregate payload fields | Only for prototyping; migrate to structured columns before production |
| No tests with real ClickHouse | Faster tests | Schema bugs caught in production | Never — use Docker for integration tests |
| Hardcoded table name | Simpler code | Cannot support multiple environments | Only in v1 MVP; make configurable in v1.1 |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| ClickHouse HTTP | Using sync client from async code | Use `clickhouse-connect` async client or run sync client in executor |
| ClickHouse datetime | Using Python `datetime` without timezone | Use Unix timestamp (Float64) or explicit UTC; ClickHouse `DateTime64(3)` |
| Docker ClickHouse | Not setting `max_insert_threads` or `max_execution_time` | Tune for batch workload; test with same config as production |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Small batch inserts ( <100 rows ) | High CPU on ClickHouse, slow ingestion | Batch to 1K-50K rows | >10K events/sec |
| No ORDER BY optimization | Queries scan entire table | `ORDER BY (timestamp, instrument_id, event_type)` | >1M rows |
| String columns for enums | High storage, slow filtering | Use LowCardinality(String) for event_type, instrument_id | >100K distinct values |
| Daily partitions only | Too many parts per partition | Add `instrument_id` to partition key or use hourly | >10M events/day per instrument |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| ClickHouse exposed on public IP | Unauthorized data access | Bind to localhost or private network; use reverse proxy |
| Default password (`default` / empty) | Full database access | Set strong password in `users.xml` or environment |
| SQL injection in query builder | Data exfiltration or deletion | Use parameterized queries; never f-string SQL |

## "Looks Done But Isn't" Checklist

- [ ] **Ingestion:** Buffer overflow handling tested — what happens when queue is full?
- [ ] **Ingestion:** Graceful shutdown flushes pending batch — verify with SIGTERM test
- [ ] **Schema:** Old data readable after schema change — migration test with existing table
- [ ] **Query:** Timezone handling consistent — events stored in UTC, queries handle conversion
- [ ] **Replay:** Events emitted in strict timestamp order — no out-of-order replay
- [ ] **Health:** Metrics exposed somewhere (admin socket, log, or ClickHouse table)

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Blocked ZMQ thread | LOW | Restart module; add queue-based ingestion |
| Too many parts | MEDIUM | Stop inserts, wait for merges, increase batch size, resume |
| Schema drift | MEDIUM | Add missing columns with defaults; update client code |
| Unflushed batch on crash | HIGH (data loss) | Accept loss for v1; implement WAL for v2 |
| Connection failure | LOW | Retry with backoff; monitor buffer depth |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Blocking ZMQ thread | Phase 1: Event Ingestion | Integration test: module receives 10K events, none dropped, ingestion thread never blocks event handler |
| Too many parts | Phase 1: Event Ingestion | Load test: 100K events in 10 seconds, no "Too many parts" error |
| Schema drift | Phase 1: Schema Design | Unit test: INSERT with old schema data into new schema table succeeds |
| Unflushed batch | Phase 1: Event Ingestion | Integration test: SIGTERM during ingestion, verify all buffered events are flushed |
| Connection failures | Phase 1: Event Ingestion | Integration test: stop ClickHouse container mid-ingestion, verify retry and recovery |

## Sources

- ClickHouse "Too many parts" troubleshooting: https://clickhouse.com/docs/en/faq/operations/production
- ZeroMQ guide (Paranoid Pirate pattern): https://zguide.zeromq.org/
- Personal experience: Batch sizing in high-frequency data pipelines
- TycheEngine codebase: `src/tyche/module.py` event receiver threading model

---
*Pitfalls research for: Event persistence with ClickHouse*
*Researched: 2026-04-21*
