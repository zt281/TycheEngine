# Architecture

*Generated: 2026-04-21*

## System Pattern

TycheEngine is a **central broker / distributed module** architecture built on ZeroMQ. The engine runs as a standalone process; modules (trading gateways, strategies, risk, OMS, portfolio) run as separate processes and communicate via ZMQ sockets.

```
+------------------+         +------------------+
|   TycheEngine    |<------->|  ExampleModule   |
|    (process)     |  ZMQ    |    (process)     |
+------------------+         +------------------+
       ^
       | (registration, events, heartbeat, admin)
       v
+------+------+------+------+
| Gateway | Strategy | Risk | OMS | Portfolio |
+---------+----------+------+-----+-----------+
```

## Communication Patterns

| Pattern | ZeroMQ Sockets | Purpose |
|---------|---------------|---------|
| Registration | REQ <-> ROUTER | Module handshake and interface discovery |
| Event Broadcasting | XPUB/XSUB Proxy | Fire-and-forget event distribution |
| Load-Balanced Work | PUSH -> PULL | Distributing tasks across workers |
| Whisper (P2P) | DEALER <-> ROUTER | Direct async module-to-module communication |
| Heartbeat | PUB/SUB | Health monitoring (Paranoid Pirate Pattern) |
| ACK Responses | ROUTER -> DEALER | Asynchronous acknowledgments |
| Admin queries | ROUTER | Engine status, module list, stats |

## Core Components

### TycheEngine (`src/tyche/engine.py`)

Central broker with 6 worker threads:
1. **Registration worker** — ROUTER socket accepting module registrations
2. **Heartbeat worker** — PUB socket broadcasting engine heartbeats
3. **Heartbeat receive worker** — ROUTER socket receiving module heartbeats
4. **Monitor worker** — Checks liveness and unregisters expired modules
5. **Event proxy worker** — XPUB/XSUB proxy forwarding events between publishers and subscribers
6. **Admin worker** — ROUTER socket for STATUS/MODULES/STATS queries

### TycheModule (`src/tyche/module.py`)

Base class for all modules. Each module:
- Registers interfaces with the engine via one-shot REQ socket
- Publishes events via PUB socket to engine's XSUB
- Subscribes to events via SUB socket from engine's XPUB
- Sends heartbeats via DEALER socket
- Dispatches incoming events to registered handlers

### ModuleBase (`src/tyche/module_base.py`)

Minimal base class defining the `start()` / `stop()` contract.

### Message System (`src/tyche/message.py`)

- `Message` dataclass with msgpack serialization
- `Envelope` for ZeroMQ routing frames
- Custom `Decimal` encoding/decoding to preserve precision

### Heartbeat (`src/tyche/heartbeat.py`)

Implements Paranoid Pirate Pattern:
- `HeartbeatMonitor` — per-peer liveness tracking
- `HeartbeatSender` — periodic heartbeat transmission
- `HeartbeatManager` — multi-peer registry with expiration

## Trading Domain Architecture (`src/modules/trading/`)

### Event Flow

```
Gateway --(quote/trade)--> Engine --> Strategy
Strategy --(order.submit)--> Risk --(order.approved)--> OMS
OMS --(order.execute)--> Gateway --> Exchange
Gateway --(fill)--> OMS --> Portfolio
Gateway --(position)--> Portfolio --> Strategy/Risk
```

### Layer Responsibilities

| Layer | Key Classes | Responsibility |
|-------|-------------|--------------|
| Gateway | `GatewayModule`, `CtpGateway` | Exchange connectivity, market data normalization, order routing |
| Strategy | `StrategyModule` | Signal generation, order submission via `StrategyContext` |
| OMS | `OrderStore`, `OMSModule` | Order lifecycle, state tracking |
| Risk | `RiskModule`, `RiskRules` | Pre-trade validation, position limits |
| Portfolio | `PortfolioModule` | Position tracking, P&L calculation |
| Clock | `Clock` | Time abstraction (live vs simulated) |
| Store | `Recorder`, `Replay` | Event recording and backtest replay |

### Gateway Internals (CTP)

The CTP gateway bridges CTP's async SPI callback model with TycheEngine's event system:

1. CTP SPI callbacks arrive on CTP's internal threads
2. Callbacks enqueue `(event_type, payload)` tuples to a `queue.Queue`
3. A dedicated dispatcher thread polls the queue and publishes via `send_event()`
4. This isolates CTP thread semantics from TycheEngine's ZMQ threads

### Connection State Machine

`ConnectionStateMachine` (`src/modules/trading/gateway/ctp/state_machine.py`) manages gateway connection lifecycle:

```
IDLE -> CONNECTING -> CONNECTED -> RECONNECTING -> CONNECTING -> ...
                \            \                              /
                 v            v                            /
              DISCONNECTED <-------------------------------
```

With exponential backoff and jitter for auto-reconnect.

## Module Naming

Modules receive IDs in format `{deity_name}{6-char hex}` where deities are drawn from Greek mythology (zeus, athena, hermes, etc.).

## Interface Patterns

| Pattern | Prefix | Behavior |
|---------|--------|----------|
| Fire-and-forget | `on_` | PUSH-PULL, load-balanced |
| Must reply | `ack_` | DEALER-ROUTER, requires ACK |
| Direct P2P | `whisper_` | DEALER-ROUTER, bypasses engine |
| Broadcast all | `on_common_` | PUB-SUB |
| Engine publish | `broadcast_` | XPUB |
