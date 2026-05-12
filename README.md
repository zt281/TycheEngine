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

Tyche Engine is a high-performance distributed event-driven framework written in Python, built on ZeroMQ. It serves as a central processing system for orchestrating multi-process applications, with a focus on quantitative trading workflows. The system consists of two core components:
- **Event Management** — ZeroMQ-based message broker with topic routing, unified per-topic queues, and async persistence
- **Module Management** — Pluggable module lifecycle, heartbeat-based liveness, and v3 auto-discovery interface model

## Architecture Overview

Tyche Engine is designed as a **multi-process distributed system**. The Engine and each Module run as separate operating system processes, communicating exclusively via ZeroMQ. This provides true process isolation, CPU scaling across cores, and the ability to distribute across machines.

```
Process A                    Process B                    Process C
+------------------+         +------------------+         +------------------+
|   TycheEngine    |<──ZMQ──>|  ExampleModule   |<──ZMQ──>|  ExampleModule   |
|    (engine.py)   |         |  (module.py)     |         |  (module.py)     |
+------------------+         +------------------+         +------------------+
```

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

#### v3 Unified Queue Interface Model

Modules declare handlers using naming conventions discovered automatically at registration:

| Pattern | Prefix | Semantics | Example |
|---------|--------|-----------|---------|
| **ON** | `on_*` | Consumer interface — receives events on this topic | `on_data`, `on_order_submit`, `on_fill` |
| **SEND** | `send_*` | Producer declaration — declares intent to publish | `send_ping`, `send_pong` |

Routing semantics (broadcast, stream, or targeted) are determined by subscriber configuration, not method name prefixes. The v3 model uses unified per-topic queues with configurable backpressure (`DROP_OLDEST`, `DROP_NEWEST`, `BLOCK_PRODUCER`).

**Handler registration details:**
- Methods defined on `TycheModule` itself are skipped
- Abstract methods are skipped (subclasses implement these as callbacks)
- For `on_*` handlers, both the full name and bare topic name are registered (e.g., `on_data` subscribes to both `on_data` and `data`)

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

Built on top of the core framework, Tyche Engine provides a complete quantitative trading domain:

| Module | Purpose | Location |
|--------|---------|----------|
| **Gateway** | Exchange connectivity (CTP, simulated) | `src/modules/trading/gateway/` |
| **OMS** | Order lifecycle management and routing | `src/modules/trading/oms/` |
| **Risk** | Pre-trade risk validation rules engine | `src/modules/trading/risk/` |
| **Portfolio** | Position tracking and P&L calculation | `src/modules/trading/portfolio/` |
| **Strategy** | Strategy framework with context and callbacks | `src/modules/trading/strategy/` |
| **Persistence** | Pluggable event storage (ClickHouse, JSONL) | `src/modules/trading/persistence/` |
| **Store** | Data recording and deterministic replay | `src/modules/trading/store/` |
| **Clock** | Live and simulated time synchronization | `src/modules/trading/clock/` |

### Order Submission Flow

```
StrategyModule
    -> submit_order() via StrategyContext
    -> send_event("order.submit", order_dict)
    -> TycheEngine XSUB socket -> TopicQueue -> XPUB socket
    -> RiskModule (on_order_submit handler)
       -> Evaluates risk rules via RiskRuleEngine
       -> If approved: send_event("order.approved", order_dict)
       -> If rejected: send_event("order.rejected", {...})
    -> OMSModule (on_order_approved handler)
       -> Stores order in OrderStore, routes to Gateway
    -> GatewayModule (on_order_execute handler)
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
| Hot path latency | <10μs | Python + ZeroMQ inproc |
| Persistence latency | 1s (batched) | Amortized via batching |
| Recovery time | <1s | From WAL checkpoint |
| Backtest throughput | >100K events/sec | Limited by CPU, not I/O |

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
| v3 Unified Queue (on_*/send_*) | ack_/whisper_/on_common_ prefixes | Simpler interface model; routing by subscriber config, not method name |
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

Tyche Engine includes a real-time terminal dashboard that is both a **monitor** and a **process supervisor**. Built with OpenTUI and Bun, it displays live events, module health, and engine stats while also managing the lifecycle of engine and module processes directly from the terminal.

### Features

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
cd tui && bun install && bun run start --config tyche-processes.json
```

**Quick Start — Connect to Existing Engine:**

```bash
# Terminal 1: Start the engine
python examples/run_engine.py

# Terminal 2: Start the TUI dashboard
cd tui && bun run start
```

## References

- [ZeroMQ Guide](https://zguide.zeromq.org/) - The definitive guide to ZeroMQ patterns
- Paranoid Pirate Pattern - Reliable worker heartbeating
- Async Persistence Pattern - Lock-free ring buffers with background writers
- Disruptor Pattern - High-performance inter-thread messaging (LMAX)
- Binary Star Pattern - High availability primary-backup
