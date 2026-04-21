# Concerns & Technical Debt

*Generated: 2026-04-21*

## No TODOs/FIXMEs Found

A codebase-wide grep for `TODO`, `FIXME`, `XXX`, `HACK`, and `BUG` returned no matches. This suggests either disciplined cleanup or under-documented known issues.

## Areas of Concern

### 1. CTP Thread Safety

The CTP gateway bridges CTP's internal SPI callback threads with TycheEngine's ZMQ threads via a `queue.Queue`. While this is the correct pattern, the `_event_dispatcher` thread and `_reconnect_loop` thread share mutable state:
- `_md_api` / `_td_api` handles are nulled during reconnect while the dispatcher may still reference them
- `_subscribed_instruments` is accessed without locks during reconnect resubscription

**File:** `src/modules/trading/gateway/ctp/gateway.py` (lines ~996-1035)

### 2. Reconnect Race Conditions

The auto-reconnect loop creates new API instances and starts a new dispatcher thread without fully synchronizing with the old ones. The old dispatcher is stopped with `_dispatcher_stop.set()` and a 5s join, but if CTP callbacks are blocked, this could leak threads.

**File:** `src/modules/trading/gateway/ctp/gateway.py` — `_reconnect_loop()`

### 3. Position Accumulator State

`OnRspQryInvestorPosition` accumulates position records into `_position_accumulator` keyed by `instrument_id`. If a query is interrupted (not `bIsLast`), partial state remains in the accumulator. There is no timeout or cleanup for stale accumulator entries.

**File:** `src/modules/trading/gateway/ctp/gateway.py` (lines ~578-641)

### 4. Missing Performance & Property Tests

The `tests/perf/` and `tests/property/` directories exist but contain no tests. The design spec mentions:
- p99 latency < 10μs for dispatch path
- All serialization round-trips via hypothesis

Neither is currently implemented.

### 5. Type Inconsistencies

Some files use `List[str]` (older style) while others use `list[str]` (Python 3.9+). The codebase requires Python >=3.9 so the newer style is preferred, but not consistently applied.

Examples:
- `src/tyche/types.py`: `List[str]` in `ModuleInfo`
- `src/tyche/heartbeat.py`: `list[str]` in `HeartbeatManager`

### 6. Error Event Handling

CTP `OnRspError` publishes `gateway.error` events but there is no consumer subscribed to handle them. The risk module and strategy base do not register handlers for `gateway.error`, so these events are silently dropped by the engine.

**File:** `src/modules/trading/gateway/ctp/gateway.py` — `_publish_error()`

### 7. Simulated Gateway Coverage

`src/modules/trading/gateway/simulated.py` exists but has no corresponding test file. The CTP gateway has extensive tests; the simulated gateway appears untested.

### 8. TUI Unlinked

The `tui/` directory contains a TypeScript/React dashboard but there is no documented integration point with the Python engine. It appears to be a standalone or work-in-progress component.

### 9. Flow File Cleanup

CTP API flow files are written to `ctp_flow/md/` and `ctp_flow/td/`. These directories are created with `os.makedirs(..., exist_ok=True)` but never cleaned up. Over time this could accumulate stale flow data.

### 10. Engine Shutdown Gracefulness

`TycheEngine.stop()` sets `_running = False` and `_stop_event.set()`, then joins threads with a 2s timeout. If a thread is blocked on a ZMQ recv, it may not respond within 2s. The context is then destroyed with `linger=0`, which forcibly closes sockets. This is generally safe but may drop in-flight messages.

**File:** `src/tyche/engine.py` — `stop()` method (lines 121-132)

## Security Notes

- CTP credentials (password, auth code) are passed as plain strings through the config system. The config loader reads from JSON files and environment variables but does not encrypt or hash credentials.
- No secrets scanning in CI beyond standard GitHub features.

## Fragile Areas

| Area | Risk | Mitigation |
|------|------|------------|
| CTP reconnect | Thread leaks, state corruption | Limited testing; relies on integration tests |
| Position query | Partial accumulator state | No timeout/cleanup |
| Error events | No consumers | Events published to void |
| Engine shutdown | Message loss on force-close | Acceptable for current use case |
