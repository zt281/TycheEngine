---
phase: 01-schema-backend
plan: 03
subsystem: persistence
wave: 3
dependency_graph:
  requires:
    - 01-01
    - 01-02
  provides:
    - Docker Compose ClickHouse dev environment
    - clickhouse-connect dependency
    - Integration test suite for ClickHouseBackend
  affects:
    - docker/clickhouse-compose.yml
    - pyproject.toml
    - tests/integration/test_clickhouse_backend.py
tech_stack:
  added:
    - clickhouse-connect>=0.7.0 (optional dependency)
    - clickhouse/clickhouse-server:24 (Docker image)
  patterns:
    - Docker Compose for local dev/CI
    - pytest.skip for optional external services
    - TRUNCATE TABLE between tests for isolation
key_files:
  created:
    - docker/clickhouse-compose.yml
    - tests/integration/test_clickhouse_backend.py
  modified:
    - pyproject.toml
---

# Phase 01 Plan 03: ClickHouse Dev Infrastructure & Integration Tests Summary

## One-liner

Docker Compose for ClickHouse 24.x, clickhouse-connect dependency, and 10 integration tests verifying round-trip insert/query, filtering, limits, ordering, schema creation, and payload encoding against a real ClickHouse instance.

## What Was Built

### Docker Compose (Task 1)
- `docker/clickhouse-compose.yml` with `clickhouse/clickhouse-server:24` image
- HTTP port 8123 (clickhouse-connect) and native port 9000
- Pre-configured database `tyche` via environment variables
- Named volume `clickhouse_data` for persistence across restarts
- Healthcheck via `wget` HTTP ping with 5 retries, 3s timeout
- ulimits for high file descriptor requirements (262144)

### Dependency (Task 2)
- Added `[project.optional-dependencies] persistence` group to `pyproject.toml`
- `clickhouse-connect>=0.7.0` for ClickHouseBackend production use
- Existing `ctp` and `dev` groups preserved unchanged

### Integration Tests (Task 3)
- `tests/integration/test_clickhouse_backend.py` with 10 test cases:
  1. `test_health_check` — backend connectivity to real ClickHouse
  2. `test_ensure_schema_creates_tables` — DDL creates `events` and `schema_meta`
  3. `test_schema_version_tracking` — `schema_meta` records version 1
  4. `test_insert_and_query_roundtrip` — full insert/query cycle with 3 rows
  5. `test_query_time_range_filter` — `start_ts`/`end_ts` filtering
  6. `test_query_event_type_filter` — `event_type` filtering
  7. `test_query_instrument_id_filter` — `instrument_id` filtering
  8. `test_query_limit` — `limit` parameter enforcement
  9. `test_query_order_by_timestamp` — ascending timestamp ordering
  10. `test_payload_bytes_roundtrip` — base64 payload encoding verification
- Graceful skip via `pytest.skip` when Docker ClickHouse unavailable
- 5-second health poll timeout for fast CI feedback
- `TRUNCATE TABLE IF EXISTS` between tests for isolation

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Reduced health poll timeout from 30s to 5s**
- **Found during:** Task 3 verification
- **Issue:** Original 30-second `max_wait` with 0.5s sleep meant each test took ~30s to skip when ClickHouse was unavailable. With 10 tests, the suite took over 5 minutes.
- **Fix:** Reduced `max_wait` to 5.0 seconds and sleep interval to 0.3s. Total skip time reduced from ~300s to ~52s.
- **Files modified:** `tests/integration/test_clickhouse_backend.py`
- **Commit:** 12141b8

**2. [Runtime Fix] Removed invalid `pool_size` parameter from `ClickHouseBackend`**
- **Found during:** Wave 3 verification (live ClickHouse)
- **Issue:** `clickhouse_connect.get_client()` raised `TypeError: get_client() got an unexpected keyword argument 'pool_size'`
- **Fix:** Removed `pool_size` from `__init__` and `_get_client()` call.
- **Files modified:** `src/modules/trading/persistence/clickhouse_backend.py`

**3. [Security Fix] Replaced f-string SQL interpolation with parameterized queries**
- **Found during:** Wave 3 code review
- **Issue:** `query()` method used f-string interpolation for filter values (`f"event_type = '{event_type}'"`), vulnerable to SQL injection
- **Fix:** Switched to clickhouse-connect parameterized query syntax: `"event_type = {event_type:String}"` with `parameters={...}` dict passed to `client.query()`
- **Files modified:** `src/modules/trading/persistence/clickhouse_backend.py`, `tests/unit/test_clickhouse_backend.py`

**4. [Data Type Fix] Convert float epoch timestamps to datetime for ClickHouse DateTime64(3)**
- **Found during:** Wave 3 verification (live ClickHouse)
- **Issue:** `clickhouse-connect` serializes `DateTime64(3)` columns from `datetime` objects, not raw floats. Passing float timestamps caused `AttributeError: 'float' object has no attribute 'timestamp'`
- **Fix:**
  - Insert path: converts `float` epoch → `datetime.fromtimestamp(ts, tz=timezone.utc)` (timezone-aware UTC datetime)
  - Query path: converts returned naive UTC `datetime` → float epoch via `dt.replace(tzinfo=timezone.utc).timestamp()`
- **Rationale:** clickhouse-connect treats naive datetimes as local time on insert but returns naive UTC on query. Timezone-aware datetimes round-trip correctly regardless of client machine timezone.
- **Files modified:** `src/modules/trading/persistence/clickhouse_backend.py`

## Known Stubs

None — all tests are fully wired to real ClickHouse when available.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: information_disclosure | docker/clickhouse-compose.yml | Empty password is dev-only; production uses separate config |

## Commits

| Task | Hash | Message | Files |
|------|------|---------|-------|
| 1 | 25e9f53 | chore(01-03): add Docker Compose for ClickHouse dev/CI | docker/clickhouse-compose.yml |
| 2 | 271d26d | chore(01-03): add clickhouse-connect dependency in pyproject.toml | pyproject.toml |
| 3 | 12141b8 | test(01-03): add integration tests for ClickHouseBackend round-trip | tests/integration/test_clickhouse_backend.py |

## Self-Check: PASSED

- [x] `docker/clickhouse-compose.yml` exists
- [x] `pyproject.toml` has `clickhouse-connect>=0.7.0` in persistence group
- [x] `tests/integration/test_clickhouse_backend.py` exists with 10 tests
- [x] All 3 commits exist in git history
- [x] Unit tests pass: 263 passed, 0 failed, no regressions
- [x] Integration tests pass against live ClickHouse Docker: 10 passed, 0 failed
- [x] Integration tests skip gracefully when ClickHouse unavailable (5s timeout)
- [x] No `__init__.py` added to tests/ or subdirectories
- [x] No modifications to STATE.md or ROADMAP.md (updated post-verification by team lead)

## Metrics

- **Duration:** ~15 minutes
- **Completed:** 2026-04-21
- **Tasks:** 4/4 completed (including verification checkpoint)
- **Files created:** 2
- **Files modified:** 4 (including runtime fixes to `clickhouse_backend.py` and unit test updates)
- **Tests added:** 10 integration tests
- **Runtime fixes applied:** 3 (pool_size removal, SQL injection, DateTime64 serialization)
