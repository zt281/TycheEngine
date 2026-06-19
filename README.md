<p align="center">
  <img src="resources/logo/tycheengine_logo_v5_4k_white.jpg" alt="Tyche Engine Logo" width="400">
</p>

<p align="center">
  <a href="https://github.com/zt281/TycheEngine/actions/workflows/ci.yml">
    <img src="https://github.com/zt281/TycheEngine/workflows/CI/badge.svg" alt="CI Status">
  </a>
  <a href="https://codecov.io/gh/zt281/TycheEngine">
    <img src="https://codecov.io/gh/zt281/TycheEngine/branch/main/graph/badge.svg" alt="Coverage">
  </a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue" alt="Python 3.9+">
  <a href="https://github.com/zt281/TycheEngine/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/zt281/TycheEngine" alt="License">
  </a>
</p>

# Tyche Engine

Tyche Engine is a high-performance distributed event-driven framework for quantitative trading, built on ZeroMQ with a hybrid Python/C++ architecture. It serves as a central processing system for orchestrating multi-process applications, with a focus on low-latency market data processing and derivatives trading workflows.

The system consists of three core layers:
- **Event Management** — ZeroMQ-based message broker with topic routing, unified per-topic queues, and async persistence
- **Module Management** — Pluggable module lifecycle, heartbeat-based liveness, and v2 auto-discovery interface model
- **C++ Engine Core** — High-performance C++ components for hot-path message serialization, shared-memory IPC, and lock-free data structures

## Architecture Overview

Tyche Engine is designed as a **multi-process distributed system** with a hybrid Python orchestration layer and C++ performance layer. The Engine and each Module run as separate operating system processes, communicating via ZeroMQ (with shared-memory IPC for ultra-low-latency paths). This provides true process isolation, CPU scaling across cores, and the ability to distribute across machines.

```
Process A                    Process B                    Process C
+------------------+         +------------------+         +------------------+
|   TycheEngine    |<──ZMQ──>|  CtpGatewayCpp   |<──ZMQ──>|  GreeksEngine    |
|  (Python/C++)    |         |    (C++)        |         |  (Python)       |
+------------------+         +------------------+         +------------------+
       ^                                                        ^
       |                                                        |
       +------------------ Shared Memory (optional) ------------+
```

### Language Stack

| Component | Language | Purpose |
|-----------|----------|---------|
| **Engine Core** | Python 3.9+ | Module orchestration, heartbeat, admin API |
| **C++ Engine** | C++17 | Hot-path message serialization, flat buffers, shared memory |
| **CTP Gateway** | C++17 | Exchange connectivity with sub-100μs tick-to-engine latency |
| **Greeks Engine** | Python | Real-time option Greeks computation (Black-Scholes) |
| **Static Data** | Python | Exchange metadata caching and query service |
| **TycheApp** | TypeScript/Vue | Electron desktop GUI for monitoring and control |
| **TycheTUI** | Python/Textual | Terminal dashboard for process supervision |

Tyche Engine uses ZeroMQ as its messaging backbone. The engine runs **8 daemon threads** managing a unified topic-queue system:

| Thread | Socket | Purpose |
|--------|--------|---------|
| Registration | ROUTER | Receive module registration requests |
| Event Proxy | XPUB/XSUB | Route events via per-topic unified queues |
| Event Egress | (internal) | Drain topic queues and broadcast via XPUB |
| Heartbeat Send | PUB | Broadcast engine heartbeats to all modules |
| Heartbeat Recv | ROUTER | Receive module heartbeats |
| Monitor | (internal) | Check liveness, unregister expired modules |
| Admin | ROUTER | Respond to STATUS/MODULES/QUEUES/STATS queries |

### C++ Engine Core

The C++ layer (`src/tyche/cpp/`) provides high-performance primitives for the hot path:

