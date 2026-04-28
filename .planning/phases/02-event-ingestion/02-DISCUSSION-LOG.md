# Phase 2: Event Ingestion - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-29
**Phase:** 02-event-ingestion
**Areas discussed:** Event capture scope, Buffer overflow strategy, Failure mode beyond max retry, Event-to-row mapping

---

## Event Capture Scope

| Option | Description | Selected |
|--------|-------------|----------|
| All events | Capture everything on the bus including heartbeats, registrations, system events | |
| Data events only | Only quotes, trades, fills, orders — consistent with DataRecorderModule | |
| Configurable filtering | Combination conditions (module + event type + instrument), white-list mode | ✓ |

**User's choice:** Configurable filtering with combination conditions.
**Follow-up decisions:**
- Default behavior: **no events captured by default**, explicit filter configuration required
- Configuration via: **config file** (TOML/YAML)
- Filter mode: **white-list** (only matching events persisted)
- Filter dimensions: module + event type + instrument (combinable)

**Notes:** User wants per-module filter configuration. New modules without filter rules are silently ignored. This is a departure from DataRecorderModule's per-instrument subscription model.

---

## Buffer Overflow Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| drop-oldest | Discard oldest events when buffer full, keep newest | ✓ |
| drop-newest | Discard new arrivals when buffer full, keep old data | |
| block | Block ZMQ recv thread until space available (causes backpressure) | |

**User's choice:** drop-oldest as default.
**Follow-up decisions:**
- Strategy mode: **configurable per event type** with preset templates
- Built-in templates: **realtime, audit, performance, balanced**
- Buffer size default: **100,000 events**

| Template | quote | trade | fill | order |
|----------|-------|-------|------|-------|
| realtime | drop-oldest | drop-oldest | block | block |
| audit | block | block | block | block |
| performance | drop-oldest | drop-oldest | drop-oldest | drop-oldest |
| balanced | drop-oldest | drop-newest | drop-newest | drop-newest |

**Notes:** User accepted the 4-template proposal. drop-oldest prioritizes freshness — appropriate for market data where the latest price matters most.

---

## Failure Mode Beyond Max Retry

| Option | Description | Selected |
|--------|-------------|----------|
| Infinite retry | Retry every 30s forever, buffer grows until memory exhausted | |
| Silent discard | After N retries, give up and start dropping events | |
| Degradation mode | Switch to JsonlBackend locally, retry ClickHouse in background | ✓ |

**User's choice:** Degradation mode.
**Follow-up decisions:**
- Degradation trigger: **5 consecutive failures** (~2 minutes of exponential backoff)
- Recovery probe interval: **every 30 seconds**
- Recovery mode: **automatic** (health check passes → switch back)
- Data backfill: **no automatic backfill** in v1 (Jsonl files preserved for manual import)
- State broadcast: **yes** — publish `persistence.state` and `persistence.error` events

**Notes:** Degradation mode provides data durability even during ClickHouse outages. JsonlBackend was explicitly built in Phase 1 as a dev/test fallback; reusing it for production degradation is a natural extension. No circuit breaker — simple retry count threshold.

---

## Event-to-Row Mapping

| Row Field | Option A | Option B | Option C | Selected |
|-----------|----------|----------|----------|----------|
| timestamp | Message.timestamp (sender time) | time.time() (arrival time) | | A with B fallback |
| event_type | Message.event | ZMQ topic | | Message.event |
| instrument_id | payload["instrument_id"] | Parse from topic | "system" default | payload.get(..., "system") |
| module_id | Message.sender | PersistenceModule self | | Message.sender |

**User's choice:** Confirmed the proposed mapping rules.
**Rationale:**
- timestamp: Prefer sender time for accuracy (e.g., gateway timestamps from exchange), fallback to arrival time for events without sender timestamp
- event_type: Message.event is the canonical event name (e.g., "quote", "fill"), cleaner than ZMQ topic which includes handler prefix
- instrument_id: payload is the authoritative source; "system" default for events without instrument context (heartbeats, registrations)
- module_id: Message.sender identifies the originator, which is what queries will filter by ("show me all events from CTP gateway")

**Notes:** Payload serialization uses existing msgpack + base64 encoding from Phase 1. No schema changes needed.

---

## Claude's Discretion

- Buffer implementation (queue.Queue vs collections.deque) — standard library approach
- Batch flush coordination mechanism — standard timer/condition pattern
- SIGTERM signal handling — register with signal module
- Config file schema details — standard TOML nested structure

## Deferred Ideas

- Runtime filter API (add/remove without restart) — noted for v1.x
- Automatic backfill of Jsonl to ClickHouse — noted for v1.x/v2
- Circuit breaker pattern — noted for v2
- Per-module buffer isolation — noted for v2

---

*Discussion completed: 2026-04-29*
