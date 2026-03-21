# TycheEngine — Core Engine Design
**Spec:** `core_engine`
**Version:** v1
**Date:** 2026-03-21
**Status:** Draft

---

## 1. Scope

The core engine is the foundational sub-project of TycheEngine — a multi-asset, institutional-grade trading platform (HFT profile) built on a Python + Rust stack. All subsequent sub-projects (market data, OMS, backtesting, risk, strategy, live execution) depend on the abstractions defined here.

This spec covers:
- Top-level process architecture (Approach B: split control/data plane)
- Instrument model and core data types
- Nexus (Control Hub)
- Bus (Data Hub)
- Module base class
- Project layout and build conventions
- Shared-memory migration path

---

## 2. Top-Level Architecture

### 2.1 Design Choice: Split Control/Data Plane

Each component of TycheEngine runs as an independent OS process pinned to a dedicated CPU core. Two hub processes coordinate all communication:

- **Nexus** (Control Hub): ROUTER/DEALER based Majordomo-style broker. Handles module registration, heartbeating, lifecycle management, and command/reply. Low-throughput, high-reliability.
- **Bus** (Data Hub): XPUB/XSUB proxy. Handles all streaming data — market events, order events, fill events, signals, risk updates. High-throughput, lossy-tolerant on market data.

Control and data planes fail independently. The Bus can keep streaming if Nexus restarts. This also maps cleanly to the shared-memory migration path: the Bus XPUB/XSUB proxy is replaced by Rust SPSC ring buffers without touching Nexus or module control logic.

### 2.2 Process Topology

```
┌─────────────────────────────────────────────────────────┐
│                      TYCHE ENGINE                       │
│                                                         │
│  ┌──────────────┐        ┌──────────────────────────┐   │
│  │    NEXUS     │        │          BUS             │   │
│  │ Control Hub  │        │       Data Hub           │   │
│  │              │        │                          │   │
│  │ ROUTER/DEALER│        │      XPUB/XSUB           │   │
│  │ tcp://*:5555 │        │  pub: tcp://*:5556       │   │
│  │  CPU core 0  │        │  sub: tcp://*:5557       │   │
│  │              │        │       CPU core 1         │   │
│  └──────┬───────┘        └──────────┬───────────────┘   │
│         │ (control)                 │ (data)             │
│    ─────┼───────────────────────────┼─────              │
│         │                           │                    │
│  ┌──────┴───────┐         ┌─────────┴──────┐            │
│  │   Module A   │         │    Module B    │            │
│  │  (e.g. MDS)  │         │   (e.g. OMS)  │            │
│  │  CPU core 2  │         │  CPU core 3   │            │
│  └──────────────┘         └───────────────┘            │
└─────────────────────────────────────────────────────────┘
```

Every module on startup:
1. Pins itself to a configured CPU core
2. Connects to Nexus via DEALER socket — sends `READY <service-name>`, maintains heartbeats
3. Connects to Bus via PUB socket (publish) and SUB socket (subscribe)
4. Receives lifecycle commands (start/stop/reconfigure) only through Nexus
5. Sends/receives all streaming data only through Bus

---

## 3. Instrument Model & Data Types

### 3.1 InstrumentId

A 64-bit integer composed of packed fields:

```
┌─────────┬──────────┬────────────────┬──────────────────┐
│AssetClass│  Venue  │  Base Symbol   │  Expiry/Strike   │
│  4 bits  │ 12 bits │    24 bits     │    24 bits       │
└─────────┴──────────┴────────────────┴──────────────────┘
```

Hashable, comparable, zero-allocation on the hot path.

### 3.2 Asset Classes

| Class | Examples |
|-------|---------|
| `EQUITY` | AAPL, SPY |
| `EQUITY_OPTION` | AAPL 150C 2025-01-17 |
| `FUTURE` | ES Z25, CL H26 |
| `FUTURE_OPTION` | ES options |
| `CRYPTO_SPOT` | BTC-USDT |
| `CRYPTO_PERP` | BTC-USDT-PERP |
| `CRYPTO_FUTURE` | BTC-USDT-250328 |
| `FX_SPOT` | EUR/USD |
| `BOND` | US10Y |

### 3.3 Core Data Types

All types are defined in Rust (`#[repr(C)]`, fixed-size), exposed to Python via PyO3 bindings, and serialized as MessagePack over ZeroMQ.

