# Phase 1: Schema & Backend Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-21
**Phase:** 1-Schema & Backend Foundation
**Areas discussed:** Payload Encoding, Schema Versioning, ClickHouse Table Layout, Backend Error Contract

---

## Payload Encoding

| Option | Description | Selected |
|--------|-------------|----------|
| msgpack bytes | Matches existing Message.serialize(), compact, fast round-trip | ✓ |
| JSON string | Human-readable, ClickHouse JSON functions work | |
| Hybrid (columns + msgpack) | Best query performance, most flexible | |

**User's choice:** msgpack bytes (after asking which is best for replay)
**Notes:** User confirmed msgpack is the right choice for round-trip fidelity and replay speed. Tradeoff: no ClickHouse JSON functions on payload, but filtering happens on common columns anyway.

---

## Schema Versioning

| Option | Description | Selected |
|--------|-------------|----------|
| Lightweight (CREATE TABLE IF NOT EXISTS + additive-only) | Simplest, no migration tooling | |
| Version table + explicit migrations | Robust, industry standard | |
| Hybrid (lightweight v1, proper versioning v2) | v1: idempotent creation + schema_meta table | ✓ |

**User's choice:** Hybrid approach
**Notes:** v1 has stable initial schema unlikely to change during this milestone. schema_meta table provides hook for future migrations without full framework overhead now.

---

## ClickHouse Table Layout

| Option | Description | Selected |
|--------|-------------|----------|
| ORDER BY (timestamp, instrument_id, event_type) + daily partitions | Time-ordered, best for time-range queries | ✓ |
| ORDER BY (instrument_id, timestamp, event_type) + monthly partitions | Per-instrument clustering, fewer parts | |
| ORDER BY (toStartOfDay(timestamp), instrument_id, event_type) + monthly | Compromise: day-level within instrument | |

**User's choice:** Option A with daily partitions
**Notes:** Primary query pattern for replay is time-range filtering. Daily partitions make TTL and data management simpler. Composite ORDER BY handles per-instrument filtering within time ranges.

---

## Backend Error Contract

| Option | Description | Selected |
|--------|-------------|----------|
| Raise exceptions | Pythonic, simple | |
| Return result objects | Explicit, easy for retry logic, testable | ✓ |
| Hybrid (exceptions for bugs, results for ops) | Clean separation | |

**User's choice:** Result objects (InsertResult, QueryResult)
**Notes:** Explicit results make Phase 2 retry/backpressure control flow clearer. Testing is easier with mock backends.

---

## Claude's Discretion

- Backend config defaults (localhost:8123, database=tyche)
- Connection pool sizing (default 4)
- JSONL backend file naming convention

## Deferred Ideas

- Full migration framework (Alembic-style) — v2
- Dedicated payload columns for frequent queries — v1.x
- ClickHouse distributed tables — v2
