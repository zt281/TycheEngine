# Module Interface Refactor - Plan v2

> **Design reference:** `docs/design/tyche_engine_design_v2.md`
> **Predecessor:** `docs/plan/module_interface_refactor_plan_v1.md` (APPROVED, partially implemented)

## Project State at Plan Time

- **Design spec:** v2, no changes pending. Some tasks in this plan may force a design clarification — see Task 0.
- **Predecessor plan:** v1 was REJECTED on first review, then APPROVED on re-review (`docs/review/module_interface_refactor_plan_v2.log`). Plan-doc commit: `1a1dfab`.
- **Implementation state of plan v1 (2026-05-01):**
  - Working tree contains uncommitted modifications to `src/tyche/module.py`, `module_base.py`, `types.py`, `example_module.py`, plus 5 trading modules. `docs/impl/module_interface_refactor_implement_v1.md` exists with **empty Task Log**.
  - Reading the working tree against plan v1 task list:
    - Task 1 (types.py rewrite): structurally complete — new 6 `InterfacePattern` values present.
    - Task 2 (slim ModuleBase): **deviation** — file uses `abc.ABC` even though plan v1 explicitly says `typing.Protocol`. `tests/unit/test_module_base.py` is written to ABC semantics (`pytest.raises(TypeError)`), so test/plan/impl disagree.
    - Task 3 (refactor TycheModule): mostly complete — auto-discovery wired, `_dispatch` returns result for `handle_*`, heartbeat uses `_stop_event.wait`, `event_endpoint` removed, ports renamed. **But** new defects surfaced (see Problem Statement).
    - Tasks 4–7: not verified by this review.
- **Test baseline:** plan v1 impl log records 403 passed, 1 flaky perf test (pre-existing). No regression introduced.
- **Code review (this session):** 17 findings classified as 4 Critical (broken behavior), 2 Plan-v1 deviations, 3 API smell, 4 robustness, 4 minor.
- **Out of scope:** anything plan v1 already specifies and got right; `EventType` enum cleanup (still deferred).

## Problem Statement

Plan v1 fixed the surface-level naming and registration issues but did not catch four deeper problems. Plan v2 closes them.

1. **`handle_*` request-response is broken end-to-end.** `_dispatch` returns the handler's `dict`, but `_event_receiver` (`module.py:303`) discards the return value. The engine has no reverse channel — events flow through XPUB/XSUB which is unidirectional. Design v2 promises "Return value is preserved by the dispatch layer"; the network layer breaks that promise.
2. **`_register_handler` does not subscribe the SUB socket.** Plan v1 Task 6 (DataRecorderModule.subscribe_instrument) explicitly relies on runtime registration delivering events. Currently `_subscribe_to_interfaces` runs once at startup; later registrations never receive a message.
3. **`call_ack` is dead code.** It connects a REQ to `engine_endpoint` and sends `MessageType.COMMAND`, but `_process_registration` only handles `MessageType.REGISTER`. Always RCVTIMEO.
4. **ModuleBase implementation deviates from plan v1.** Uses `ABC`, plan says `Protocol`. Tests assert ABC behavior. Three artifacts disagree.

