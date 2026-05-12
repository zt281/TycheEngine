# Unified Message Queue Design Specification v1

## Overview

This specification replaces the v2 interface pattern model with a unified message-queue-based routing layer. All events—regardless of broadcast, P2P, or streaming semantics—flow through the engine's per-topic message queues. Interface patterns are collapsed from six category-specific variants to two fundamental roles: **consumer** (`on_{event}`) and **producer** (`send_{event}`).

The engine becomes the sole authority for topic queue lifecycle and subscription mapping. Modules declare the events they produce and consume; the engine creates queues, maintains subscriber lists, and routes messages accordingly.

## Relation to Prior Designs

- **tyche_engine_design_v1.md** — Superseded. v1's five ad-hoc patterns are replaced by the `on_`/`send_` model.
- **tyche_engine_design_v2.md** — Superseded. v2's six `InterfacePattern` values (`ON_BROADCASTED`, `HANDLE_BROADCASTED`, etc.) and category-specific prefixes are removed. The transport layer (ZeroMQ XPUB/XSUB) is retained but repurposed: it becomes a distribution pipe fed by the unified egress worker rather than a direct proxy.

## Motivation

### Problems with v2

1. **Fragmented routing.** `broadcasted`, `whispered`, and `streaming` prefixes encode routing intent in method names. This scatters routing policy across module code. Changing a broadcast to a P2P message requires renaming methods in multiple modules.
2. **Dual hot paths.** EVENT messages bypass the engine's `_topic_queues` via the XPUB/XSUB proxy, while COMMAND/RESPONSE messages go through `_topic_queues` and `_event_egress_worker`. This split prevents unified backpressure, monitoring, and persistence.
3. **Request-response coupling.** The `handle_*` prefix imposes a synchronous request-response contract (`send_event_with_response` → `ack_socket` → return dict). This couples caller and callee through correlation IDs and timeouts, which is fragile in a distributed system.
4. **Observability gaps.** Because EVENTs never enter `_topic_queues`, the engine cannot report per-topic queue depth, latency, or drop rates for the bulk of traffic.

### Goals

1. **Single routing abstraction.** Every event enters a topic queue. The engine decides how to deliver it (broadcast, P2P, or stream) based on subscriber configuration, not method name prefixes.
2. **Minimal interface surface.** Modules only implement `on_{event}` handlers and call `send_event`. No `handle_*`, no prefix categories, no `send_event_with_response`.
3. **Observable at every hop.** Per-topic queue depth, enqueue/dequeue rates, and subscriber counts are queryable via the admin endpoint.
4. **Backward-compatible transport.** Modules continue to use their existing ZMQ sockets (PUB, SUB, DEALER). The change is engine-internal.

## Architecture

### System Topology

```
                           +------------------+
                           |   TycheEngine    |
                           |                  |
  Module A                 |  +------------+  |                 Module B
  +-----------+            |  | _topic_    |  |            +-----------+
  | on_tick   |<-----------|--| queues     |  |----------->| on_tick   |
  | send_bar  |----------->|  | (per-topic)|  |            | on_bar    |
  +-----------+            |  +------------+  |            +-----------+
        |                  |        |         |                  ^
        | PUB/XSUB         |        | egress  |                  | XPUB/SUB
        v                  |        v worker  |                  |
      [frames] ----------> |  [queue] -> [XPUB] -------------> [frames]
                           +------------------+
```

All events from module PUB sockets enter the engine's XSUB socket and are enqueued into `_topic_queues[topic]`. The `_event_egress_worker` dequeues and broadcasts via XPUB. Subscribing modules receive through their SUB sockets unchanged.

### Interface Patterns (v3)

Auto-discovery scans for two prefixes only:

| Role | Method Prefix | Pattern Enum | Behavior |
|------|--------------|--------------|----------|
| **Consumer** | `on_{event}` | `InterfacePattern.ON` | Receive events on this topic. Engine adds module to topic subscriber list. |
| **Producer** | `send_{event}` | `InterfacePattern.SEND` | Declare intent to publish on this topic. Engine creates queue if absent. No method body required (engine uses `send_event` API). |

**Key differences from v2:**
- No `broadcasted` / `whispered` / `streaming` suffix. Topic name alone defines the event type.
- No `handle_*` prefix. Request-response is replaced by event chaining (see below).
- `send_{event}` methods are optional declarations. If present, they signal the engine to ensure the topic queue exists at registration time. The actual sending is done through `TycheModule.send_event`.