| Component | File | Purpose |
|-----------|------|---------|
| **FlatMessage** | `flat_message.h` | Zero-allocation fixed-layout message struct |
| **FlatSerializer** | `flat_serializer.h` | Fast msgpack-like serialization without `std::any` |
| **RingBuffer** | `engine/ring_buffer.h` | Lock-free SPSC queue for inter-thread communication |
| **ShardedTopicMap** | `engine/sharded_topic_map.h` | Lock-free topic-to-handler routing |
| **SharedMemoryBridge** | `engine/shared_memory_bridge.h` | Zero-copy IPC between C++ modules |
| **ObjectPool** | `engine/object_pool.h` | Pre-allocated object cache to eliminate heap allocation |
| **RCUSnapshot** | `engine/rcu_snapshot.h` | Read-copy-update for lock-free config updates |
| **FastClock** | `engine/fast_clock.h` | High-resolution timestamping (`QueryPerformanceCounter` on Windows) |
| **AdaptiveSpin** | `engine/adaptive_spin.h` | Exponential backoff spinlock for sub-μs synchronization |
| **TopicQueue** | `engine/topic_queue.h` | Per-topic queue with configurable backpressure policies |

Module socket architecture:

| Socket | Pattern | Purpose |
|--------|---------|---------|
| REQ | Request-Reply | One-shot registration handshake |
| PUB | Pub-Sub | Publish events to engine's XSUB |
| SUB | Pub-Sub | Subscribe to events from engine's XPUB |
| DEALER | DEALER-ROUTER | Send heartbeats to engine |

### Multi-Instance Engine Coordination

When running multiple Tyche Engine instances for high availability:
- **Binary Star Pattern** for primary-backup failover
- Shared configuration via distributed consensus (Raft/Paxos) or shared storage
- Message queue state replication between instances
- Automatic failover with client retry via Lazy Pirate pattern

### C++ Build System

The C++ components use CMake with automatic Visual Studio generator detection:

```bash
# Windows (auto-detects VS 2022/2026)
mkdir build && cd build
cmake .. -A x64
cmake --build . --config Release

# With tests
cmake .. -A x64 -DBUILD_TESTS=ON
cmake --build . --config Release
ctest -C Release --output-on-failure
```

## Modules and Events

Modules are the smallest unit for integrating with Tyche Engine. They can be:

- **Heterogeneous**: Asynchronous independent processes that automatically register their event handling interfaces with Tyche Engine via the v3 unified queue interface discovery protocol.
- **Homogeneous**: Multiple instances started with nearly identical configurations (except for CPU core binding) as multi-node modules, exposing the same interfaces to Tyche Engine for load balancing.

Tyche Engine itself is also a module and can start multiple instances for load balancing.

### Standard Module Requirements

A standard module must have the following:

- **Module Type**: The category or class of the module
- **Module Name (UUID)**: Assigned by Tyche Engine, guaranteed to be unique (format: `{deity_name}{6-char hex}`, e.g. `athena3f2a1b`)
- **Module Settings**: Including CPU core binding, heartbeat interval, timeout thresholds, and restart limits
- **Interface Contract**: Methods following the v3 naming conventions below

#### v2 Unified Queue Interface Model

Modules declare handlers using naming conventions discovered automatically at registration. No manual registration is required.

| Category | Fire-and-forget | Request-response | ZeroMQ Pattern | Behavior |
|----------|----------------|------------------|----------------|----------|
| **Broadcast** | `on_broadcasted_{event}` | `handle_broadcasted_{event}` | PUB-SUB / XPUB | All subscribers receive |
| **P2P (Whisper)** | `on_whispered_{event}` | `handle_whispered_{event}` | DEALER-ROUTER | Direct module-to-module |
| **Streaming** | `on_streaming_{event}` | `handle_streaming_{event}` | PUSH-PULL | Continuous data stream |

**Prefix semantics:**
- `on_*` — Fire-and-forget. Handler returns `None`. No ACK expected.
- `handle_*` — Request-response. Handler must return a `dict` response. Return value is preserved by the dispatch layer.

**Suffix semantics:**
- `_broadcasted` — Event is broadcast to all subscribers via the Engine's XPUB/XSUB proxy.
- `_whispered` — Event is sent directly to a specific module via P2P routing.
- `_streaming` — Continuous stream of messages (e.g., market data, logs).

> **Note:** The v1 `whisper_{target}_{event}` pattern embedded the target module ID in the method name. In v2, the target is specified in the message payload (`recipient` field), not in the method name.

Routing semantics (broadcast, stream, or targeted) are determined by subscriber configuration, not method name prefixes. The v2 model uses unified per-topic queues with configurable backpressure (`DROP_OLDEST`, `DROP_NEWEST`, `BLOCK_PRODUCER`).

