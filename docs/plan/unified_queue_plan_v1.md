# Unified Message Queue — Plan v1

> **Design reference:** `docs/design/unified_queue_design_v1.md`
> **Predecessor:** `docs/plan/module_interface_refactor_plan_v2.md` (APPROVED, fully implemented and merged)

## Project State at Plan Time

- **Design spec:** `unified_queue_design_v1.md` is written and all three open decisions are resolved (grace-period GC, optional `send_` declarations, configurable backpressure defaulting to drop-oldest).
- **Predecessor plan:** `module_interface_refactor_plan_v2.md` is APPROVED and fully merged to `main` at commit `4f1f2da`.
- **Implementation state of plan v2:**
  - `InterfacePattern` has 6 values (`ON_BROADCASTED`, `HANDLE_BROADCASTED`, `ON_WHISPERED`, `HANDLE_WHISPERED`, `ON_STREAMING`, `HANDLE_STREAMING`).
  - `TycheModule._dispatch` distinguishes `handle_*` (returns dict) from `on_*` (returns None).
  - `TycheModule.send_event_with_response` and `call_ack` exist and connect to the engine's ACK ROUTER socket.
  - Engine has `_ack_worker` (`engine.py:323`) handling COMMAND/RESPONSE correlation via `_ack_correlations`.
  - Engine `_event_proxy_worker` forwards EVENTs directly from XSUB to XPUB, bypassing `_topic_queues`.
  - `_enqueue_from_xsub` exists but is never called.
  - `_event_egress_worker` only drains ACK-enqueued messages.
  - Trading modules use `handle_broadcasted_order_submit` (Risk), `handle_whispered_order_execute`/`handle_whispered_order_cancel` (Gateway), and OMS sends to `"handle_whispered_order_execute"` topics.
- **Test baseline:** 403 passed, 0 critical failures (from `module_interface_refactor_implement_v2.md` Task Log).
- **Current branch:** `main` (clean working tree).

## Problem Statement

The v2 architecture has two irreconcilable routing paths:

1. **Hot path (EVENT):** XPUB/XSUB proxy forwards directly. Fast, but unobservable and bypasses all queue-level backpressure.
2. **Queue path (COMMAND/RESPONSE):** ACK worker enqueues to `_topic_queues`, egress worker drains. Observable, but only used for request-response.

This split prevents unified metrics, backpressure, and persistence. Additionally, the 6 `InterfacePattern` variants and `handle_*` request-response coupling add complexity without proportional value—event chaining can express the same workflows with looser coupling.

## Solution Summary

1. **Collapse `InterfacePattern` to `ON` and `SEND`** (Task 1).
2. **Add `BackpressureStrategy`** and wire it into `Interface` (Task 1).
3. **Update module discovery and dispatch** to recognize only `on_*` and `send_*`, removing `handle_*` support (Tasks 2–3).
4. **Unify EVENT ingress** so `_event_proxy_worker` enqueues all messages into `_topic_queues` instead of forwarding directly (Task 4).
5. **Add subscriber/producer maps** so the engine knows who consumes and who produces each topic (Task 4).
6. **Add backpressure and queue GC** to `_enqueue_from_xsub` and `_monitor_worker` (Task 5).
7. **Remove ACK worker and request-response APIs** (Tasks 3, 6).
8. **Migrate all modules** from `handle_*` to event-chaining `on_*` + `send_*` (Tasks 7–8).
9. **Update all tests** to match v3 behavior (Tasks 9–10).

---

## Task 1: Foundation Types — InterfacePattern, BackpressureStrategy, Interface

**What:**
- Replace `InterfacePattern` enum (6 values) with 2 values: `ON = "on"` and `SEND = "send"`.
- Add `BackpressureStrategy` enum: `DROP_OLDEST = "drop_oldest"`, `DROP_NEWEST = "drop_newest"`, `BLOCK_PRODUCER = "block_producer"`.
- Add `backpressure: BackpressureStrategy = BackpressureStrategy.DROP_OLDEST` and `max_queue_depth: int = 10000` fields to `Interface` dataclass.
- Update `ModuleInfo` if necessary (no structural change expected).

**Why:** All downstream tasks depend on these type definitions. They must land first.

**Expected result:** `pytest tests/unit/test_types.py -v` passes with updated assertions for the new enum values and `Interface` fields.

