# Module Interface Refactor - Plan v1

> **Design reference:** `docs/design/tyche_engine_design_v2.md`

## Project State at Plan Time

- **Design spec:** v1 defines five interface patterns (`on_`, `ack_`, `whisper_`, `on_common_`, `broadcast_`). v2 has been drafted to replace them with three semantically clear categories (`broadcasted`, `whispered`, `streaming`), each with `on_*` and `handle_*` variants.
- **Plan history:** v1 (project setup) and v2 (process separation) are fully implemented. All tasks closed, CRITICAL empty in impl v2.
- **Impl history:** v2 complete. No open critical items.
- **Baseline tests:** 403 passed, 1 skipped, 1 flaky perf failure (message queue throughput -- pre-existing, not related to this refactor).
- **Current branch:** `refactor/base_module`. Note: `src/tyche/module_base.py` is deleted in the working tree (`D` in git status). The plan treats Task 2 as "create from scratch" rather than "modify existing".
- **Key files:** `src/tyche/types.py`, `src/tyche/module.py`, `src/tyche/engine.py`, `src/tyche/example_module.py`, plus 8 trading modules under `src/modules/trading/`.
- **Out of scope for this refactor:** `EventType` enum cleanup (overlaps with `MessageType` but is not used by the interface system; deferred to future cleanup).

## Problem Statement

The current module system has three architectural problems:

1. **Dual registration mechanisms** -- `ModuleBase.discover_interfaces()` auto-scans methods, but `TycheModule` ignores it and requires manual `add_interface()` calls. This confuses users and leads to duplicated registration code.
2. **Incoherent interface patterns** -- Five patterns (`on_`, `ack_`, `whisper_`, `on_common_`, `broadcast_`) mix delivery semantics (P2P vs broadcast), return semantics (void vs ACK), and naming conventions inconsistently.
3. **Bloated base class** -- `ModuleBase` contains concrete reflection and dispatch logic that is either unused or overridden by `TycheModule`.

## Solution Summary

1. Replace `InterfacePattern` with 6 semantically clear values.
2. Make `TycheModule` auto-discover all interfaces from method names during `__init__`. Remove `add_interface()` from the public API. Keep `_register_handler()` as a protected method for subclasses that need dynamic registration.
3. Slim `ModuleBase` to a pure protocol (abstract property + abstract methods only).
4. Fix known bugs in `TycheModule._dispatch` and `_send_heartbeats`.
5. Update all trading modules to use the new naming convention.

---

## Task 1: Update Core Types

**What:** Replace `InterfacePattern` enum in `src/tyche/types.py`.

**Changes:**
- Remove `ON`, `ACK`, `WHISPER`, `ON_COMMON`, `BROADCAST`.
- Add `ON_BROADCASTED`, `HANDLE_BROADCASTED`, `ON_WHISPERED`, `HANDLE_WHISPERED`, `ON_STREAMING`, `HANDLE_STREAMING`.

**Why:** All downstream code depends on these enum values. This must be the first task.

**Expected result:** `tests/unit/test_types.py` passes with updated assertions.

**Files touched:** `src/tyche/types.py`, `tests/unit/test_types.py`

**Estimated LOC:** 20 source + 40 test

---

## Task 2: Slim ModuleBase to Pure Protocol

**What:** Create `src/tyche/module_base.py` as a lightweight protocol (file is deleted in working tree, so this is a create, not a modify).

**Changes:**
- Keep `module_id` abstract property.
- Keep `start()` and `stop()` abstract methods.
- Remove all concrete methods (`discover_interfaces`, `get_handler`, `handle_event`).
- Use `typing.Protocol` instead of `ABC`.

**Why:** Separates the contract from the dispatch implementation.

**Expected result:** `tests/unit/test_module_base.py` passes.

**Files touched:** `src/tyche/module_base.py`, `tests/unit/test_module_base.py`

**Estimated LOC:** 25 source + 50 test

---

## Task 3: Refactor TycheModule Core

**What:** Rewrite `src/tyche/module.py` to use pure auto-discovery and fix bugs.

**Changes:**
- `__init__`: Call `_discover_and_register_handlers()` after super init. This method scans all methods on `self` using `_pattern_for_name()` and registers matching handlers automatically.
- `add_interface`: **Remove from public API.** Keep private `_register_handler(name, handler, pattern, durability)` for subclasses that need dynamic registration at runtime (e.g., `DataRecorderModule.subscribe_instrument()`).
- `_dispatch`: For `handle_*` prefixes, return `handler(msg.payload)`. For `on_*` prefixes, call `handler(msg.payload)` and return `None`.
- `_send_heartbeats`: Replace the `for _ in range(...)` busy-wait with `self._stop_event.wait(HEARTBEAT_INTERVAL)`.
- Remove unused `event_endpoint` parameter from `__init__`.
- Rename `_event_pub_port` / `_event_sub_port` to `_engine_pub_port` / `_engine_sub_port` for clarity.

