# Phase 1: Schema & Backend Foundation - Context

**Gathered:** 2026-04-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Establish the database schema and persistence backend abstraction so all storage implementations are swappable and testable. This phase delivers:
- Abstract `PersistenceBackend` interface
- `ClickHouseBackend` with connection pooling and schema management
- `JsonlBackend` as dev/test fallback (refactored from existing `DataRecorderModule`)
- ClickHouse `events` table with optimized time-series schema
- Docker Compose for local ClickHouse dev/CI
- Unit and integration tests for both backends

</domain>

<decisions>
## Implementation Decisions

### Payload Encoding
- **D-01:** `payload` column stores msgpack bytes (opaque binary). Matches existing `Message.serialize()` / `deserialize()` — round-trip fidelity with no conversion loss. ClickHouse stores as `String` type. Phase 3 replay deserializes via `msgpack.unpackb()` into the original Python dict.

### Schema Versioning
- **D-02:** Lightweight approach for v1: `CREATE TABLE IF NOT EXISTS` for initial schema, plus a `schema_meta` table tracking a single `version` integer. No full migration framework in v1 — additive-only changes. Proper migration runner deferred to v2 if schema changes become frequent.

### ClickHouse Table Layout
- **D-03:** `events` table uses `ORDER BY (timestamp, instrument_id, event_type)` with daily partitions (`toYYYYMMDD(timestamp)`). Prioritizes time-range queries for replay. Per-instrument filtering within a time range is efficient via the composite ORDER BY.

### Backend Error Contract
- **D-04:** `insert_batch()` and `query()` return explicit result objects (`InsertResult`, `QueryResult`) with `.success`, `.rows_inserted` / `.rows`, and `.error` fields. No exceptions for operational errors (connection failures, timeouts). Phase 2's retry and backpressure logic checks `.success` directly.

### Claude's Discretion
- Backend config defaults (host=localhost, port=8123, database=tyche) — use standard ClickHouse defaults
- Connection pool sizing (default 4 connections) — standard for HTTP client
- `jsonl` backend file naming convention — follow existing `DataRecorderModule` pattern

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project & Requirements
- `.planning/PROJECT.md` — Project vision, core value, constraints, key decisions
- `.planning/REQUIREMENTS.md` — Full v1 requirements with REQ-IDs and traceability
- `.planning/ROADMAP.md` — Phase 1 goal, success criteria, dependencies

### Research
- `.planning/research/STACK.md` — ClickHouse stack choices, library versions, alternatives
- `.planning/research/ARCHITECTURE.md` — Producer-Consumer pattern, backend abstraction, single wide table
- `.planning/research/PITFALLS.md` — 5 critical pitfalls with prevention strategies

### Existing Code
- `src/modules/trading/store/recorder.py` — Existing `DataRecorderModule` (JSONL writer, to be refactored into `JsonlBackend`)
- `src/modules/trading/store/replay.py` — Existing `ReplayModule` (JSONL reader)
- `src/tyche/message.py` — `Message.serialize()` / `deserialize()` with msgpack and custom Decimal encoding
- `src/tyche/module.py` — `TycheModule` base class, event handler pattern
- `src/tyche/types.py` — Core types: `Endpoint`, `MessageType`, `DurabilityLevel`, etc.

### Design Docs
- `docs/design/tyche_engine_design_v1.md` — Engine architecture, ZMQ patterns
- `docs/design/openctp_gateway_design_v1.md` — CTP gateway design (context for event types)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `DataRecorderModule` — Logic for date-partitioned JSONL writes can be refactored into `JsonlBackend`
- `Message.serialize()` / `deserialize()` — msgpack with Decimal custom encoding; reuse for payload encoding
- `TycheModule` event handler pattern — `add_interface()` + `_record_event(payload: Dict[str, Any])`

### Established Patterns
- All modules inherit from `TycheModule`; persistence module will follow same pattern
- Threading: daemon threads with `threading.Event` for stop signals; explicit socket cleanup in `finally`
- Error handling: ZMQ timeout loops catch `zmq.error.Again`; graceful shutdown checks `self._running`
- Dataclasses with `to_dict()` / `from_dict()` for all models

### Integration Points
- New code connects to engine via `TycheModule.__init__()` + `add_interface()` for event subscription
- `DataRecorderModule` currently lives in `src/modules/trading/store/` — persistence backend code should go here or in a new `src/modules/trading/persistence/` package
- Config system: `pyproject.toml` optional-dependencies `[persistence]` for `clickhouse-connect`

</code_context>

<specifics>
## Specific Ideas

- Docker Compose file for ClickHouse dev: `clickhouse/clickhouse-server:24` with HTTP port 8123
- `schema_meta` table: `CREATE TABLE schema_meta (version UInt32, applied_at DateTime64(3)) ENGINE = MergeTree ORDER BY version`
- `events` table initial DDL:
  ```sql
  CREATE TABLE IF NOT EXISTS events (
      timestamp DateTime64(3),
      event_type LowCardinality(String),
      instrument_id LowCardinality(String),
      module_id String,
      payload String
  ) ENGINE = MergeTree()
  PARTITION BY toYYYYMMDD(timestamp)
  ORDER BY (timestamp, instrument_id, event_type)
  ```
- Result types:
  ```python
  @dataclass
  class InsertResult:
      success: bool
      rows_inserted: int = 0
      error: Optional[str] = None

  @dataclass
  class QueryResult:
      success: bool
      rows: List[Dict[str, Any]] = field(default_factory=list)
      error: Optional[str] = None
  ```

</specifics>

<deferred>
## Deferred Ideas

- Full migration framework (Alembic-style) for schema changes — v2 consideration
- Dedicated columns for frequently-queried payload fields (price, quantity, side) — v1.x if query performance needs it
- ClickHouse cluster / distributed tables — v2
- SQLite backend — explicitly out of scope per PROJECT.md

</deferred>

---

*Phase: 01-schema-backend*
*Context gathered: 2026-04-21*
