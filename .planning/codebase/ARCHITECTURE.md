# Architecture

**Analysis Date:** 2026-05-14

## Pattern Overview

**Overall:** Distributed Event-Driven Broker with Multi-Language Module Support

**Key Characteristics:**
- Multi-process architecture: Engine and Modules run as separate OS processes communicating exclusively via ZeroMQ
- Thread-per-concern engine design: 9 daemon threads each managing a specific ZMQ socket or internal concern
- Unified per-topic message queues (v3 design): All events flow through `TycheEngine._topic_queues` before broadcast
- Auto-discovery interface model: Module handlers discovered via method name prefix conventions (`on_*`, `send_*`, `handle_*`, `request_*`)
- Multi-language module support: Python (primary), C++ (cppzmq + msgpack-cxx), Rust (zmq + rmp-serde)
- Paranoid Pirate heartbeat pattern for reliable liveness detection

## Layers

**Core Framework (tyche package):**
- Purpose: ZeroMQ broker, message serialization, module lifecycle, heartbeat protocol
- Location: `src/tyche/`
- Contains: Engine, module base classes, types, message serialization, heartbeat manager
- Depends on: pyzmq, msgpack, Python threading
- Used by: All application modules, C++ modules via pybind11, Rust modules via FFI

**Language Bindings:**
- Purpose: Enable modules written in C++ and Rust to participate in the Tyche ecosystem
- Location: `src/tyche/cpp/`, `src/tyche/rust/`
- Contains: C++ TycheModule class (PIMPL), Rust TycheModuleBase struct
- Depends on: cppzmq + msgpack-cxx (C++), zmq + rmp-serde (Rust)
- Used by: Performance-critical modules (market data, execution)

**Application Modules (modules package):**
- Purpose: Domain-specific trading modules (gateway, OMS, risk, portfolio, strategy)
- Location: `src/modules/`
- Contains: Trading domain modules (currently minimal — framework only)
- Depends on: `tyche.*` core framework
- Used by: End-user trading strategies and system configurations

**Terminal UI (tui):**
- Purpose: Real-time monitoring dashboard and process supervisor
- Location: `tui/`
- Contains: TypeScript/Bun terminal application using OpenTUI and ZeroMQ
- Depends on: zeromq.js, @msgpack/msgpack, @opentui/core
- Used by: Operators for monitoring and controlling engine/modules

**Documentation & Process:**
- Purpose: Design specs, implementation plans, review logs, ADRs
- Location: `docs/design/`, `docs/plan/`, `docs/review/`, `docs/impl/`
- Contains: Versioned design documents, plan documents, implementation logs

## Data Flow

**Module Registration Flow:**

1. Module process starts, creates ZMQ context and sockets
2. Module sends `REGISTER` message via one-shot REQ socket to Engine's ROUTER
3. Engine `_registration_worker` receives frames, enqueues to `MessageType.REGISTER` queue
4. Engine `_registration_egress_worker` dequeues, creates `ModuleInfo`, calls `register_module()`
5. Engine creates per-topic queues for module's interfaces, updates subscriber/producer maps
6. Engine sends `ACK` reply with XPUB/XSUB port assignments and job router port
7. Module connects PUB to engine XSUB, SUB to engine XPUB, DEALER to heartbeat receive
8. Module starts event receiver, heartbeat sender, and job receiver threads

**Event Publishing Flow (v3 Unified Queue):**

1. Module calls `send_event(topic, payload)` — sends `[topic, serialized_msg]` via PUB socket
2. Engine `_event_proxy_worker` receives on XSUB socket
3. `_enqueue_from_xsub()` routes to `TopicQueue` for that topic (creates if absent)
4. `_event_egress_worker` wakes on `_egress_wakeup` queue, drains all topic queues
5. Each frame batch is sent via XPUB socket to all subscribed modules
6. Subscribing modules' `_event_receiver` threads receive and dispatch to handlers

**Job Request/Response Flow:**

1. Requester module calls `request_event(event, payload, timeout)`
2. Module sends REQUEST message via DEALER socket with correlation_id
3. Engine `_job_router_worker` receives on ROUTER socket
4. Engine looks up handlers for topic, selects via round-robin
5. Engine stores `correlation_id -> requester_identity` mapping
6. Engine forwards request to handler module's DEALER identity
7. Handler module's `_job_receiver` receives, dispatches to handler
8. Handler returns result; module sends RESPONSE back via DEALER
9. Engine `_job_router_worker` receives response, looks up requester, forwards back
10. Requester module's `_handle_job_response` sets event, unblocking `request_event()`

**Heartbeat Flow:**

1. Engine `_heartbeat_worker` broadcasts heartbeat messages via PUB socket
2. Module `_send_heartbeats` sends heartbeat via DEALER to engine's heartbeat receive endpoint
3. Engine `_heartbeat_receive_worker` receives on ROUTER, updates `HeartbeatManager`
4. Engine `_monitor_worker` ticks all monitors, unregisters expired modules
5. Expired modules trigger topic queue GC (queues with no subscribers/producers after TTL)

**Admin Query Flow:**

1. External tool (TUI, CLI) sends query string via REQ to Engine's admin ROUTER
2. Engine `_admin_worker` receives, dispatches to `_process_admin_query()`
3. Query types: `STATUS`, `MODULES`, `QUEUES`, `STATS`
4. Response serialized via msgpack and returned

