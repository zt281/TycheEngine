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

Tyche Engine is a high-performance distributed event-driven framework written in Python, built on ZeroMQ. It serves as a central processing system for orchestrating multi-process applications. The system consists of two core components:
- Event Management
- Module Management

## Architecture Overview

Tyche Engine uses ZeroMQ as its messaging backbone, leveraging specific socket patterns for different communication needs:

| Communication Pattern | ZeroMQ Pattern | Socket Types | Purpose |
|----------------------|----------------|--------------|---------|
| Module Registration | Request-Reply | REQ (Module) → ROUTER (Engine) | Initial handshake and interface discovery |
| Event Broadcasting | Pub-Sub | XPUB/XSUB Proxy | Fire-and-forget event distribution |
| Load-Balanced Work | Pipeline | PUSH → PULL | Distributing tasks across homogeneous workers |
| Whisper (P2P) | DEALER-ROUTER | DEALER ↔ ROUTER | Direct async module-to-module communication |
| Heartbeat | Pub-Sub | PUB (Engine) / SUB (Modules) | Health monitoring and failure detection |
| ACK Responses | DEALER-ROUTER | ROUTER (Engine) → DEALER (Source) | Asynchronous acknowledgments |

### Multi-Instance Engine Coordination

When running multiple Tyche Engine instances for high availability:
- **Binary Star Pattern** for primary-backup failover
- Shared configuration via distributed consensus (Raft/Paxos) or shared storage
- Message queue state replication between instances
- Automatic failover with client retry via Lazy Pirate pattern

## Modules and Events

Modules are the smallest unit for integrating with Tyche Engine. They can be:

- **Heterogeneous**: Asynchronous independent processes that automatically register their event handling interfaces, event broadcasting interfaces, and single-point communication interfaces (called "Whisper") with Tyche Engine according to the same standard module discovery protocol.

- **Homogeneous**: Multiple instances started with nearly identical configurations (except for CPU core binding) as multi-node modules, exposing the same event handling interfaces, broadcasting interfaces, and single-point communication interfaces to Tyche Engine for load balancing.

Tyche Engine itself is also a module and can start multiple instances for load balancing.

### Standard Module Requirements

A standard module must have the following:

- **Module Type**: The category or class of the module
- **Module Name (UUID)**: Assigned by Tyche Engine, guaranteed to be unique (format: `{deity_name}{6-char MD5}`)
- **Module Settings**: Including CPU core binding, heartbeat interval, timeout thresholds, and restart limits
- **Interface Contract**: Methods following the naming conventions below

#### Event Handling Interfaces

| Interface Pattern | ZeroMQ Pattern | Behavior | Use Case |
|------------------|----------------|----------|----------|
| `on_{event}` | PUSH-PULL | Fire-and-forget, load-balanced across workers | Background processing, no response needed |
| `ack_{event}` | DEALER-ROUTER | Must reply with ACK within timeout | Critical operations requiring confirmation |
| `whisper_{target}_{event}` | DEALER-ROUTER | Direct P2P, bypasses Engine routing | Module-to-module private communication |
| `on_common_{event}` | PUB-SUB | Broadcast to ALL subscribers, no load balancing | Consensus, cache invalidation, state sync |

**Important Design Notes:**
- `ack_{event}` uses idempotent operation assumption — modules must handle duplicate ACK requests gracefully
- `whisper` interfaces are established during registration; both modules must consent to the P2P channel
- `on_common` events have no back-pressure protection — ensure subscribers can keep up or implement Suicidal Snail pattern

#### Broadcasting Interfaces

- `broadcast_{event}`: Publishes event to XPUB socket; Tyche Engine routes to matching SUB subscribers

### Events

Events are the smallest unit of communication between modules registered in Tyche Engine.

Each event consists of:
- **Event name**: Topic identifier for routing (string)
- **Event ID**: Unique UUID for idempotency tracking
- **Timestamp**: Unix timestamp with microsecond precision
- **Source module**: Sender's assigned UUID
- **Data**: Serialized payload (MessagePack recommended)
- **Processing hints**: Optional QoS, priority, TTL

### Event Delivery Guarantees

| Pattern | Delivery | Ordering | Failure Mode |
|---------|----------|----------|--------------|
| `on_` | At-least-once | FIFO per producer | Retry with exponential backoff |
| `ack_` | At-least-once with confirmation | FIFO | Timeout → retry → dead letter |
| `whisper_` | Best-effort or confirmed (configurable) | FIFO | Connection failure → fallback to Engine |
| `on_common_` | Best-effort (no guarantee) | None | Drop if subscriber slow |
| `broadcast_` | Best-effort | None | Drop if subscriber slow |