**Files touched:** `src/tyche/types.py`

**Estimated LOC:** ~35 source, ~30 test.

**Dependencies:** none.

---

## Task 2: Module Discovery and Dispatch — Simplify to on_/send_

**What:**
- Rewrite `TycheModule._pattern_for_name` to return `InterfacePattern.ON` for `on_*` prefixes, `InterfacePattern.SEND` for `send_*` prefixes, and `None` for everything else.
- Update `_discover_and_register_handlers` so `SEND` patterns are recorded in `_interfaces` but **not** added to `_handlers` (producers have no inbound handler).
- Simplify `_dispatch` to remove the `handle_*` return-value special case. All dispatch is fire-and-forget; handler return values are discarded.
- Remove `_subscribe_to_interfaces` filtering that assumes specific prefixes (keep the generic SUB socket subscription logic).

**Why:** Modules must correctly discover and register under the v3 two-pattern model before any module migration can happen.

**Expected result:** `pytest tests/unit/test_module.py -v` passes. A test module with `on_tick` and `send_bar` methods discovers exactly two interfaces with patterns `ON` and `SEND`.

**Files touched:** `src/tyche/module.py`

**Estimated LOC:** ~50 source, ~40 test.

**Dependencies:** Task 1.

---

## Task 3: Remove Request-Response APIs

**What:**
- Remove `send_event_with_response` and `call_ack` from `TycheModule`.
- Remove `_ack_socket`, `_ack_lock`, and `_ack_port` usage from `TycheModule._start_workers` and `stop`.
- Remove the response-sending branch from `_event_receiver` (the `if result is not None and self._ack_socket is not None` block).
- Clean up imports if `uuid` was only used for correlation IDs.

**Why:** v3 eliminates synchronous request-response. Modules use `send_event` + `on_{event}_result` event chaining instead.

**Expected result:** `grep -r "send_event_with_response\|call_ack" src/tyche/` returns nothing. `pytest tests/unit/test_module.py -v` passes.

**Files touched:** `src/tyche/module.py`

**Estimated LOC:** ~50 source, ~20 test.

**Dependencies:** Task 2.

---

## Task 4: Engine — Unified Ingress and Subscriber/Producer Maps

**What:**
- Add `_topic_subscribers: Dict[str, List[str]]` and `_topic_producers: Dict[str, List[str]]` to `TycheEngine.__init__`.
- Update `register_module` to populate subscriber and producer maps from `ModuleInfo.interfaces`:
  - `ON` interfaces → add to `_topic_subscribers[event_name]`
  - `SEND` interfaces → add to `_topic_producers[event_name]`
  - create `_topic_queues[event_name]` if absent for both
- Update `unregister_module` to remove module_id from subscriber/producer maps.
- Change `_event_proxy_worker` XSUB handling to call `self._enqueue_from_xsub(frames)` instead of `self._xpub_socket.send_multipart(frames)`.
- Update `_event_egress_worker` so it drains **all** topic queues (not just ACK-populated ones) and forwards via XPUB.
- Update admin `STATUS` query to report `_topic_subscribers` and `_topic_producers` counts.

**Why:** This is the core architectural change. All events now flow through `_topic_queues`, enabling unified observability and backpressure.

**Expected result:** `pytest tests/unit/test_engine.py -v` passes. Two ExampleModules exchanging ping-pong events still work, but events now traverse `_topic_queues`.

**Files touched:** `src/tyche/engine.py`

**Estimated LOC:** ~90 source, ~40 test.

**Dependencies:** Task 1. Can run in parallel with Tasks 2–3 once Task 1 is done.

---

## Task 5: Engine — Backpressure and Queue GC

**What:**
- Update `_enqueue_from_xsub` to read `max_queue_depth` and `backpressure` from a per-topic config. For now, use hardcoded defaults (`max_queue_depth=10000`, `backpressure=DROP_OLDEST`) since `Interface` backpressure config is not yet plumbed through registration serialization. A follow-up task can wire per-topic config.
- Implement overflow logic:
  - `DROP_OLDEST`: `while len(q) >= max_depth: q.pop(0)` then `q.append(frames)`
  - `DROP_NEWEST`: if `len(q) >= max_depth`, discard incoming `frames`
  - `BLOCK_PRODUCER`: not implemented in v1 (ZMQ PUB is non-blocking; true blocking requires credit-based flow control). Log warning and treat as DROP_NEWEST.