### Topic Queue Lifecycle

The engine maintains three registry structures:

```python
# Topic queue: topic -> List[frames]
self._topic_queues: Dict[str, List[List[bytes]]]

# Subscriber map: topic -> [module_id, ...]
self._topic_subscribers: Dict[str, List[str]]

# Producer map: topic -> [module_id, ...] (for rate-limiting and auth)
self._topic_producers: Dict[str, List[str]]
```

**On module registration:**
1. For each `ON` interface (`on_tick`), add `module_id` to `_topic_subscribers[tick]`. Create queue if absent.
2. For each `SEND` interface (`send_bar`), add `module_id` to `_topic_producers[bar]`. Create queue if absent.
3. Subscribe the module's SUB socket to all `ON` topics via XPUB subscription frames (unchanged from v2).

**On module unregistration:**
1. Remove `module_id` from all subscriber and producer lists.
2. If a topic has zero subscribers and zero producers, the queue may be retained (for late subscribers) or garbage-collected (configurable).

### Unified Event Routing

**Ingress path (`_event_proxy_worker`):**

```python
frames = self._xsub_socket.recv_multipart(zmq.NOBLOCK)
self._enqueue_from_xsub(frames)  # was: direct forward
```

All events—whether `EVENT`, `COMMAND`, or `HEARTBEAT`—that arrive on XSUB are enqueued. The `_enqueue_from_xsub` method already exists in the codebase; this change simply activates it.

**Egress path (`_event_egress_worker`):**

```python
# Drain each topic queue
for topic, q in self._topic_queues.items():
    while q:
        frames = q.pop(0)
        # Broadcast to all subscribers via XPUB
        self._xpub_socket.send_multipart(frames)
        self._event_count += 1
```

XPUB/XSUB remains the distribution mechanism. The engine does not open per-module sockets. This preserves ZeroMQ's efficient fan-out.

### Replacing Request-Response

The v2 `handle_*` + `send_event_with_response` pattern is removed. Modules use **event chaining** instead:

**v2 (removed):**
```python
# Risk module
class RiskModule(TycheModule):
    def handle_broadcasted_order_submit(self, payload):
        # validate...
        return {"status": "approved", "order_id": oid}

# Strategy module
result = self.send_event_with_response(
    "handle_broadcasted_order_submit",
    {"order": order},
    timeout_ms=5000,
)
```

**v3:**
```python
# Risk module
class RiskModule(TycheModule):
    def on_order_submit(self, payload):
        # validate...
        self.send_event("order_result", {
            "order_id": payload["order_id"],
            "status": "approved",
        })

# Strategy module
class StrategyModule(TycheModule):
    def on_order_result(self, payload):
        if payload["status"] == "approved":
            self.send_event("order_execute", {"order_id": payload["order_id"]})

    def send_order_submit(self, payload):
        self.send_event("order_submit", payload)
```

**Benefits:**
- No correlation ID state in the engine.
- No blocking `send_event_with_response` call in the caller.
- Timeout and retry logic are explicit in module code (or in a future library helper), not hidden in the transport layer.
- Risk and Strategy modules are decoupled: Strategy does not need to know that Risk processed the event.

## Components

### TycheEngine

**New responsibilities:**
- Maintain `_topic_subscribers` and `_topic_producers` maps.
- Enqueue all XSUB traffic into `_topic_queues` (no more hot-path bypass).
- Admin endpoint exposes per-topic metrics: queue depth, subscriber count, producer count, enqueue/dequeue rate.

**Retained responsibilities:**
- Module registration/unregistration and heartbeat monitoring.
- XPUB/XSUB binding (now fed by egress worker, not direct proxy).

**Removed responsibilities:**
- ACK correlation tracking (`_ack_correlations`, `_ack_worker`). The DEALER-ROUTER ack socket may be retained for backward compatibility during migration, but new code does not use it.

### TycheModule

**New behavior:**
- `_pattern_for_name` recognizes only `on_*` and `send_*`.
- `send_{event}` methods are discovered and recorded as `SEND` interfaces. They are **not invoked** by the engine; they serve as declarative metadata.
- `_dispatch` no longer distinguishes `handle_*` return values. All handlers are fire-and-forget.