**Handler registration details:**
- Methods defined on `TycheModule` itself are skipped
- Abstract methods are skipped (subclasses implement these as callbacks)
- For `on_*` handlers, both the full name and bare topic name are registered (e.g., `on_streaming_market_data` subscribes to both `on_streaming_market_data` and `streaming_market_data`)

### Events

Events are the smallest unit of communication between modules registered in Tyche Engine.

Each event consists of:
- **Event name**: Topic identifier for routing (string), e.g. `quote.BTCUSDT.simulated.crypto`, `order.submit`
- **Event ID**: Unique UUID for idempotency tracking
- **Timestamp**: Unix timestamp with microsecond precision
- **Source module**: Sender's assigned UUID
- **Data**: Serialized payload (MessagePack with custom Decimal encoder)
- **Processing hints**: Optional QoS, priority, TTL

### Event Delivery Guarantees

| Delivery Mode | Guarantee | Ordering | Failure Mode |
|---------------|-----------|----------|--------------|
| Pub-Sub (topic broadcast) | At-least-once | FIFO per producer | Retry with exponential backoff |
| Best-effort broadcast | Best-effort (no guarantee) | None | Drop if subscriber slow |

## Trading Domain Modules

Built on top of the core framework, Tyche Engine provides a complete quantitative trading domain for China futures and options markets:

| Module | Purpose | Language | Location |
|--------|---------|----------|----------|
| **CTP Gateway (C++)** | CTP/TTS exchange connectivity with sub-100μs tick latency | C++17 | `src/modules/ctp_gateway_cpp/` |
| **Static Data** | Exchange metadata caching (OpenCTP DataCenter) | Python | `src/modules/static_data/` |
| **Greeks Engine** | Real-time option Greeks (IV, delta, gamma, vega, theta, rho) | Python | `src/modules/greeks_engine/` |
| **OMS** | Order lifecycle management and routing | Python | `src/modules/trading/oms/` (planned) |
| **Risk** | Pre-trade risk validation rules engine | Python | `src/modules/trading/risk/` (planned) |
| **Portfolio** | Position tracking and P&L calculation | Python | `src/modules/trading/portfolio/` (planned) |
| **Strategy** | Strategy framework with context and callbacks | Python | `src/modules/trading/strategy/` (planned) |
| **Persistence** | Pluggable event storage (ClickHouse, JSONL) | Python | `src/modules/trading/persistence/` (planned) |
| **Clock** | Live and simulated time synchronization | Python | `src/modules/trading/clock/` (planned) |

### CTP Gateway (C++)

The C++ CTP gateway is the primary exchange connectivity module, replacing the earlier Python implementation. Key features:

- **RAII resource management** — CTP API objects and DLL handles managed via custom deleters
- **QuoteTick POD** — Zero-allocation fixed struct for internal tick representation
- **Mixed routing** — Futures broadcast via `send_event`, options dispatched via async job
- **Quote validation** — Price jump detection, stale data detection (>30s), timestamp validation
- **Auto-reconnect** — Automatic re-subscription after CTP SDK internal reconnect
- **Performance targets** — <100μs tick-to-engine latency (tcp loopback), <5μs with shared memory

### Greeks Engine

Computes real-time implied volatility and Greeks for China futures options using a pure-Python Black-Scholes implementation:

- **Standard normal CDF:** Abramowitz & Stegun formula 26.2.17 (Hastings rational approximation), absolute error < 7.5e-8
- **Greeks scaling:** Vega per 1% vol, Theta per day, Rho per 1% rate
- **IV solver:** Newton-Raphson with tolerance 1e-8, max 100 iterations
- **No NumPy/Numba dependency** — pure Python for portability
- **Round-robin job dispatch** — `handle_compute_greeks` distributed across all registered instances

### Static Data

Fetches and caches exchange reference data from the OpenCTP DataCenter REST API:

- **Dual cache** — In-memory + disk (`data/static/*.json`)
- **Background refresh** — Configurable interval (default 6 hours)
- **Job query API** — `handle_query_markets`, `handle_query_products`, `handle_query_instruments`, etc.

### Data Flow — Market Data to Greeks