- Add queue TTL GC in `_monitor_worker`:
  - Track `self._topic_last_access: Dict[str, float]` updated on enqueue/dequeue.
  - If a topic has zero subscribers, zero producers, and `time.time() - last_access > TOPIC_QUEUE_TTL_SECONDS` (default 60), delete the queue.

**Why:** Prevents unbounded memory growth and provides basic backpressure without per-topic config complexity in the first iteration.

**Expected result:** Admin query shows queue depths. A load test with a slow subscriber does not OOM the engine (queue caps at 10000).

**Files touched:** `src/tyche/engine.py`

**Estimated LOC:** ~70 source, ~30 test.

**Dependencies:** Task 4.

---

## Task 6: Engine — Remove ACK Worker

**What:**
- Remove `_ack_worker` method entirely.
- Remove `_ack_correlations`, `_ack_lock`, and `ack_endpoint` from `__init__`.
- Remove `ack_port` from the registration ACK reply payload in `_process_registration`.
- Remove `_message_queues[MessageType.RESPONSE]` from `_message_queues` (no longer needed).
- Clean up `_start_workers` thread list (remove `ack` thread).
- Remove `MessageType.RESPONSE` usage if it becomes orphaned (check codebase).

**Why:** ACK channel was solely for `handle_*` request-response. With `handle_*` removed, it is dead code.

**Expected result:** `pytest tests/unit/test_engine.py -v` passes. No `_ack_worker` thread in `engine._threads`. grep for `_ack_worker` in `src/tyche/` returns nothing.

**Files touched:** `src/tyche/engine.py`, `src/tyche/types.py` (if `MessageType.RESPONSE` is removed)

**Estimated LOC:** ~60 source, ~20 test.

**Dependencies:** Task 4. Can run in parallel with Task 5.

---

## Task 7: ExampleModule — Migrate to v3 Patterns

**What:**
- Rename all event handlers:
  - `on_streaming_data` → `on_data`
  - `on_whispered_message` → `on_message`
  - `on_broadcasted_broadcast` → `on_broadcast`
  - `on_broadcasted_ping` → `on_ping`
- Remove `handle_broadcasted_request`.
- Add `send_ping` and `send_pong` as declarative `SEND` interfaces (empty methods, or simply rely on `send_event` calls inside `_broadcast_ping`/`_broadcast_pong`).
- Update ping-pong to pure event chaining: `on_ping` receives, schedules timer, calls `_broadcast_pong` which calls `send_event("pong", ...)`. No correlation IDs.
- Update docstrings and comments.

**Why:** ExampleModule is the reference implementation. It must demonstrate the v3 model clearly.

**Expected result:** `pytest tests/unit/test_example_module.py -v` passes. `ExampleModule.interfaces` contains only `ON` and `SEND` patterns.

**Files touched:** `src/tyche/example_module.py`

**Estimated LOC:** ~70 source, ~40 test.

**Dependencies:** Tasks 2, 3.

---

## Task 8: Trading Modules — Migrate handle_* to Event Chaining

**What:**
- **RiskModule** (`src/modules/trading/risk/module.py`):
  - Rename `handle_broadcasted_order_submit` → `on_order_submit`.
  - Remove return dict. Keep `send_event(events.ORDER_APPROVED, ...)` and `send_event(events.ORDER_REJECTED, ...)`.
  - Rename `on_broadcasted_position_update` → `on_position_update`.
- **GatewayBase** (`src/modules/trading/gateway/base.py`):
  - Rename `handle_whispered_order_execute` → `on_order_execute`.
  - Remove return dict. On success, call `send_event("order_executed", result.to_dict())`. On failure, call `send_event("order_execution_failed", ...)`. Venue filtering stays (non-matching venues simply return early).
  - Same for `handle_whispered_order_cancel` → `on_order_cancel`.
- **OMSModule** (`src/modules/trading/oms/module.py`):
  - Rename `on_broadcasted_order_approved` → `on_order_approved`.
  - Rename `on_broadcasted_fill` → `on_fill`.
  - Rename `on_broadcasted_order_cancel` → `on_order_cancel`.
  - Update `send_event` topic strings from `"handle_whispered_order_execute"` → `"order_execute"`, `"handle_whispered_order_cancel"` → `"order_cancel"`.