| Type | Description | Distinct from |
|------|-------------|---------------|
| `Instrument` | Full instrument descriptor (InstrumentId + metadata) | — |
| `Quote` | Both sides — bid price+size, ask price+size, timestamp | `Order` (one side), `Tick` (raw stream) |
| `Trade` | Last executed trade — price, size, aggressor side, timestamp | `Tick` (pre-trade), fill (OMS internal) |
| `Bar` | OHLCV aggregate with `BarInterval` | — |
| `OrderEvent` | Internal OMS lifecycle event — new/cancel/replace/fill/reject | `Ack` (exchange-side confirm) |
| `Position` | Net quantity + avg price + unrealised PnL per instrument | — |
| `Timestamp` | Nanosecond-precision `u64`, UTC | — |
| `Order` | Single-sided order intent — side, price, qty, order type, TIF, instrument | `Quote` (two sides), `OrderEvent` (lifecycle) |
| `Tick` | Raw market data atom — price, size, side, sequence number; snapshot or streaming | `Trade` (confirmed execution), `Bar` (aggregated) |
| `Ack` | Exchange confirmation — exchange order ID, status, `sent_ns`, `acked_ns` | `OrderEvent` (internal), fill (execution) |
| `Risk` | Asset risk exposure — delta, gamma, vega, theta, DV01, notional, margin | `Position` (size/PnL only) |
| `Model` | Model parameters — `ModelKind` tag, fixed-capacity parameter map, version, valid timestamp range | `Risk` (output), market data (input) |

### 3.4 BarInterval

`BarInterval` is a fixed enum — no arbitrary parameterisation:

```python
class BarInterval(Enum):
    MIN_1  = "1MIN"
    MIN_3  = "3MIN"
    MIN_5  = "5MIN"
    MIN_15 = "15MIN"
    MIN_30 = "30MIN"
    MIN_60 = "60MIN"
    HOUR_4 = "4H"
    DAILY  = "1D"
    WEEKLY = "1W"
```

`Bar` embeds `interval: BarInterval` directly. The `on_bar` handler always receives interval as a mandatory parameter.

### 3.5 Clock Abstraction

```python
class Clock(Protocol):
    def now_ns(self) -> int: ...   # nanoseconds since Unix epoch

class LiveClock(Clock): ...        # wraps CLOCK_REALTIME / QueryPerformanceCounter
class SimClock(Clock): ...         # controlled by backtesting engine
```

Every timestamp-bearing type takes a `Clock` source. This makes the entire engine deterministically replayable in backtesting without changing downstream code.

### 3.6 Type Rules

- Fixed-size where possible — no heap allocation on hot path
- `#[repr(C)]` in Rust — castable to/from shared memory in Phase 2
- MessagePack serialization over ZeroMQ (not JSON)
- Immutable once created — updates produce new instances
- Defined once in Rust, imported in Python via PyO3 — no duplicate Python-only definitions

---

## 4. Nexus — Control Hub

### 4.1 Responsibilities

| Responsibility | Mechanism |
|----------------|-----------|
| Module registration | Module sends `READY <service-name> <cpu-core>` on connect |
| Liveness monitoring | Bidirectional heartbeats every 1000ms, 3 missed = module declared dead |
| Lifecycle commands | Routes `START / STOP / RECONFIGURE` to named services |
| Service discovery | Any module queries `mmi.service <name>` → `EXISTS / NOT_FOUND` |
| Ordered shutdown | Sends `STOP` in dependency order on SIGTERM |
| Module restart | Spawns new process for dead module (configurable: auto / alert-only) |

### 4.2 Protocol Frames

```
READY:       [identity | "TYCHE" | "READY"  | service_name | cpu_core]
HEARTBEAT:   [identity | "TYCHE" | "HB"     | timestamp_ns]
COMMAND:     [identity | "TYCHE" | "CMD"    | command | payload_msgpack]
REPLY:       [identity | "TYCHE" | "REPLY"  | request_id | status | payload_msgpack]
DISCONNECT:  [identity | "TYCHE" | "DISCO"  | reason]
```

### 4.3 Module State Machine

```
UNREGISTERED → (READY received)  → REGISTERED
REGISTERED   → (HB missed × 3)  → DEAD
REGISTERED   → (DISCO received) → UNREGISTERED
REGISTERED   → (CMD STOP sent)  → STOPPING → UNREGISTERED
DEAD         → (restart policy) → RESTARTING → REGISTERED
```

### 4.4 Implementation

- Language: Python (`pyzmq`), `zmq.ROUTER` socket, `zmq.Poller` loop
- CPU: pinned to core 0
- Config: `config/modules/nexus.toml` — known services, CPU assignments, restart policies, heartbeat interval
- Module registry entry: `ModuleDescriptor(service_name, pid, cpu_core, status, last_heartbeat_ns, socket_identity)`

---

## 5. Bus — Data Hub

### 5.1 Responsibilities

