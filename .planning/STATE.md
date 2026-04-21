# State: TycheEngine Event Persistence Layer

**Project:** TycheEngine — Event Persistence Layer
**Current Phase:** 1 — Schema & Backend Foundation
**Last Action:** 2026-04-21 — Phase 1 context gathered, 4 areas discussed and decided

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-04-21)

**Core value:** All events flowing through TycheEngine are durably persisted to ClickHouse with sub-second latency, queryable by instrument, time range, event type, and module.
**Current focus:** Phase 1 — Schema & Backend Foundation

## Phase Status

| Phase | Status | Requirements | Completed |
|-------|--------|-------------|-----------|
| 1: Schema & Backend Foundation | Context gathered | 8 | 0/8 |
| 2: Event Ingestion | Not started | 8 | 0/8 |
| 3: Query API & Replay Engine | Not started | 11 | 0/11 |
| 4: Operational Health & Migration | Not started | 5 | 0/5 |

## Active Plans

(None — planning phase not yet started)

## Blockers

(None)

## Recent Decisions

| Decision | Date | Status |
|----------|------|--------|
| ClickHouse as backend | 2026-04-21 | — Pending validation |
| clickhouse-connect over asynch | 2026-04-21 | — Pending validation |
| Single events table with event_type column | 2026-04-21 | — Pending validation |
| Batch async ingestion with 1s / 5000 row flush | 2026-04-21 | — Pending validation |

---
*State updated: 2026-04-21 after roadmap creation*