```
CTP Gateway (C++)
    -> OnRtnDepthMarketData callback
    -> QuoteTick POD (zero allocation)
    -> Mixed routing:
       - Futures: send_event("quote", tick) -> broadcast
       - Options: async send_event("compute_greeks", tick) -> job dispatch
    -> TycheEngine XSUB socket -> TopicQueue -> XPUB socket
    -> GreeksEngine (on_streaming_quote for futures, handle_compute_greeks for options)
       -> Caches underlying prices
       -> Computes IV + Greeks via Black-Scholes
       -> send_event("greeks_update", result)
    -> TycheApp / TycheTUI (subscribes to greeks_update)
```

### Order Submission Flow (Planned)

```
StrategyModule
    -> submit_order() via StrategyContext
    -> send_event("order.submit", order_dict)
    -> TycheEngine XSUB socket -> TopicQueue -> XPUB socket
    -> RiskModule (handle_broadcasted_order_submit)
       -> Evaluates risk rules via RiskRuleEngine
       -> If approved: send_event("order.approved", order_dict)
       -> If rejected: send_event("order.rejected", {...})
    -> OMSModule (handle_broadcasted_order_approved)
       -> Stores order in OrderStore, routes to Gateway
    -> GatewayModule (handle_broadcasted_order_execute)
       -> Calls venue API, publishes fills and order updates
```

## Message Management

Tyche Engine implements **pluggable async persistence** to support production trading, backtesting, and research workflows without blocking the hot path.

### Persistence Backends

| Backend | Use Case | Features |
|---------|----------|----------|
| **ClickHouse** | Production | High-throughput columnar storage, SQL queries, schema versioning |
| **JSON Lines** | Development / Testing | Simple file-based storage, human-readable, date-partitioned |

### Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         HOT PATH (Sub-millisecond)                   │
│  Module ──▶ Event Router ──▶ Handler ──▶ Continue processing         │
│                                          (no blocking)               │
└─────────────────────────────────────────┬────────────────────────────┘
                                          │
                                          ▼ (async, batched)
┌──────────────────────────────────────────────────────────────────────┐
│                     PERSISTENCE SERVICE (Background)                 │
│  ┌─────────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │
│  │ Batch Processor │─▶│ WAL Writer   │  │ Recovery & Replay Store  │ │
│  │ (1s / 5000 evt) │  │ (crash-safe) │  │ (JSONL / ClickHouse)     │ │
│  └─────────────────┘  └──────────────┘  └──────────────────────────┘ │
│           │                    │                    │                │
│           ▼                    ▼                    ▼                │
│  ┌─────────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │
│  │ Research Store  │  │ Cloud Export │  │ Backtesting Feed         │ │
│  │ (Parquet/HDF5)  │  │ (S3, etc)    │  │ (deterministic replay)   │ │
│  └─────────────────┘  └──────────────┘  └──────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

### Durability Levels

Events can specify their durability requirement at the time of publication:

| Level | Behavior | Use Case | Latency Impact |
|-------|----------|----------|----------------|
| `BEST_EFFORT` | No persistence, fire-and-forget | High-frequency telemetry | Zero |
| `ASYNC_FLUSH` | Write to ring buffer, ack immediately (default) | Production trading | <1μs |
| `SYNC_FLUSH` | Wait for disk acknowledgment | Critical settlement events | 1-10ms |

### Async Persistence Mechanism

1. **Batching**: Events are batched before writing to the backend
   - Batch size: 5000 events OR 1s timeout (whichever comes first)
   - Amortizes I/O cost across many events

2. **Pluggable Backends**: `PersistenceBackend` abstract base with `InsertResult`/`QueryResult`
   - `ClickHouseBackend`: HTTP client with parameterized queries, `DateTime64(3)` support, schema versioning via `schema_meta` table
   - `JsonlBackend`: Date-partitioned JSON Lines files (`{data_dir}/{date}/{instrument}_{event_type}.jsonl`)

3. **Backpressure Handling**: If persistence falls behind:
   - **Drop oldest** (research mode): Acceptable loss for analysis
   - **Block and alert** (production mode): Backpressure propagates to producers
   - **Expand buffer** (elastic): Temporarily allocate more memory

### Operating Modes

#### Live Trading Mode
Standard operation with async persistence to ClickHouse or WAL for crash recovery.