**Why:** The trading pipeline is the primary consumer of `handle_*` patterns. It must work under v3 before the change can be considered complete.

**Expected result:** `pytest tests/unit/test_risk_rules.py tests/unit/test_oms_module.py tests/unit/test_gateway_main.py -v` passes.

**Files touched:** `src/modules/trading/risk/module.py`, `src/modules/trading/gateway/base.py`, `src/modules/trading/oms/module.py`

**Estimated LOC:** ~80 source, ~50 test.

**Dependencies:** Tasks 2, 3.

---

## Task 9: Tests — Unit Tests for Types and Module

**What:**
- Update `tests/unit/test_types.py`: Replace 6 `InterfacePattern` assertions with 2. Add `BackpressureStrategy` assertions. Update `Interface` construction tests.
- Update `tests/unit/test_module.py`: Replace 6-pattern discovery test with 2-pattern (`on_*` / `send_*`). Remove `handle_*` dispatch return-value tests. Add `send_*` discovery test. Verify `SEND` patterns are not in `_handlers`.
- Update `tests/unit/test_engine.py`: Remove ACK-related tests. Add unified-queue tests (verify EVENT enters `_topic_queues`).

**Why:** Core unit tests must match the new behavior before integration tests can be trusted.

**Expected result:** `pytest tests/unit/test_types.py tests/unit/test_module.py tests/unit/test_engine.py -v` passes.

**Files touched:** `tests/unit/test_types.py`, `tests/unit/test_module.py`, `tests/unit/test_engine.py`

**Estimated LOC:** ~120 test.

**Dependencies:** Tasks 1, 2, 3, 4, 6.

---

## Task 10: Tests — Integration and Trading Tests

**What:**
- Update `tests/integration/test_engine_module.py` to use v3 interface names.
- Update `tests/integration/test_message_queue_perf.py` if it asserts direct-proxy behavior.
- Update `tests/unit/test_example_module.py` for renamed handlers.
- Update `tests/unit/test_strategy_context.py` if it references old `InterfacePattern` values.
- Update `tests/unit/test_ctp_gateway*.py`, `tests/unit/test_simulated_gateway.py` if they reference old event names or `handle_*` patterns.
- Run full suite: `pytest tests/ -v`. Fix any remaining failures.

**Why:** Final verification that the entire codebase is consistent and green.

**Expected result:** Full test suite passes with no regressions from the 403-passed baseline.

**Files touched:** Multiple test files under `tests/unit/` and `tests/integration/`.

**Estimated LOC:** ~150 test.

**Dependencies:** Tasks 5, 7, 8, 9.

---

## Dependency Graph

```
Task 1 (types)
    ├── Task 2 (module discovery)
    │       ├── Task 3 (remove req-resp)
    │       │       ├── Task 7 (ExampleModule)
    │       │       ├── Task 8 (trading modules)
    │       │       └── Task 9 (unit tests)
    │       └── Task 9 (unit tests, partial — test_module.py)
    │
    └── Task 4 (engine ingress + maps)
            ├── Task 5 (backpressure + GC)
            ├── Task 6 (remove ACK worker)
            └── Task 9 (unit tests, partial — test_engine.py)
                    └── Task 10 (integration + full suite)
```

**Parallelizable groups:**
- Tasks 2–3 can run in parallel with Task 4 after Task 1 completes.
- Tasks 7–8 can run in parallel after Tasks 2–3 complete.
- Tasks 5–6 can run in parallel after Task 4 completes.

---

## Rollback Plan

If any integration test fails catastrophically and cannot be resolved within the Task 10 budget:

1. Revert Tasks 6, 5, 4 in that order (engine changes are the riskiest).
2. Keep Tasks 1–3 and 7–8 in a feature branch; the module-side v3 changes are compatible with a v2 engine as long as `handle_*` methods are removed (they would simply not be invoked, which is acceptable for a partial migration).
3. Re-evaluate whether unified queue should be feature-flagged rather than always-on.

## Out of Scope

- Per-topic configurable `max_queue_depth` and `backpressure` via registration payload (follow-up plan after v1 is stable).
- `BLOCK_PRODUCER` full implementation (credit-based flow control requires protocol changes).
- Persistent queue backend (`SYNC_FLUSH` durability still writes to the existing async backend; no new persistence layer).
- Performance benchmark regression gates (manual A/B comparison only).