**Removed:**
- `send_event_with_response`
- `call_ack`
- `InterfacePattern` references to broadcasted/whispered/streaming variants

### ModuleBase (Protocol)

Unchanged.

## Event Delivery Guarantees

| Scenario | Guarantee | Mechanism |
|----------|-----------|-----------|
| Module alive, queue non-empty | At-least-once, FIFO | `_topic_queues` is a list; egress worker drains in order. |
| Module slow / backpressure | Queue bounded, drop or block | Configurable `max_queue_depth` per topic. Default: unbounded (current behavior). |
| Module crashes mid-processing | Event may be redelivered | No ACK from module. Future enhancement: consumer-side offset tracking. |
| Engine crashes | In-memory queues lost | Future enhancement: `SYNC_FLUSH` durability writes queue to persistent backend before acking ingress. |

## Performance

### Baseline Impact

Activating `_enqueue_from_xsub` for all events introduces one Python heap allocation per message (`list.append(frames)`) and one thread wake-up (`_egress_wakeup.put`). In tick-heavy workloads, this adds measurable latency.

### Mitigations

1. **Batch ingress.** `_event_proxy_worker` accumulates up to `INGRESS_BATCH_SIZE` frames (default 64) before enqueuing as a single batch. This amortizes lock and wake-up overhead.
2. **Lock-free fast path.** Replace `list` + `threading.Lock` with `collections.deque` for `_topic_queues`. Deque append/pop are thread-safe and avoid the GIL contention of list resize.
3. **Selective persistence.** Only topics with `DurabilityLevel.SYNC_FLUSH` are written to disk. Others remain in-memory only, preserving throughput.
4. **Future: per-topic worker pool.** If egress worker becomes a bottleneck, shard topics across a pool of worker threads. This is a localized change to `_event_egress_worker` and does not affect module code.

## Migration Path

### Phase 1: Engine (non-breaking)
1. Implement `_topic_subscribers` / `_topic_producers`.
2. Activate `_enqueue_from_xsub` behind a feature flag `UNIFIED_QUEUE=1`.
3. Run A/B benchmarks. Verify throughput regression < 20% at p99.

### Phase 2: Module API (breaking)
1. Reduce `InterfacePattern` to `ON` and `SEND`.
2. Update `_pattern_for_name` and `_dispatch`.
3. Mark `send_event_with_response` / `call_ack` as deprecated with a `DeprecationWarning`.
4. Update `ExampleModule` and all trading modules to v3 patterns.

### Phase 3: Cleanup
1. Remove `ACK` worker, `_ack_correlations`, and the DEALER-ROUTER ack socket.
2. Remove deprecated methods.
3. Update all tests and documentation.

## Decisions

### [DEC-1] Queue garbage collection policy — **RESOLVED**
**Chosen:** Option B — Grace period with TTL.
**Rationale:** Retain queues for `TOPIC_QUEUE_TTL_SECONDS=60` after the last subscriber or producer leaves. This prevents race conditions where a module re-registers and finds an empty queue. A background sweeper thread in `_monitor_worker` garbage-collects expired queues.

### [DEC-2] send_{event} declaration semantics — **RESOLVED**
**Chosen:** Option B — Optional.
**Rationale:** `send_{event}` methods are documentary. The engine creates queues on first ingress. Modules are not required to declare every topic they publish. This avoids boilerplate while still allowing explicit registration for pre-warming or documentation purposes.

### [DEC-3] Backpressure strategy — **RESOLVED**
**Chosen:** Configurable per topic at registration time; default is drop-oldest.
**Rationale:** `Interface` gains a new optional field `backpressure: BackpressureStrategy`. The enum has `DROP_OLDEST` (default), `DROP_NEWEST`, and `BLOCK_PRODUCER`. Market data topics naturally use `DROP_OLDEST` (stale ticks are worthless). Control-plane topics may opt for `DROP_NEWEST` or `BLOCK_PRODUCER`. The engine reads this field during `register_module` and applies the strategy in `_enqueue_from_xsub` when `max_queue_depth` is exceeded.

## References

- [tyche_engine_design_v2.md](tyche_engine_design_v2.md) — Prior design, superseded by this spec.
- [ZeroMQ Guide: Pub-Sub](https://zguide.zeromq.org/docs/chapter2/#Pub-Sub-Messaging)
- [ZeroMQ Guide: Reliability Patterns](https://zguide.zeromq.org/docs/chapter4/)
