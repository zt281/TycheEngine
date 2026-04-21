---
phase: 01-schema-backend
plan: 02
subsystem: persistence
completed: 2026-04-21
---

# Phase 01 Plan 02: Backend Implementations Summary

**One-liner:** ClickHouseBackend (production with connection pooling) and JsonlBackend (dev/test file-based) both implementing the PersistenceBackend ABC, with explicit package exports.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Implement ClickHouseBackend with connection pooling | cc7264b | `src/modules/trading/persistence/clickhouse_backend.py`, `tests/unit/test_clickhouse_backend.py` |
| 2 | Implement JsonlBackend (refactored from DataRecorderModule) | ff560aa | `src/modules/trading/persistence/jsonl_backend.py`, `tests/unit/test_jsonl_backend.py` |
| 3 | Create package `__init__.py` with explicit exports | 9bf08e9 | `src/modules/trading/persistence/__init__.py` |

## Key Decisions

- **Lazy client initialization:** ClickHouseBackend creates the `clickhouse_connect` client on first use (`_get_client()`) rather than in `__init__`, avoiding connection errors at construction time.
- **Payload encoding:** Both backends accept `payload` as either `bytes` or `str`. Bytes are base64-encoded for storage (ClickHouse String column, JSONL file). This aligns with D-01 (msgpack bytes stored opaquely).
- **File layout:** JsonlBackend uses `{data_dir}/{date}/events.jsonl`, a simplification of the existing DataRecorderModule pattern (which used `{instrument_id}_{event_type}.jsonl`). This keeps the backend interface clean while still being date-partitioned.
- **Error contract (D-04):** All operational errors (connection failures, file I/O, query errors) return `InsertResult` or `QueryResult` with `success=False` and `error` set. No exceptions propagate to callers.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test assertions for base64-encoded payload in query results**
- **Found during:** Task 2 (JsonlBackend GREEN phase)
- **Issue:** Two tests (`test_jsonl_backend_query_filter_by_date_range` and `test_jsonl_backend_query_limit_and_offset`) asserted `payload == "b"` and `payload == "1"` respectively, but JsonlBackend base64-encodes bytes payloads on insert, so query returns the base64 string.
- **Fix:** Updated test assertions to use `base64.b64decode(result.rows[0]["payload"])` and added `import base64` to the test file.
- **Files modified:** `tests/unit/test_jsonl_backend.py`
- **Commit:** Included in ff560aa

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: injection | `clickhouse_backend.py` | `ClickHouseBackend.query()` interpolates filter values directly into SQL strings. This is acknowledged in the plan's threat model (T-02-01) with disposition `mitigate`. The current implementation uses f-string interpolation for filter values. A future hardening should use parameterized queries or strict input validation. |

## Known Stubs

None. All planned functionality is implemented and tested.

## Metrics

- **Duration:** ~15 minutes
- **Tests:** 73 passing (22 ClickHouseBackend + 24 JsonlBackend + 11 backend ABC + 16 SchemaManager)
- **Files created:** 5 (3 source + 2 test)
- **Lines of code:** ~580 (clickhouse_backend.py) + ~240 (jsonl_backend.py) + ~26 (__init__.py)
- **Test coverage:** All new code paths exercised

## Self-Check: PASSED

- [x] `src/modules/trading/persistence/clickhouse_backend.py` exists
- [x] `src/modules/trading/persistence/jsonl_backend.py` exists
- [x] `src/modules/trading/persistence/__init__.py` exists
- [x] `tests/unit/test_clickhouse_backend.py` exists (22 tests)
- [x] `tests/unit/test_jsonl_backend.py` exists (24 tests)
- [x] All 73 tests pass
- [x] Package import verification passes
- [x] Subclass verification passes (ClickHouseBackend and JsonlBackend both subclass PersistenceBackend)
- [x] Commits verified: d4772ad, cc7264b, ff560aa, 9bf08e9