| Responsibility | Mechanism |
|----------------|-----------|
| Data fan-out | XPUB/XSUB proxy |
| Topic routing | ZeroMQ prefix matching on topic frames |
| Backpressure | `ZMQ_SNDHWM` high-water marks per socket |
| Monitoring | Captures subscription events on XPUB, emits counts to Nexus |

### 5.2 Socket Layout

```
Publishers  →  XSUB tcp://*:5556  ←→  XPUB tcp://*:5557  →  Subscribers
```

### 5.3 Topic Naming Convention

```
<asset_class>.<venue>.<symbol>.<data_type>[.<interval>]

Examples:
  CRYPTO.BINANCE.BTCUSDT.TICK
  CRYPTO.BINANCE.BTCUSDT.QUOTE
  EQUITY.NYSE.AAPL.TRADE
  EQUITY.NYSE.AAPL.BAR.5MIN
  EQUITY.NYSE.AAPL.BAR.15MIN
  INTERNAL.OMS.ORDER_EVENT
  INTERNAL.RISK.RISK_UPDATE
  INTERNAL.MODEL.VOL_SURFACE
  CTRL.NEXUS.HEARTBEAT
```

Prefix subscriptions:
```python
self.subscribe("EQUITY.NYSE.AAPL.BAR.5MIN")    # only 5min bars for AAPL
self.subscribe("EQUITY.NYSE.AAPL.BAR")          # all bar intervals for AAPL
self.subscribe("EQUITY.NYSE.*.BAR.15MIN")        # 15min bars, all NYSE equities
self.subscribe("INTERNAL.RISK")                  # all risk updates
```

### 5.4 Message Envelope

```
Frame 0:  topic (UTF-8 string, prefix-matchable)
Frame 1:  timestamp_ns (u64 big-endian, latency tracing without payload deserialization)
Frame 2:  payload (MessagePack-serialized data type)
```

### 5.5 Backpressure Policy

- Market data topics (`EQUITY.*`, `CRYPTO.*`, `FX.*`): `ZMQ_SNDHWM=10000` — drop oldest under load
- Internal topics (`INTERNAL.*`): `ZMQ_SNDHWM=0` — no drop, block — order/risk events are never silently lost

### 5.6 Implementation

- Language: Python (`pyzmq`), single `zmq.proxy(xsub, xpub)` call
- CPU: pinned to core 1 (alongside Nexus on core 0)
- Config: `config/modules/bus.toml`

---

## 6. Module Base Class

### 6.1 Responsibilities

| Responsibility | Mechanism |
|----------------|-----------|
| CPU core pinning | `os.sched_setaffinity` / `SetThreadAffinityMask` on `start()` |
| Nexus registration | Sends `READY`, maintains heartbeat loop |
| Bus connection | Manages PUB + SUB sockets, subscription registration |
| Message dispatch | Routes inbound Bus messages to typed handler methods |
| Graceful shutdown | Handles `STOP` from Nexus, flushes in-flight work, sends `DISCO` |
| Logging | Structured JSON with `timestamp_ns`, `service_name`, `level` |
| Latency tracing | Reads Frame 1 timestamp from every Bus message, logs end-to-end latency |

### 6.2 Interface

```python
class Module(ABC):
    service_name: str
    cpu_core: int

    # Lifecycle (override these)
    def on_start(self) -> None: ...
    def on_stop(self) -> None: ...
    def on_reconfigure(self, cfg: dict) -> None: ...

    # Subscriptions
    def subscribe(self, topic: str) -> None: ...
    def unsubscribe(self, topic: str) -> None: ...

    # Publishing
    def publish(self, topic: str, payload: Any) -> None: ...

    # Typed data handlers (override to handle data)
    def on_tick(self, topic: str, tick: Tick) -> None: ...
    def on_quote(self, topic: str, quote: Quote) -> None: ...
    def on_trade(self, topic: str, trade: Trade) -> None: ...
    def on_bar(self, topic: str, bar: Bar, interval: BarInterval) -> None: ...
    def on_order(self, topic: str, order: Order) -> None: ...
    def on_order_event(self, topic: str, event: OrderEvent) -> None: ...
    def on_ack(self, topic: str, ack: Ack) -> None: ...
    def on_risk(self, topic: str, risk: Risk) -> None: ...
    def on_model(self, topic: str, model: Model) -> None: ...

    # Commands from Nexus (override if needed)
    def on_command(self, command: str, payload: dict) -> dict: ...

    # Run loop (do not override)
    def run(self) -> None: ...
```

### 6.3 Run Loop

