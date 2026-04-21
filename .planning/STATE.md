# State: TycheEngine Event Persistence Layer

**Project:** TycheEngine — Event Persistence Layer
**Current Phase:** 1 — Schema & Backend Foundation
**Last Action:** 2026-04-21 — Phase 1 planning complete — 3 plans in 3 waves, all 8 requirements covered, verification passed

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-04-21)

**Core value:** All events flowing through TycheEngine are durably persisted to ClickHouse with sub-second latency, queryable by instrument, time range, event type, and module.
**Current focus:** Phase 1 — Schema & Backend Foundation

## Phase Status

| Phase | Status | Requirements | Completed |
|-------|--------|-------------|-----------|
| 1: Schema & Backend Foundation | **Complete** | 8 | 8/8 |
| 2: Event Ingestion | Not started | 8 | 0/8 |
| 3: Query API & Replay Engine | Not started | 11 | 0/11 |
| 4: Operational Health & Migration | Not started | 5 | 0/5 |

## Active Plans

| Plan | Wave | Status | Files |
|------|------|--------|-------|
| 01-01 | 1 | **Complete** | backend.py, schema.py, tests |
| 01-02 | 2 | **Complete** | clickhouse_backend.py, jsonl_backend.py, __init__.py, tests |
| 01-03 | 3 | **Complete** | docker/clickhouse-compose.yml, pyproject.toml, integration tests |

## Blockers

(None)

## Recent Decisions

| Decision | Date | Status |
|----------|------|--------|
| ClickHouse as backend | 2026-04-21 | Validated |
| clickhouse-connect over asynch | 2026-04-21 | Validated |
| Single events table with event_type column | 2026-04-21 | Validated |
| Batch async ingestion with 1s / 5000 row flush | 2026-04-21 | Pending validation (Phase 2) |

## Verification Results

**Phase 1 — 2026-04-21**
- Unit tests: 263 passed, 0 failed
- Integration tests: 10 passed, 0 failed (live ClickHouse Docker)
- Coverage: ≥90% for new persistence module code

## Fixes Applied During Wave 3 Verification

1. **Removed invalid `pool_size` parameter** — `clickhouse_connect.get_client()` does not accept `pool_size` in the installed version
2. **SQL injection fix** — Switched `query()` filter values from f-string interpolation to clickhouse-connect parameterized queries (`{param:Type}` syntax)
3. **DateTime64 serialization fix** — `clickhouse-connect` requires `datetime` objects (not float epoch) for `DateTime64(3)` columns. Insert path converts `float` → `datetime` (timezone-aware UTC). Query path converts returned naive UTC `datetime` → `float` epoch.

---
*State updated: 2026-04-21 after Wave 3 verification and Phase 1 completion*