**Why:** Core of the refactor. Fixes dual-mechanism, ACK bug, and heartbeat busy-wait.

**Test strategy:** The existing `test_module.py` only covers `add_interface()` and lifecycle. This task must also expand the test file to cover:
- Auto-discovery of all 6 patterns from method names
- `_dispatch()` behavior: `on_*` calls handler and returns `None`; `handle_*` calls handler and returns its `dict` result
- `_register_handler()` works for dynamic registration
- Heartbeat sleep uses `stop_event.wait()` (mocked)

**Expected result:** `tests/unit/test_module.py` passes with expanded coverage.

**Files touched:** `src/tyche/module.py`, `tests/unit/test_module.py`

**Estimated LOC:** 120 source + 120 test

---

## Task 4: Update Engine for New InterfacePattern Values

**What:** Ensure `src/tyche/engine.py` handles the new enum values.

**Changes:**
- `_create_module_info`: `InterfacePattern(i["pattern"])` works generically for any enum value. Verify no hardcoded references to old enum names exist.
- Engine stores interfaces opaquely; no routing logic changes needed.

**Why:** Engine's pattern usage is deserialization-only.

**Expected result:** Integration tests pass.

**Files touched:** `src/tyche/engine.py` (verification, likely no changes)

**Estimated LOC:** 0-10 source + 60 test

---

## Task 5: Update ExampleModule and Core Integration Tests

**What:** Rewrite `src/tyche/example_module.py` to use new naming conventions.

**Method renames:**
| Old | New |
|-----|-----|
| `on_data` | `on_streaming_data` |
| `ack_request` | `handle_broadcasted_request` |
| `whisper_athena_message` | `on_whispered_message` |
| `on_common_broadcast` | `on_broadcasted_broadcast` |
| `on_common_ping` | `on_broadcasted_ping` |
| `on_common_pong` | `on_broadcasted_pong` |

**Changes:**
- Remove manual `discover_interfaces()` + `add_interface()` loop in `__init__`.
- Update `send_event` calls to use new topic names.

**Test updates:**
- `tests/integration/test_engine_module.py`
- `tests/integration/test_multiprocess.py`
- `tests/unit/test_heartbeat_protocol.py`
- `tests/unit/test_signal_handling.py`

**Expected result:** All core integration tests pass. `test_trading_pipeline.py` is NOT expected to pass yet (it is covered in Task 6).

**Files touched:** `src/tyche/example_module.py`, `src/tyche/module_main.py`, 4 test files

**Estimated LOC:** 80 source + 120 test

---

## Task 6: Update Trading Modules

**What:** Update all 8 trading modules to use auto-discovery.

**Affected modules:**
- `src/modules/trading/strategy/base.py`
- `src/modules/trading/risk/module.py`
- `src/modules/trading/portfolio/module.py`
- `src/modules/trading/oms/module.py`
- `src/modules/trading/gateway/base.py`
- `src/modules/trading/store/recorder.py`
- `src/modules/trading/store/replay.py`
- `src/modules/trading/clock/clock.py`

### Migration strategy by module

#### 1. RiskModule (`risk/module.py`)
- Static handlers only. Rename `_handle_order_submit` to `handle_broadcasted_order_submit` and `_handle_position_update` to `on_broadcasted_position_update`.
- Remove `add_interface()` calls. No dynamic registration needed.

#### 2. StrategyModule (`strategy/base.py`)
- Per-instrument quote/trade handlers are dynamic (loop over `self._instruments` at init time). Convert to generic handlers:
  ```python
  def on_streaming_quote(self, payload: dict) -> None:
      instrument_id = payload.get("instrument_id")
      if instrument_id in self._instruments:
          self.on_quote(Quote.from_dict(payload))

  def on_streaming_trade(self, payload: dict) -> None:
      instrument_id = payload.get("instrument_id")
      if instrument_id in self._instruments:
          self.on_trade(Trade.from_dict(payload))
  ```
- Remove `_register_trading_handlers()` and all `add_interface()` calls.
- `subscribe_instrument()` at runtime: since this only adds to `self._instruments`, the generic handler will pick it up automatically. No dynamic registration needed.
- `subscribe_bars()`: convert to `on_streaming_bar(self, payload)` with timeframe/instrument filtering.
- Static handlers (`on_order_update`, `on_position_update`, `on_clock`) rename to `on_broadcasted_order_update`, `on_broadcasted_position_update`, `on_broadcasted_system_clock`.