Secondary issues (lower severity but in this plan's scope):

5. `start()` aliases the blocking `run()`, conflicting with the abstract `start()` contract used in `test_module_base.py::test_concrete_module_lifecycle`.
6. `heartbeat_endpoint` parameter is stored but never read.
7. `_dispatch` swallows handler exceptions to `None`, indistinguishable from a legitimate `None` return.
8. `_handlers` / `_interfaces` are mutated without synchronization. Once dynamic registration (Task 2) is wired, this becomes a data race under live traffic.

## Solution Summary

1. **Decision gate** (Task 0): pick a path for `handle_*` semantics — implement reverse channel, or remove it from design v2.
2. **Reconcile ABC vs Protocol** (Task 1): pick one, align tests + design + impl.
3. **Dynamic register → SUB subscribe** (Task 2): mechanical fix.
4. **Resolve `call_ack`** (Task 3): rewrite or delete based on Task 0.
5. **Implement reverse channel** (Task 4) — only if Task 0 chooses Option A.
6. **API cleanup** (Task 5): standardize start/run; remove dead `heartbeat_endpoint`.
7. **Robustness** (Task 6): lock handler maps; explicit error return from `_dispatch`.

---

## Task 0: Design Decision — `handle_*` Semantics

**What:** Team lead chooses between Option A and Option B and records the decision in `docs/design/tyche_engine_design_v2.md` (or bumps to v3 if changes are non-trivial). No code in this task.

- **Option A — Implement reverse channel:** keep `handle_*` patterns. Engine grows an ACK ROUTER worker bound to `ack_endpoint` (already declared in `engine.py:48` but unused). Modules grow a DEALER socket. `_event_receiver` for `handle_*` topics ships the handler return value back, correlated by `correlation_id`.
- **Option B — Drop `handle_*` from v2:** remove `HANDLE_BROADCASTED`, `HANDLE_WHISPERED`, `HANDLE_STREAMING` from `InterfacePattern`. Update `_pattern_for_name` and dispatch. Trading modules use side-channel events (handler does its work, then publishes a result topic).

**Why:** Tasks 3 and 4 fork on this answer. Implementation cannot start without a chosen path.

**Expected result:** A revised design doc with one option marked as the chosen path and the other recorded as rejected. Plan v2 review note appended.

**Files touched:** `docs/design/tyche_engine_design_v2.md` (or new `_v3.md`).

**Estimated LOC:** ≤50 doc-only.

---

## Task 1: Reconcile ModuleBase — ABC vs Protocol

**What:** Pick one of:
- **1a:** Switch `module_base.py` to `typing.Protocol` (matches plan v1). Update `test_module_base.py` to drop `pytest.raises(TypeError)` and instead assert structural conformance via `isinstance(mod, ModuleBase)` after `runtime_checkable`.
- **1b:** Keep `ABC`. Append a one-line correction to the impl log noting the deviation. Update design v2 wording from "Protocol" to "abstract base class".

**Why:** Three sources of truth currently disagree. Pick one before downstream type annotation work spreads the inconsistency.

**Expected result:** All three artifacts (design, impl, test) agree. `pytest tests/unit/test_module_base.py -v` passes.

**Files touched:** `src/tyche/module_base.py` + `tests/unit/test_module_base.py` (option 1a), or `docs/design/tyche_engine_design_v2.md` + impl log entry (option 1b).

**Estimated LOC:** ≤30 source + ≤30 test (1a) / ≤20 docs (1b).

**Dependencies:** none.

---

## Task 2: Wire Dynamic `_register_handler` to SUB Subscription

**What:** When `_register_handler` is invoked after sockets exist, immediately subscribe the SUB socket to the new topic.

```python
def _register_handler(self, name, handler, pattern=..., durability=...) -> None:
    self._handlers[name] = handler
    self._interfaces.append(Interface(name=name, pattern=pattern, ...))
    if self._sub_socket is not None:
        self._sub_socket.setsockopt(zmq.SUBSCRIBE, name.encode())
```

**Why:** Plan v1 Task 6 (DataRecorderModule.subscribe_instrument) requires runtime registration to deliver events. Without this, the dynamic-registration use case is silently broken.

**Expected result:** New unit test `tests/unit/test_module.py::test_dynamic_register_subscribes_topic` — start a module against a paired XPUB, register a handler post-start, send an event with that topic, assert handler invoked. Existing tests remain green.

**Files touched:** `src/tyche/module.py`, `tests/unit/test_module.py`.

**Estimated LOC:** ≤25 source + ≤80 test.

**Dependencies:** none.

---

## Task 3: Resolve `call_ack` Fate

**What:** Branch on Task 0:
- **If Option A:** rewrite `call_ack` to use the new DEALER socket (Task 4). It must include a `correlation_id`, send via DEALER, await the routed reply.
- **If Option B:** delete `call_ack` and `MessageType.COMMAND`. Grep the repo for callers; update them to use `send_event`.

**Why:** `call_ack` currently always times out. Either fix it or remove the misleading API surface.

**Expected result:** Either:
- Option A: integration test `tests/integration/test_call_ack.py` round-trips a request/response.
- Option B: no symbol named `call_ack` remains. `MessageType.COMMAND` removed from `types.py`.

**Files touched:** `src/tyche/module.py`, possibly `src/tyche/types.py`, callers.

**Estimated LOC:** Option A: ≤80 source + ≤80 test. Option B: ≤30 deletions + ≤20 test cleanup.

**Dependencies:** Task 0 (decision); Task 4 (only if Option A — Task 3 lands after the DEALER infra).

---

## Task 4: Implement `handle_*` Network Response Delivery (skip if Task 0 = Option B)

**What:** Add the reverse channel that makes `handle_*` actually return values to the caller. Splittable into 4a + 4b if it exceeds 300 LOC.

**4a — Engine side:**
- New thread `_ack_worker` binds ROUTER on `self.ack_endpoint`.
- Maintains `Dict[correlation_id, identity]` to route replies.
- Forwards inbound `MessageType.COMMAND` (or new `RESPONSE`) frames to the recorded identity.

**4b — Module side:**
- New DEALER socket `self._ack_socket` connects to `ack_endpoint`.
- After `_dispatch` returns a non-None value for a `handle_*` topic, package the result with the inbound `correlation_id` into a `Message(msg_type=RESPONSE)` and send via DEALER.
- New helper `send_event_with_response(event, payload, timeout_ms)` generates a `correlation_id`, sends via PUB, and awaits the matching reply on a per-call DEALER socket (or a shared one with a future map).

**Why:** Honor design v2's request-response promise. Without this, `handle_*` is a footgun.

**Expected result:** Integration test `tests/integration/test_handle_response.py`:
- Module A defines `handle_broadcasted_query` returning `{"x": 1}`.
- Module B calls `send_event_with_response("handle_broadcasted_query", {"q": "ping"})`.
- Assert returned dict equals `{"x": 1}`.
Trading test `test_oms_routes_order_to_gateway` validates the Gateway path with venue filtering.

**Files touched:** `src/tyche/engine.py`, `src/tyche/module.py`, new test file.

**Estimated LOC:** 4a ≤120 source + ≤80 test; 4b ≤120 source + ≤100 test. **If single task exceeds 300 source LOC, must split.**

**Dependencies:** Task 0 = Option A.

---

## Task 5: API Cleanup — `start` / `run` / `heartbeat_endpoint`

**What:** Two coupled cleanups in one task because both touch `__init__` / lifecycle:

- **5a — Lifecycle:** Standardize on the engine's convention.
  - `start()` non-blocking, returns once threads up. Internally: `self._start_workers()`.
  - `run()` blocks until stop. Internally: `self.start(); self._stop_event.wait()`.
  - Remove `start_nonblocking()`. Update callers in `tests/`.
- **5b — Drop `heartbeat_endpoint`:** Remove the unused `__init__` parameter and `self.heartbeat_endpoint` attribute. Grep for keyword callers.

**Why:** `start()` aliasing the blocking `run()` violates the protocol contract asserted in `test_concrete_module_lifecycle`. Three lifecycle methods is one too many. `heartbeat_endpoint` misleads users into thinking it controls heartbeat behavior.

**Expected result:** `inspect.signature(TycheModule.__init__).parameters` does not contain `heartbeat_endpoint`. `start_nonblocking` removed. Existing tests pass after caller updates. New unit test `test_start_does_not_block` (uses a thread to assert `start()` returns within 100ms).

**Files touched:** `src/tyche/module.py`, `src/tyche/example_module.py`, `tests/unit/test_module.py`, `tests/integration/test_engine_module.py`, `tests/integration/test_multiprocess.py`, `tests/integration/test_message_queue_perf.py`.

**Estimated LOC:** ≤80 source + ≤100 test.

**Dependencies:** none. Independent of Task 0.

---

## Task 6: Robustness — Locking and Explicit Error Returns

**What:** Two coupled fixes:

- **6a — Lock handler maps:** Add `self._handlers_lock = threading.RLock()`. Wrap mutations (`_register_handler`) and reads (`_dispatch`, `_subscribe_to_interfaces`).
- **6b — Explicit `_dispatch` errors:** For `handle_*` topics, on handler exception return `{"error": str(e), "type": type(e).__name__}` instead of `None`. For `on_*` topics, keep returning `None` (no caller to notify).

**Why:** Once Task 2 lands, threads will mutate and read `_handlers` concurrently. Currently no synchronization. CPython's GIL prevents corruption but does not prevent subscribe/dispatch ordering bugs. `_dispatch` swallowing exceptions to `None` makes errors invisible to `handle_*` callers.

**Expected result:** New unit tests:
- `test_concurrent_register_and_dispatch` — spawn N threads, half register handlers, half dispatch; no exceptions, all dispatched events handled.
- `test_dispatch_handle_error_returns_error_dict` — handler raises; dispatch returns `{"error": ..., "type": ...}`.

**Files touched:** `src/tyche/module.py`, `tests/unit/test_module.py`.

**Estimated LOC:** ≤60 source + ≤100 test.

**Dependencies:** Task 2 (locking only matters once dynamic register works).

---

## Verification

After all applicable tasks land:

```bash
pytest tests/ -v
```

Success criteria:
- All unit and integration tests pass (allowing the pre-existing flaky `test_message_queue_perf` failure recorded in plan v1 baseline).
- `grep -r "add_interface" src/` returns no public API call sites.
- `grep -r "start_nonblocking" src/ tests/` returns no hits.
- If Task 0 = Option A: at least one integration test demonstrates a `handle_*` round-trip through the engine, not a direct handler call.
- If Task 0 = Option B: `grep -rE "HANDLE_(BROADCASTED|WHISPERED|STREAMING)" src/` returns no hits; trading modules use publish patterns instead.

## Dependencies

```
Task 0 (decision) ──┬─► Task 3 (call_ack)
                    └─► Task 4 (response delivery, only if Option A)

Task 1 (ABC vs Protocol) ──► (independent, may run first)
Task 2 (sub subscribe) ────► Task 6 (locking matters after dynamic register)
Task 5 (API cleanup) ──────► (independent)
```

Suggested execution order under default (Option A) path:
`Task 1 → Task 0 → Task 5 → Task 2 → Task 4a → Task 4b → Task 3 → Task 6`.

Under Option B:
`Task 1 → Task 0 → Task 5 → Task 2 → Task 3 → Task 6` (Task 4 skipped).

## Notes on Plan v1 Status

Plan v1 implementation is mid-flight in the working tree. Plan v2 does **not** re-do plan v1 work. The expectation is:

1. Plan v1's outstanding tasks (4–7: engine verification, ExampleModule rename, trading modules, public API) get committed first as plan v1 closure.
2. Plan v2's tasks land afterwards on top.

If plan v1's remaining tasks turn out to overlap with plan v2 fixes (e.g., a trading module rename that should also pick up the `handle_*` rework), the impl log notes the merge.
