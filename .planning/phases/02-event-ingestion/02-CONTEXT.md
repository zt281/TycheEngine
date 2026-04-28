# Phase 2: Event Ingestion - Context

**Gathered:** 2026-04-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the non-blocking event ingestion pipeline that captures all engine events and durably persists them to ClickHouse without impacting event dispatch latency.

This phase delivers:
- `PersistenceModule` (TycheModule) that subscribes to engine events via ZMQ SUB
- Thread-safe event buffer with configurable size and overflow policy
- Background ingestion worker that batches events and flushes to backend
- Batch flush triggered by size threshold (default 5000) OR timeout (default 1s)
- Graceful shutdown that flushes pending batch
- Exponential backoff retry on ClickHouse failure (max 30s)
- Configurable buffer overflow policy (drop-oldest, drop-newest, block)
- Degradation to JsonlBackend on persistent ClickHouse failure
- Ingestion p99 latency < 1000ms under normal load

**Depends on:** Phase 1 (Schema & Backend Foundation)

</domain>

<decisions>
## Implementation Decisions

### Event Capture Scope
- **D-01:** Configurable filtering with combination conditions (module + event type + instrument). PersistenceModule does NOT capture any events by default — explicit filter configuration is required.
- **D-02:** White-list mode. Only events matching at least one configured filter rule are persisted. Events from unconfigured modules are silently ignored.
- **D-03:** Filter configuration lives in the project config file (e.g., `pyproject.toml` or YAML), not runtime API for v1.

### Buffer Overflow Strategy
- **D-04:** Default overflow policy is **drop-oldest** — when the buffer is full, the oldest events are discarded to make room for new ones. This prioritizes freshness over completeness, which is appropriate for market data.
- **D-05:** Policy is configurable per event type via preset templates. Four built-in templates are provided:
  - `realtime`: quote/trade → drop-oldest; fill/order → block
  - `audit`: all events → block (zero-loss)
  - `performance`: all events → drop-oldest (max throughput)
  - `balanced`: quote → drop-oldest; trade/fill/order → drop-newest
- **D-06:** Default buffer size is **100,000 events**. Configurable per instance.

### Failure Mode (ClickHouse Unreachable)
- **D-07:** **Degradation mode** — after 5 consecutive failures (~2 minutes of exponential backoff), automatically switch to JsonlBackend for local file-based persistence.
- **D-08:** Recovery: every 30 seconds, attempt a ClickHouse health check. If healthy, automatically switch back to ClickHouseBackend.
- **D-09:** Data written to Jsonl during degradation is NOT automatically backfilled to ClickHouse in v1. Files are preserved and can be manually replayed or batch-imported later.
- **D-10:** State transitions (degraded ↔ normal) are broadcast as engine events (`persistence.state`, `persistence.error`) so other modules can observe persistence health.