#### Backtesting Mode
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Replay Store   │────▶│  Backtest       │────▶│  Tyche Engine   │
│  (historical    │     │  Controller     │     │  (same code     │
│   events)       │     │  (simulated     │     │  path as live)  │
└─────────────────┘     │   time)         │     └─────────────────┘
                        └─────────────────┘              │
                                                         ▼
                                                 ┌─────────────────┐
                                                 │  Results Store  │
                                                 │  (PnL, fills)   │
                                                 └─────────────────┘
```
- Events replayed at simulated time (deterministic) via `ReplayModule` + `SimulatedClock`
- Same engine code path as live trading
- Outputs captured for strategy evaluation

#### Research Mode
All events captured with rich metadata:
- Event timestamps (enqueue, dequeue, processing complete)
- Source module, event type, latency histograms
- Export formats: CSV (small datasets), HDF5 (medium), Parquet (large/compressed)

### Recovery

| Scenario | Recovery Mechanism |
|----------|-------------------|
| Engine crash | Replay WAL from last checkpoint |
| Module crash | Redeliver un-ACKed messages to available workers |
| Persistence lag | Resume from last committed sequence number |
| Disk full | Alert operators, pause new accepts, allow reads |

### Performance Characteristics

| Metric | Target | Notes |
|--------|--------|-------|
| Hot path latency (C++ SHM) | <5μs | Shared memory zero-copy path |
| Hot path latency (C++ tcp) | <100μs | C++ gateway to engine via tcp loopback |
| Hot path latency (Python) | <10μs | Python + ZeroMQ inproc (engine internal) |
| Persistence latency | 1s (batched) | Amortized via batching |
| Recovery time | <1s | From WAL checkpoint |
| Backtest throughput | >100K events/sec | Limited by CPU, not I/O |
| C++ tick throughput | >50,000 ticks/s | Sustained via async option dispatch |

## Module Management

Tyche Engine serves as the unified entry point for the entire system, managing all modules including itself.

### Registration Protocol

```
Module (REQ)                    Tyche Engine (ROUTER)
    |                                  |
    |--- REGISTER + interface list --->|
    |                                  | (validate, generate UUID)
    |<------ ACK + {uuid, config} -----|
    |                                  |
    |--- SUBSCRIBE (to Engine PUB) --->| (add to heartbeat monitoring)
    |<------ READY confirmation -------|
```

**Module Naming**: `{deity_name}{6-char MD5}` (e.g., `zeus3f7a9c`). Names are sourced from historical deities and guaranteed unique within the cluster.

### Module Lifecycle States

```
REGISTERING ──▶ ACTIVE ◀────────────────────────┐
                   │                            │
                   ▼                            │
              SUSPECT (missed heartbeat)        │
                   │                            │
         timeout   ▼              success       │
    ┌───────── RESTARTING ──────────────────────┤
    │              │                            │
    │      max    ▼                             │
    └────▶ FAILED (terminal)                    │
```

| State | Description | Transition |
|-------|-------------|------------|
| `REGISTERING` | Initial handshake in progress | → `ACTIVE` on ACK |
| `ACTIVE` | Normal operation, heartbeats OK | → `SUSPECT` on missed heartbeat |
| `SUSPECT` | Heartbeat timeout, grace period | → `RESTARTING` or `ACTIVE` |
| `RESTARTING` | Attempting process restart | → `ACTIVE` or `FAILED` |
| `FAILED` | Terminal state, max restarts exceeded | Manual intervention required |

### Heartbeat Protocol (Paranoid Pirate Pattern)

- **Frequency**: Configurable (default: 1s)
- **Timeout**: 3 × heartbeat interval
- **Max missed**: 3 heartbeats before marking SUSPECT
- **Heartbeat content**: Module UUID, timestamp, current load (0.0-1.0)

```python
# Worker heartbeat example
heartbeat_interval = 1.0
heartbeat_at = time.time() + heartbeat_interval

while True:
    if poll.poll(timeout):
        msg = socket.recv_multipart()
        process_work(msg)
        heartbeat_at = time.time() + heartbeat_interval  # Reset after work

    if time.time() >= heartbeat_at:
        socket.send(HEARTBEAT)
        heartbeat_at = time.time() + heartbeat_interval