## Message Management

Tyche Engine implements **Async Persistence** to support production trading, backtesting, and research workflows without blocking the hot path:

### Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         HOT PATH (Sub-millisecond)                   │
│  Module ──▶ Event Router ──▶ Handler ──▶ Lock-free Ring Buffer ──▶   │
│                                          (SPSC, memory-mapped)       │
└─────────────────────────────────────────┬────────────────────────────┘
                                          │
                                          ▼ (async handoff)
┌──────────────────────────────────────────────────────────────────────┐
│                     PERSISTENCE SERVICE (Background)                 │
│  ┌─────────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │
│  │ Batch Processor │─▶│ WAL Writer   │  │ Recovery & Replay Store  │ │
│  │ (100ms/1000 evt)│  │ (crash-safe) │  │                          │ │
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

1. **Lock-free Ring Buffer**: Single-producer, single-consumer (SPSC) queue between hot path and persistence thread
   - Default capacity: 1M events (~256MB, configurable)
   - Memory-mapped for crash recovery of buffer state
   - Sequence numbers ensure strict ordering

2. **Batching**: Events are batched before writing to disk
   - Batch size: 1000 events OR 100ms timeout (whichever comes first)
   - Amortizes disk I/O cost across many events

3. **Backpressure Handling**: If persistence falls behind:
   - **Drop oldest** (research mode): Acceptable loss for analysis
   - **Block and alert** (production mode): Backpressure propagates to producers
   - **Expand buffer** (elastic): Temporarily allocate more memory

### Operating Modes

#### Live Trading Mode
Standard operation with async persistence to WAL for crash recovery.

#### Backtesting Mode
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Replay Store   │────▶│  Backtest       │────▶│  Tyche Engine   │
│  (historical    │     │  Controller     │     │  (same code     │
│   events)       │     │  (simulated     │     │   path as live) │
└─────────────────┘     │   time)         │     └─────────────────┘
                        └─────────────────┘              │
                                                         ▼
                                                 ┌─────────────────┐
                                                 │  Results Store  │
                                                 │  (PnL, fills)   │
                                                 └─────────────────┘
```
- Events replayed at simulated time (deterministic)
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
| Engine crash | Replay WAL from last checkpoint + ring buffer snapshot |
| Module crash | Redeliver un-ACKed messages to available workers |
| Persistence lag | Resume from last committed sequence number |
| Disk full | Alert operators, pause new accepts, allow reads |

### Performance Characteristics

| Metric | Target | Notes |
|--------|--------|-------|
| Hot path latency | <10μs | Python + ZeroMQ inproc |
| Persistence latency | 100ms (batched) | Amortized via batching |
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
| PUB-SUB for broadcasts | Message queue | True broadcast needed for consensus events |
| PUSH-PULL for load balancing | Round-robin REQ-REP | Better back-pressure, natural load distribution |
| DEALER-ROUTER for P2P | Direct TCP | Identity-based routing, async capability |
| Async persistence | Synchronous disk write | Keeps hot path fast; supports backtesting/research |
| Lock-free ring buffer | ZeroMQ PUSH-PULL | Lower latency, memory-mapped for crash recovery |
| Binary Star for HA | Active-Active | Simpler consistency, prevents split-brain |
| Deity-based naming | UUID-only | Human-readable + unique |

### Known Limitations

1. **No total ordering across producers**: Events from different producers may be processed out of order relative to each other
2. **Best-effort broadcast**: `on_common_` events may be dropped by slow subscribers
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

Tyche Engine includes a real-time terminal dashboard for monitoring engine state, active modules, and event flow. Built with OpenTUI and Bun, it provides an intuitive interface for observing system health without leaving the terminal.

See [tui/README.md](tui/README.md) for full documentation.

**Quick Start:**

```bash
# Terminal 1: Start the engine
python examples/run_engine.py

# Terminal 2: Start the TUI dashboard
cd tui && bun install && bun run start
```

## References

- [ZeroMQ Guide](https://zguide.zeromq.org/) - The definitive guide to ZeroMQ patterns
- Paranoid Pirate Pattern - Reliable worker heartbeating
- Async Persistence Pattern - Lock-free ring buffers with background writers
- Disruptor Pattern - High-performance inter-thread messaging (LMAX)
- Binary Star Pattern - High availability primary-backup