### Event-to-Row Mapping
- **D-11:** `timestamp` → use `Message.timestamp` if present (set by sender), otherwise `time.time()` at arrival.
- **D-12:** `event_type` → `Message.event` (the event name from the Message object, e.g., "quote", "fill").
- **D-13:** `instrument_id` → `payload.get("instrument_id", "system")`. If the payload does not contain an instrument identifier, use "system" as the default.
- **D-14:** `module_id` → `Message.sender` (the module ID of the event originator, not the persistence module itself).
- **D-15:** `payload` → `msgpack.packb(payload)` (the Message's payload dict, serialized with msgpack and base64-encoded for storage). This matches Phase 1's payload encoding decision.

### Claude's Discretion
- Buffer implementation details (queue.Queue vs collections.deque with maxlen) — use standard library, prefer queue.Queue for blocking semantics
- Batch flush coordination mechanism (timer thread vs condition variable) — standard approach
- Graceful shutdown signal handling (SIGTERM) — register with signal module, delegate to module.stop()
- Exact TOML/YAML config schema for filters — standard nested structure

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project & Requirements
- `.planning/PROJECT.md` — Project vision, core value, constraints, key decisions
- `.planning/REQUIREMENTS.md` — Full v1 requirements with REQ-IDs and traceability (INGT-01..08 for this phase)
- `.planning/ROADMAP.md` — Phase 2 goal, success criteria, dependencies

### Phase 1 Context (prior decisions)
- `.planning/phases/01-schema-backend/01-CONTEXT.md` — Phase 1 decisions that carry forward

### Existing Code
- `src/tyche/module.py` — TycheModule base class, event handler pattern, _event_receiver(), stop()
- `src/tyche/message.py` — Message dataclass, serialize()/deserialize(), msgpack with Decimal encoding
- `src/tyche/types.py` — DurabilityLevel, MessageType, Endpoint, Interface, InterfacePattern
- `src/modules/trading/store/recorder.py` — DataRecorderModule (JSONL writer, to be superseded)
- `src/modules/trading/persistence/backend.py` — PersistenceBackend ABC, InsertResult, QueryResult
- `src/modules/trading/persistence/clickhouse_backend.py` — ClickHouseBackend with insert_batch()
- `src/modules/trading/persistence/jsonl_backend.py` — JsonlBackend (degradation fallback)
- `src/modules/trading/persistence/schema.py` — SchemaManager, events table DDL
- `src/modules/trading/persistence/__init__.py` — Package exports

### Concerns & Architecture
- `.planning/codebase/CONCERNS.md` — Unbounded queue growth risk (line 76), no rate limiting (line 157)
- `.planning/codebase/ARCHITECTURE.md` — Engine architecture, ZMQ patterns

### Design Docs
- `docs/design/tyche_engine_design_v1.md` — Engine architecture, ZMQ patterns
- `docs/design/openctp_gateway_design_v1.md` — CTP gateway design (context for event types)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `TycheModule` base class — PersistenceModule inherits from this; add_interface() + _event_receiver() pattern
- `PersistenceBackend` ABC — insert_batch() returns InsertResult with .success flag (no exceptions for operational errors)
- `ClickHouseBackend.insert_batch()` — batch insert with base64 payload encoding, float→datetime conversion
- `JsonlBackend.insert_batch()` — file-based fallback for degradation mode
- `Message.serialize()/deserialize()` — msgpack with custom Decimal encoding; reuse for payload serialization
- ZMQ SUB socket — already configured with 100ms RCVTIMEO, runs in daemon thread

### Established Patterns
- Threading: daemon threads with `threading.Event` for stop signals; explicit socket cleanup in finally
- Error handling: catches `zmq.error.Again` for timeouts; graceful shutdown checks `self._running`
- Module lifecycle: `__init__` → `add_interface()` → `start_nonblocking()`/`run()` → `stop()`
- Config via constructor kwargs + `**kwargs` passthrough (see DataRecorderModule pattern)

### Integration Points
- PersistenceModule connects to engine via `TycheModule.__init__()` + `add_interface()` for event subscription
- ZMQ SUB socket receives events from engine XPUB; topic = handler name, body = serialized Message
- Backend code lives in `src/modules/trading/persistence/` alongside Phase 1 backends
- Config system: `pyproject.toml` optional-dependencies `[persistence]` for `clickhouse-connect`

### Known Constraints
- Event proxy is single-threaded Python poller loop (not `zmq.proxy()`), bottleneck ~1000-5000 msg/s
- No HWM (high water mark) configured on ZMQ sockets — uses defaults
- `DataRecorderModule` currently lives in `src/modules/trading/store/` and subscribes per-instrument; new PersistenceModule will supersede it

</code_context>

<specifics>
## Specific Ideas

- Filter config TOML example:
  ```toml
  [persistence.ingestion]
  enabled = true
  buffer_size = 100000
  batch_size = 5000
  flush_timeout_ms = 1000
  overflow_policy = "drop-oldest"

  [[persistence.ingestion.filters]]
  module = "ctp_gateway"
  events = ["quote.*", "trade.*", "fill.*"]
  instruments = ["rb2410", "IF2506"]

  [[persistence.ingestion.filters]]
  module = "strategy_engine"
  events = ["order.*"]
  ```
- Degradation event names: `persistence.state` (payload: `{"status": "degraded|normal", "backend": "jsonl|clickhouse"}`), `persistence.error` (payload: `{"error": "...", "retry_count": N}`)
- Preset template selection: `persistence.ingestion.policy_template = "realtime"` — individual event type overrides can be specified below
- Buffer implementation should use `queue.Queue(maxsize=buffer_size)` — drop-oldest can be implemented by `get()` before `put()` when full

</specifics>

<deferred>
## Deferred Ideas

- Runtime filter API (add/remove filters without restart) — v1.x enhancement
- Automatic backfill of Jsonl data to ClickHouse on recovery — v1.x or v2
- Circuit breaker pattern for ClickHouse (instead of simple retry count) — v2
- Buffer size auto-tuning based on throughput metrics — v2
- Per-module buffer isolation (separate queues per event type) — v2
- Compression of payload before storage (beyond base64) — v2, out of scope per PROJECT.md

</deferred>

---

*Phase: 02-event-ingestion*
*Context gathered: 2026-04-29*