#### 3. PortfolioModule (`portfolio/module.py`)
- `_handle_fill`: rename to `on_broadcasted_fill`. Fills are broadcast (any module can listen).
- `subscribe_quotes()`: convert to generic `on_streaming_quote(self, payload)` with instrument filtering, same pattern as StrategyModule. Remove dynamic `add_interface()` calls.

#### 4. OMSModule (`oms/module.py`)
- `_handle_order_approved`: rename to `on_broadcasted_order_approved`.
- `_handle_fill`: rename to `on_broadcasted_fill`.
- `_handle_cancel_request`: rename to `on_broadcasted_order_cancel`.
- **Gateway routing change:** Currently OMS constructs `ack_order_execute_{venue}` as the event topic. Under v2, OMS sends a single event `handle_whispered_order_execute` with `venue` in the payload. Each Gateway subscribes to this event and filters by `payload["venue"] == self.venue_name`.
  - Update `_handle_order_approved` to send `handle_whispered_order_execute` with venue in payload.
  - Update `_handle_cancel_request` to send `handle_whispered_order_cancel` with venue in payload.

#### 5. GatewayModule (`gateway/base.py`)
- `_handle_order_execute`: rename to `handle_whispered_order_execute`. Add venue filtering at the top:
  ```python
  def handle_whispered_order_execute(self, payload: dict) -> dict:
      if payload.get("venue") != self.venue_name:
          return {"status": "ignored", "reason": "venue_mismatch"}
      ...
  ```
- `_handle_order_cancel`: rename to `handle_whispered_order_cancel` with same venue filtering.
- Remove `add_interface()` calls from `__init__`.
- **Note:** This moves venue routing from topic-name-based to payload-based. All Gateways receive the same event topic but only process those matching their venue.

#### 6. DataRecorderModule (`store/recorder.py`)
- Convert to generic `on_streaming_quote` and `on_streaming_trade` handlers that record all events (no filtering needed — recording everything is acceptable).
- `subscribe_instrument()` at runtime: keep using `_register_handler()` to dynamically add instrument-specific handlers if fine-grained filtering is still desired. This is a legitimate use of the protected dynamic registration API.
- `on_broadcasted_fill` and `on_broadcasted_order_update` for fill/order recording.

#### 7. ReplayModule (`store/replay.py`)
- No event handlers to register (it publishes, not subscribes). Only needs `send_event` calls updated to new topic names if any.

#### 8. LiveClockModule (`clock/clock.py`)
- No event handlers to register (it publishes `system.clock`). Update `send_event` call if needed.

### Events constants update
- Update `src/modules/trading/events.py` comments to reference new patterns (e.g., "Strategy -> Risk (handle_broadcasted pattern)" instead of "ack_ pattern").

### Test expectations
- `tests/integration/test_trading_pipeline.py` is expected to pass **after Task 6 completes**. It exercises business logic via direct handler calls, so the main risk is method rename mismatches.
- Additional unit tests for each trading module's interface naming are **recommended but not required** for this phase; the pipeline test provides sufficient coverage.

**Expected result:** `tests/integration/test_trading_pipeline.py` passes.

**Files touched:** 8 trading modules, `src/modules/trading/events.py`, `tests/integration/test_trading_pipeline.py`

**Estimated LOC:** 180 source + 40 test

---

## Task 7: Update Public API and Documentation

**What:** Update `src/tyche/__init__.py`, README, and wiki.

**Changes:**
- Verify exports are correct (especially if `ModuleBase` becomes a `Protocol`).
- Update README examples to use new naming conventions.
- Update `.qoder/repowiki/` API reference docs for `TycheModule` and `ModuleBase`.

**Expected result:** No import errors. Documentation matches code.

**Files touched:** `src/tyche/__init__.py`, `README.md`, `.qoder/repowiki/en/content/...`

**Estimated LOC:** 30 source + 50 docs

---

## Verification

Run the full test suite after all tasks:
```bash
pytest tests/ -v
```

Success criteria:
- All unit tests pass
- All integration tests pass (except pre-existing flaky perf test)
- No old `InterfacePattern` values in source
- `add_interface()` not used in public API (only `_register_handler()` in protected contexts)

## Dependencies

```
Task 1 -> Task 2 -> Task 3 -> Task 4 -> Task 5 -> Task 6 -> Task 7
```

Strict sequential dependency.