`run()` drives a `zmq.Poller` over three sockets simultaneously:
- **Nexus DEALER** — inbound commands, outbound heartbeats
- **Bus SUB** — inbound data dispatched to typed handlers
- **Internal PAIR** — cross-thread signals from Rust hot-path via FFI

Deserialization (MessagePack → typed struct) is performed in Rust via PyO3 bindings. Python handlers receive fully-constructed typed objects with zero Python-side parsing overhead.

### 6.4 Minimal Concrete Module

```python
class MyStrategy(Module):
    service_name = "strategy.momentum"
    cpu_core = 4

    def on_start(self):
        self.subscribe("EQUITY.NYSE.AAPL.QUOTE")
        self.subscribe("EQUITY.NYSE.AAPL.BAR.5MIN")

    def on_quote(self, topic: str, quote: Quote) -> None:
        if quote.ask - quote.bid > self.threshold:
            order = Order(instrument=quote.instrument, side=Side.BUY, ...)
            self.publish("INTERNAL.OMS.ORDER", order)

    def on_bar(self, topic: str, bar: Bar, interval: BarInterval) -> None:
        # interval is always BarInterval.MIN_5 for this subscription
        ...
```

---

## 7. Project Layout

```
TycheEngine/
├── tyche/                          # Python package root
│   ├── core/
│   │   ├── __init__.py
│   │   ├── clock.py                # Clock protocol, LiveClock, SimClock
│   │   ├── module.py               # Module base class
│   │   ├── nexus.py                # Nexus process (Control Hub)
│   │   ├── bus.py                  # Bus process (Data Hub)
│   │   └── config.py               # NexusConfig, BusConfig, ModuleConfig (TOML)
│   ├── model/
│   │   ├── __init__.py
│   │   ├── instrument.py           # Instrument, InstrumentId, AssetClass, Venue
│   │   ├── types.py                # Quote, Trade, Tick, Bar, Order, OrderEvent,
│   │   │                           # Ack, Position, Risk, Model, BarInterval
│   │   └── enums.py                # Side, OrderType, TIF, BarInterval, ModelKind
│   └── utils/
│       ├── __init__.py
│       ├── serialization.py        # MessagePack encode/decode helpers
│       ├── topics.py               # Topic builder/parser utilities
│       └── logging.py              # Structured JSON logger
│
├── tyche-core/                     # Rust crate — hot path types + serialization
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs
│       ├── types.rs                # #[repr(C)] Tick, Quote, Trade, Bar, Order, etc.
│       ├── instrument.rs           # InstrumentId bit packing
│       ├── clock.rs                # LiveClock, SimClock (Rust side)
│       ├── serialization.rs        # MessagePack encode/decode (rmp-serde)
│       └── python.rs               # PyO3 bindings
│
├── config/
│   ├── engine.toml                 # global: CPU map, Bus/Nexus addresses
│   └── modules/
│       ├── nexus.toml
│       ├── bus.toml
│       └── example_strategy.toml
│
├── docs/
│   ├── resources/
│   │   └── tycheengine_logo_v1.png
│   ├── design/
│   │   └── {spec}_design_{version}.md
│   ├── impl/
│   │   └── {spec}_implement_{version}.md
│   └── review/
│       └── {spec}_review_{version}.log
│
├── tests/
│   ├── unit/
│   │   ├── test_instrument.py
│   │   ├── test_types.py
│   │   └── test_topics.py
│   └── integration/
│       ├── test_nexus_lifecycle.py
│       └── test_bus_pubsub.py
│
├── Cargo.toml                      # Rust workspace root
├── pyproject.toml                  # Python package config (maturin for PyO3 build)
├── Makefile                        # build, test, lint targets
└── LICENSE
```

---

## 8. Shared-Memory Migration Path

The Bus XPUB/XSUB proxy is replaced in Phase 2 by a Rust-based `RingBufferManager`. Module subscription API is unchanged from Python's perspective.

```
Phase 1 (current):
  Module PUB → tcp → Bus XPUB/XSUB → tcp → Module SUB

Phase 2 (future):
  Module Rust writer → SPSC ring buffer (shared memory) → Module Rust reader
  Bus process replaced by RingBufferManager (Rust)
  Python module subscription API: identical
```

Ring buffer types use `#[repr(C)]` layout established in Phase 1, enabling zero-copy cast from ZeroMQ payload bytes to shared-memory slots.

---

## 9. Out of Scope (this spec)

The following are defined as subsequent sub-projects:
- Market data feed handlers and normalisation
- Order Management System (OMS)
- Backtesting engine and historical replay
- Risk engine (Greeks, pre/post-trade checks)
- Strategy framework (signal generation, portfolio management)
- Live exchange/broker connectors
- Research tooling (notebooks, optimisation)