```

### Load Balancing (LRU Queue Pattern)

For homogeneous modules, Tyche Engine maintains a queue of ready workers:

1. Workers send `READY` after registration and after completing each task
2. Engine assigns work to the longest-waiting ready worker
3. If no workers ready, queue events with TTL
4. Dead letter queue for expired events

```
┌──────────┐     ┌──── ────────┐     ┌──────────┐
│  Event   │───▶│  LRU Queue  │────▶│ Worker 1 │
│  Source  │     │  (Engine)   │◀────│ (READY)  │
└──────────┘     └─────────────┘     ├──────────┤
                                     │ Worker 2 │
                                     │ Worker 3 │
                                     └──────────┘
```

### Failure Handling Matrix

| Failure Mode | Detection | Response | Recovery |
|--------------|-----------|----------|----------|
| Module crash | Missed heartbeat | Mark FAILED, redistribute work | Manual restart |
| Slow module | Load report + timeout | Reduce work allocation | Auto-restart if persistent |
| Network partition | Heartbeat timeout | Buffer events, retry connection | Reconnect on partition heal |
| Engine crash | Multi-instance failover | Promote backup | Binary Star takeover |
| Disk full | Write failure | Pause accepts, alert | Operator intervention |

## Design Considerations & Trade-offs

### Why ZeroMQ?

ZeroMQ provides the right balance of performance and reliability patterns for Tyche Engine:
- **Speed**: Sub-millisecond latencies possible with inproc/tcp transports
- **Patterns**: Built-in support for pub-sub, pipeline, request-reply
- **Reliability**: Established patterns (Lazy Pirate, Paranoid Pirate, Majordomo, Titanic)
- **Transport independence**: Same code works in-process, inter-process, or distributed

### Architectural Decisions

| Decision | Alternative | Rationale |
|----------|-------------|-----------|
| v2 Unified Queue (on_*/handle_*) | ack_/whisper_/on_common_ prefixes | Simpler interface model; routing by subscriber config, not method name |
| PUB-SUB for broadcasts | Message queue | True broadcast needed for consensus events |
| PUSH-PULL for load balancing | Round-robin REQ-REP | Better back-pressure, natural load distribution |
| Async persistence (ClickHouse/JSONL) | Synchronous disk write | Keeps hot path fast; supports backtesting/research |
| Pluggable backend abstraction | Single backend | Supports both production (ClickHouse) and dev/test (JSONL) |
| Binary Star for HA | Active-Active | Simpler consistency, prevents split-brain |
| Deity-based naming | UUID-only | Human-readable + unique |

### Known Limitations

1. **No total ordering across producers**: Events from different producers may be processed out of order relative to each other
2. **Best-effort broadcast**: Events may be dropped by slow subscribers; use `ASYNC_FLUSH` or `SYNC_FLUSH` for critical data
3. **Memory pressure**: Default ZeroMQ high-water marks apply; tune for your workload
4. **Single-engine bottleneck**: Single instance limits throughput; scale via multi-instance with shared storage

### Scaling Guidelines

| Scenario | Solution |
|----------|----------|
| High event throughput | Shard by event type across Engine instances |
| Many homogeneous workers | Increase Engine PUSH socket HWM |
| Geographic distribution | Engine instances per region with inter-region gossip |
| Strict ordering required | Partition by key to single worker |
| Exactly-once semantics | Implement idempotency in handlers + async WAL |
| Backtesting large datasets | Use Parquet format, streaming replay |
| Research data export | Batch to HDF5/Parquet, avoid CSV for large datasets |

## Terminal UI Dashboard

Tyche Engine includes two UI options for monitoring and control:

### TycheTUI (Terminal)

A real-time terminal dashboard built with Textual that is both a **monitor** and a **process supervisor**. It displays live events, module health, and engine stats while also managing the lifecycle of engine and module processes directly from the terminal.

**Features:**
- **Live monitoring**: Real-time event stream, module health, heartbeat status, and engine statistics
- **Process management**: Start, stop, restart, and force-kill engine and module processes
- **Dependency resolution**: Auto-starts processes in topological order based on `dependsOn`
- **Module filtering**: Select a module to filter the event log to that sender only
- **Microsecond timestamps**: Event log shows `HH:MM:SS.mmmuuu` with inline payload preview
- **Keyboard navigation**: `Tab` cycles through processes and modules; all controls are keyboard-driven

See [tui/README.md](tui/README.md) for full documentation.

**Quick Start — TUI as Supervisor:**

```bash
# Terminal 1: Start the TUI (auto-launches engine and modules)
cd tui && pip install -r requirements.txt && python -m tychetui --config tyche-processes.json
```

### TycheApp (Desktop)

An Electron + Vue desktop application providing a modern GUI for trading operations:

- **Event Panel**: Real-time event stream with filtering
- **Greeks Panel**: Live option Greeks visualization
- **Market Making Panel**: Market making controls and spread monitoring
- **Order Panel**: Order submission and lifecycle tracking
- **System Status Panel**: Module health and engine statistics
- **Volatility Curve Panel**: Implied volatility surface visualization

**Quick Start:**

```bash
cd app && npm install && npm run dev
```

## Testing

Tyche Engine maintains a comprehensive test suite across Python and C++:

### Python Tests

```bash
pytest tests/ -v
```

| Category | Location | Coverage Target |
|----------|----------|-----------------|
| Unit tests | `tests/unit/` | >= 80% line coverage |
| Integration tests | `tests/integration/` | Full stack minus external venues |
| Property tests | `tests/property/` | Serialization round-trips |

### C++ Tests

```bash
mkdir build && cd build
cmake .. -A x64 -DBUILD_TESTS=ON
cmake --build . --config Release
ctest -C Release --output-on-failure
```

| Category | Location | Coverage Target |
|----------|----------|-----------------|
| Unit tests | `tests/cpp/` | Core engine + gateway logic |
| Gateway unit tests | `tests/unit/ctp_gateway/` | Config, routing, validation, loader |
| Performance tests | `tests/perf/` | Latency benchmarks, throughput |

### C++ Test Categories

| Test File | Coverage |
|-----------|----------|
| `test_config.cpp` | JSON parsing, field validation, boundary values |
| `test_ctp_loader.cpp` | DLL path validation, resolve logic |
| `test_quote_routing.cpp` | Mixed futures/options routing |
| `test_quote_validator.cpp` | Price jump detection, stale data |
| `test_option_dispatch.cpp` | Queue overflow, graceful stop |
| `test_engine.cpp` | C++ engine core: message serialization, topic queues |
| `test_flat_message.cpp` | FlatMessage serialization round-trips |
| `test_shared_memory_bridge.cpp` | SHM IPC correctness |
| `test_ring_buffer.cpp` | Lock-free queue correctness |
| `test_adaptive_spin.cpp` | Spinlock behavior under contention |

## Project Structure

```
TycheEngine/
├── src/
│   ├── tyche/                    # Core framework (Python + C++)
│   │   ├── engine.py             # Python engine orchestration
│   │   ├── module.py             # Python module base class
│   │   ├── message.py            # Event message model
│   │   ├── heartbeat.py          # Heartbeat protocol
│   │   ├── dead_letter.py        # Dead letter queue
│   │   ├── cpp/                  # C++ engine core
│   │   │   ├── engine/           # Engine primitives
│   │   │   ├── flat_message.h    # Zero-allocation message struct
│   │   │   ├── flat_serializer.h # Fast binary serialization
│   │   │   ├── message.h/cpp     # C++ message system
│   │   │   └── module.h/cpp     # C++ module base
│   │   └── rust/                 # Rust components (future)
│   └── modules/                  # Domain modules
│       ├── ctp_gateway_cpp/      # C++ CTP exchange gateway
│       ├── greeks_engine/        # Option Greeks computation
│       └── static_data/          # Exchange metadata service
├── tests/                        # Test suite (Python + C++)
│   ├── unit/                     # Python unit tests
│   ├── cpp/                      # C++ engine tests
│   ├── unit/ctp_gateway/         # C++ gateway unit tests
│   └── perf/                     # Performance benchmarks
├── app/                          # Electron + Vue desktop app
├── tui/                          # Textual terminal dashboard
├── docs/                         # Design specs, plans, ADRs
├── runtime/                      # Compiled binaries
│   ├── engine/                   # Engine executable
│   └── gateway/                  # Gateway executable
└── data/                         # Runtime data
    └── static/                   # Cached exchange metadata
```