## State Management

**Engine State:**
- `modules: Dict[str, ModuleInfo]` — registered modules (thread-safe via `_lock`)
- `interfaces: Dict[str, List[Tuple[str, Interface]]]` — topic -> [(module_id, interface)]
- `_topic_queues: Dict[str, TopicQueue]` — per-topic message queues (`_topic_queues_lock`)
- `_topic_subscribers: Dict[str, List[str]]` — topic -> module_ids (consumer mapping)
- `_topic_producers: Dict[str, List[str]]` — topic -> module_ids (producer mapping)
- `_job_handlers: Dict[str, List[str]]` — topic -> module_ids with `handle_*` interfaces
- `_pending_jobs: Dict[str, bytes]` — correlation_id -> requester identity
- `heartbeat_manager: HeartbeatManager` — per-peer liveness tracking

**Module State:**
- `_handlers: Dict[str, Tuple[Callable, InterfacePattern]]` — event_type -> (handler, pattern)
- `_pending_requests: Dict[str, Dict]` — correlation_id -> {event, result} for job responses
- `_interfaces: List[Interface]` — auto-discovered from method names

## Key Abstractions

**TycheEngine:**
- Purpose: Central broker — the only process that binds sockets; all modules connect to it
- Location: `src/tyche/engine.py`
- Pattern: Thread-per-concern with shared ZMQ context; ingress/egress separation for registration and events

**TycheModule:**
- Purpose: Base class for all modules — handles registration, event pub/sub, heartbeats, job request/response
- Location: `src/tyche/module.py`
- Pattern: Template method with auto-discovery; subclasses implement `on_*`/`send_*`/`handle_*`/`request_*` methods

**ModuleBase (Protocol):**
- Purpose: Minimal contract — `module_id`, `start()`, `stop()`
- Location: `src/tyche/module_base.py`
- Pattern: Structural subtyping via `@runtime_checkable`; enables duck-typing for module interfaces

**Message / Envelope:**
- Purpose: Application-level message structure with MessagePack serialization
- Location: `src/tyche/message.py`
- Pattern: Dataclass with custom Decimal encoder/decoder for msgpack

**TopicQueue / TrackedQueue:**
- Purpose: Thread-safe queues with capacity, processed count, and dropped count statistics
- Location: `src/tyche/engine.py` (lines 28-95)
- Pattern: Wrapper around `list`/`queue.Queue` with `threading.Lock` for stats

**HeartbeatManager:**
- Purpose: Track liveness of all connected modules using Paranoid Pirate pattern
- Location: `src/tyche/heartbeat.py`
- Pattern: Per-peer `HeartbeatMonitor` objects with centralized tick/expiry

## Entry Points

**Python Engine:**
- Location: `src/tyche/engine.py` — `TycheEngine.run()` / `TycheEngine.start_nonblocking()`
- Triggers: Direct instantiation or `python -m tyche.engine_main`
- Responsibilities: Bind all ZMQ sockets, start 9 worker threads, block until stop

**Python Module:**
- Location: `src/tyche/module.py` — `TycheModule.run()` / `TycheModule.start()`
- Triggers: Subclass instantiation in separate process
- Responsibilities: Register with engine, start worker threads, dispatch events to handlers

**C++ Module:**
- Location: `src/tyche/cpp/module.h` — `tyche::TycheModule::start()` / `run()`
- Triggers: C++ binary linking against tyche cpp headers
- Responsibilities: Same as Python module but in native code

**Rust Module:**
- Location: `src/tyche/rust/src/module.rs` — `TycheModuleBase::start_with_dispatcher()`
- Triggers: Rust crate depending on `tyche` crate
- Responsibilities: Same lifecycle but with closure-based dispatcher

**TUI Dashboard:**
- Location: `tui/src/app.ts` — `runApp(options)`
- Triggers: `cd tui && bun run start`
- Responsibilities: Connect to engine admin/event/heartbeat endpoints, render real-time dashboard

## Error Handling

**Strategy:** Log and continue — no global exception handler; each worker thread has its own try/except

**Patterns:**
- ZMQ `EAGAIN` timeouts are silently retried (polling loops)
- Deserialization failures are logged and the message is dropped
- Handler exceptions are caught in `_dispatch()`, logged, and do not crash the receiver thread
- Job request timeouts raise `TimeoutError` to the caller
- Registration failures return `False`; caller must handle

## Cross-Cutting Concerns

**Logging:** Python `logging` module with module-id prefixed messages; no structured logging

**Validation:** Minimal — registration payload validated during `_create_module_info()`; no schema validation on event payloads

**Authentication:** None — open ZMQ sockets; no auth layer detected

**Serialization:** MessagePack with custom Decimal encoder/decoder; C++ uses msgpack-cxx; Rust uses rmp-serde

**Thread Safety:**
- Engine: `_lock` (modules/interfaces), `_topic_queues_lock` (topic queues), `_registration_lock` (ROUTER socket), `_xpub_lock` (XPUB socket)
- Module: `_handlers_lock` (handler registry), `_pub_lock` (PUB socket), `_job_lock` (pending requests)

---

*Architecture analysis: 2026-05-14*
