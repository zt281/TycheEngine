# TycheEngine — Core Engine Design
**Spec:** `core_engine`
**Version:** v2
**Date:** 2026-03-21
**Status:** Draft
**Changes from v1:** Fixed 3 critical, 6 major, 6 minor issues from spec review v1.

---

## 1. Scope

The core engine is the foundational sub-project of TycheEngine — a multi-asset, institutional-grade trading platform (HFT profile) built on a Python + Rust stack. All subsequent sub-projects (market data, OMS, backtesting, risk, strategy, live execution) depend on the abstractions defined here.

This spec covers:
- Top-level process architecture (Approach B: split control/data plane)
- Instrument model and core data types
- Nexus (Control Hub)
- Bus (Data Hub)
- Module base class including Rust FFI bridge
- Project layout and build conventions
- Shared-memory migration path

---

## 2. Top-Level Architecture

### 2.1 Design Choice: Split Control/Data Plane

Each component of TycheEngine runs as an independent OS process pinned to a dedicated CPU core. Two hub processes coordinate all communication:

- **Nexus** (Control Hub): ROUTER/DEALER based Majordomo-style broker. Handles module registration, heartbeating, lifecycle management, and command/reply. Low-throughput, high-reliability.
- **Bus** (Data Hub): XPUB/XSUB proxy. Handles all streaming data — market events, order events, fill events, signals, risk updates. High-throughput.

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
│  │ tcp://*:5555 │        │ xsub: tcp://*:5556 (←pub)│   │
│  │  CPU core 0  │        │ xpub: tcp://*:5557 (→sub)│   │
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

**Bus socket direction:** Publishers connect to the XSUB socket (port 5556); subscribers connect to the XPUB socket (port 5557). The XPUB/XSUB proxy forwards all messages from the XSUB side to all matching XPUB subscribers.

Every module on startup:
1. Pins itself to a configured CPU core
2. Connects to Nexus via DEALER socket — sends `READY`, awaits `READY_ACK`, then maintains heartbeats
3. Connects to Bus via PUB socket on port 5556 (publish) and SUB socket on port 5557 (subscribe)
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
| `CRYPTO_SPOT` | BTCUSDT |
| `CRYPTO_PERP` | BTCUSDT-PERP |
| `CRYPTO_FUTURE` | BTCUSDT-250328 |
| `FX_SPOT` | EURUSD (no slash — normalised) |
| `BOND` | US10Y |

### 3.3 Core Data Types

All types are defined in Rust (`#[repr(C)]`, fixed-size), exposed to Python via PyO3 bindings, and serialized as MessagePack over ZeroMQ. There are **no duplicate Python-only type definitions** — all types in `enums.py` and `types.py` are re-exports of Rust-defined types via `tyche_core`.

| Type | Description | Distinct from |
|------|-------------|---------------|
| `Instrument` | Full instrument descriptor (InstrumentId + metadata) | — |
| `Quote` | Both sides — bid price+size, ask price+size, timestamp | `Order` (one side), `Tick` (raw stream) |
| `Trade` | Last executed trade — price, size, aggressor side, timestamp | `Tick` (pre-trade), fill (OMS internal) |
| `Bar` | OHLCV aggregate with embedded `BarInterval` | — |
| `OrderEvent` | Internal OMS lifecycle event — new/cancel/replace/fill/reject | `Ack` (exchange-side confirm) |
| `Position` | Net quantity + average cost per instrument (no PnL — see note below) | — |
| `Timestamp` | Nanosecond-precision `u64`, UTC | — |
| `Order` | Single-sided order intent — side, price, qty, order type, TIF, instrument | `Quote` (two sides), `OrderEvent` (lifecycle) |
| `Tick` | Raw market data atom — price, size, side, sequence number; snapshot or streaming | `Trade` (confirmed execution), `Bar` (aggregated) |
| `Ack` | Exchange confirmation — exchange order ID, status, `sent_ns`, `acked_ns` | `OrderEvent` (internal), fill (execution) |
| `Risk` | Asset risk exposure — delta, gamma, vega, theta, DV01, notional, margin | `Position` (size/cost only) |
| `Model` | Model parameters — `ModelKind` tag, fixed-capacity parameter map, version, valid timestamp range | `Risk` (output), market data (input) |

**Position note:** `Position` holds `(instrument_id, net_qty, avg_cost)` only. Unrealised PnL is computed by the Risk engine (a subsequent sub-project) which marks positions against live market data. The OMS owns Position updates on fills; the Risk engine owns PnL computation.

### 3.4 BarInterval

`BarInterval` is defined as a `#[repr(u8)]` enum in Rust and re-exported to Python via PyO3. The string representation is used as the topic suffix component directly.

```rust
#[repr(u8)]
pub enum BarInterval {
    M1  = 0,   // topic suffix: "M1"
    M3  = 1,   // topic suffix: "M3"
    M5  = 2,   // topic suffix: "M5"
    M15 = 3,   // topic suffix: "M15"
    M30 = 4,   // topic suffix: "M30"
    H1  = 5,   // topic suffix: "H1"
    H4  = 6,   // topic suffix: "H4"
    D1  = 7,   // topic suffix: "D1"
    W1  = 8,   // topic suffix: "W1"
}
```

`Bar` embeds `interval: BarInterval` directly. The `on_bar` handler always receives `interval` as a mandatory parameter.

### 3.5 ModelKind

```rust
#[repr(u8)]
pub enum ModelKind {
    VolSurface  = 0,   // implied volatility surface parameters
    FairValue   = 1,   // fair value / theoretical price model
    Signal      = 2,   // alpha signal model parameters
    RiskFactor  = 3,   // factor model for risk decomposition
    Custom      = 255, // user-defined; interpret via model metadata
}
```

### 3.6 Clock Abstraction

```python
class Clock(Protocol):
    def now_ns(self) -> int: ...   # nanoseconds since Unix epoch

class LiveClock(Clock): ...        # wraps CLOCK_REALTIME / QueryPerformanceCounter
class SimClock(Clock): ...         # controlled by backtesting engine
```

Every timestamp-bearing type takes a `Clock` source. This makes the entire engine deterministically replayable in backtesting without changing downstream code.

### 3.7 Type Rules

- Fixed-size where possible — no heap allocation on hot path
- `#[repr(C)]` or `#[repr(u8)]` in Rust — castable to/from shared memory in Phase 2
- MessagePack serialization over ZeroMQ (not JSON)
- Immutable once created — updates produce new instances
- Defined once in Rust, imported in Python via PyO3 — no duplicate Python-only definitions

---

## 4. Nexus — Control Hub

### 4.1 Responsibilities

| Responsibility | Mechanism |
|----------------|-----------|
| Module registration | Module sends `READY`, Nexus replies `READY_ACK` |
| Liveness monitoring | Bidirectional heartbeats every 1000ms, 3 missed = module declared dead |
| Lifecycle commands | Routes `START / STOP / RECONFIGURE` to named services |
| Service discovery | Any module queries `mmi.service <name>` → `EXISTS / NOT_FOUND` |
| Ordered shutdown | Sends `STOP` in dependency order on SIGTERM |
| Module restart | Spawns new process for dead module (configurable: auto / alert-only) |

### 4.2 Protocol Frames

```
READY:      [identity | "TYCHE" | "READY"     | service_name | cpu_core]
READY_ACK:  [identity | "TYCHE" | "READY_ACK" | request_id   | timestamp_ns]
HEARTBEAT:  [identity | "TYCHE" | "HB"        | timestamp_ns]
COMMAND:    [identity | "TYCHE" | "CMD"        | command | payload_msgpack]
REPLY:      [identity | "TYCHE" | "REPLY"      | request_id | status | payload_msgpack]
DISCONNECT: [identity | "TYCHE" | "DISCO"      | reason]
```

`request_id` in `READY_ACK` matches the `timestamp_ns` of the originating `READY` frame, enabling modules to detect stale acknowledgements.

### 4.3 Registration Retry Policy

1. Module sends `READY` and starts a 500ms timer.
2. If `READY_ACK` is not received within 500ms, resend `READY`.
3. Retry up to 20 times (10 seconds total).
4. If no `READY_ACK` after 20 retries, module logs a fatal error and exits.

This handles the case where Nexus is slow to start or the initial `READY` is lost in the DEALER send buffer.

### 4.4 Module State Machine

```
UNREGISTERED → (READY_ACK received) → REGISTERED
REGISTERED   → (HB missed × 3)     → DEAD
REGISTERED   → (DISCO received)    → UNREGISTERED
REGISTERED   → (CMD STOP sent)     → STOPPING → UNREGISTERED
DEAD         → (restart policy)    → RESTARTING → REGISTERED
```

### 4.5 Implementation

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
| Slow consumer detection | Monitor XPUB subscription events; alert Nexus when subscriber lag is detected |

### 5.2 Socket Layout

```
Publishers  →  XSUB tcp://*:5556  ←→  XPUB tcp://*:5557  →  Subscribers
```

Publishers connect to port **5556** (XSUB side). Subscribers connect to port **5557** (XPUB side).

### 5.3 Topic Naming Convention

Topics use the full asset class enum name as the first component. ZeroMQ performs **prefix matching only** — no glob or wildcard. Clients requiring cross-symbol subscriptions subscribe to the broadest applicable prefix and filter by topic in the handler.

```
<asset_class>.<venue>.<symbol>.<data_type>[.<interval>]

Examples:
  CRYPTO_SPOT.BINANCE.BTCUSDT.TICK
  CRYPTO_SPOT.BINANCE.BTCUSDT.QUOTE
  CRYPTO_PERP.BINANCE.BTCUSDT-PERP.TICK
  EQUITY.NYSE.AAPL.TRADE
  EQUITY.NYSE.AAPL.BAR.M5
  EQUITY.NYSE.AAPL.BAR.M15
  EQUITY_OPTION.CBOE.AAPL.QUOTE
  FX_SPOT.EBS.EURUSD.TICK
  INTERNAL.OMS.ORDER_EVENT
  INTERNAL.RISK.RISK_UPDATE
  INTERNAL.MODEL.VOL_SURFACE
  CTRL.NEXUS.HEARTBEAT
```

**Symbol normalisation:** Symbols in topics are alphanumeric and hyphen only. Slashes, spaces, and dots are stripped (e.g. `EUR/USD` → `EURUSD`). The `topics.py` utility enforces this at topic construction time.

Prefix subscriptions (no wildcards):
```python
self.subscribe("EQUITY.NYSE.AAPL.BAR.M5")     # only 5min bars for AAPL
self.subscribe("EQUITY.NYSE.AAPL.BAR")          # all bar intervals for AAPL
self.subscribe("EQUITY.NYSE")                   # all data for all NYSE equities
self.subscribe("INTERNAL.RISK")                 # all risk updates
```

### 5.4 Message Envelope

```
Frame 0:  topic (UTF-8 string, prefix-matchable)
Frame 1:  timestamp_ns (u64 big-endian, latency tracing without payload deserialization)
Frame 2:  payload (MessagePack-serialized data type)
```

Frame 1 is always present so any subscriber can measure end-to-end latency without deserializing the payload.

### 5.5 Backpressure Policy

`zmq.proxy()` provides no blocking backpressure feedback from Bus back to publishers — the Bus buffers outbound messages per subscriber. The policy is therefore:

- **All topics:** `ZMQ_SNDHWM=10000` per subscriber socket. When the high-water mark is reached for a given subscriber, ZeroMQ drops the oldest message for that subscriber silently.
- **Slow consumer detection:** Bus monitors XPUB socket events to detect when a subscriber's queue is persistently near the HWM. It emits a `CTRL.NEXUS.SLOW_CONSUMER` alert to Nexus (not to the Bus proxy itself — this is published via a separate monitor PUB socket), which can trigger a module restart or operator alert.
- **INTERNAL.\* reliability:** Guaranteed delivery cannot be achieved through the Bus alone. Modules publishing to `INTERNAL.*` topics (OMS, risk) that require reliable delivery should additionally maintain a local event log and implement replay-on-reconnect when a subscriber re-registers with Nexus.

### 5.6 Implementation

- Language: Python (`pyzmq`), `zmq.proxy(xsub, xpub, capture)` — the capture socket feeds the slow-consumer monitor
- CPU: pinned to core 1
- Config: `config/modules/bus.toml`

---

## 6. Module Base Class

### 6.1 Responsibilities

| Responsibility | Mechanism |
|----------------|-----------|
| CPU core pinning | Platform affinity call on `start()` — see §6.5 |
| Nexus registration | Sends `READY`, retries per §4.3, maintains heartbeat loop |
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
- **Internal PAIR** (`inproc://tyche-rust-{service_name}`) — signals from Rust hot-path via FFI (see §6.4)

Deserialization (MessagePack → typed struct) is performed in Rust via PyO3 bindings. Python handlers receive fully-constructed typed objects with zero Python-side parsing overhead.

### 6.4 Rust FFI Bridge

The Internal PAIR socket provides a zero-copy notification channel between the Rust hot-path crate and the Python event loop within the same process.

**Socket:** `inproc://tyche-rust-{service_name}` — PAIR/PAIR, in-process only.

**Initialisation:** On module startup, the Python `Module` creates both ends of the PAIR. The Rust end is obtained via a PyO3-exported call:
```python
rust_handle = tyche_core.init_ffi_bridge(service_name)  # returns opaque handle
```
The handle is passed to any Rust component that needs to send signals to the Python loop.

**Message format:**
```
Byte 0:    signal type (u8)
Bytes 1-N: MessagePack payload (optional, type-dependent)
```

**Signal types (initial set):**

| Value | Name | Payload | Meaning |
|-------|------|---------|---------|
| `0x01` | `DATA_READY` | topic (str) | Rust has written a new item to a local buffer; Python should call the typed handler |
| `0x02` | `SHUTDOWN` | none | Rust requests clean shutdown of the Python loop |
| `0x03` | `ERROR` | error string | Rust encountered a fatal error |

Additional signal types are defined per sub-project (e.g. `FILL_READY` for the OMS).

### 6.5 Platform CPU Affinity

CPU pinning is performed at the start of `Module.run()`:

**Linux:**
```python
os.sched_setaffinity(0, {self.cpu_core})
```

**Windows:**
```python
import ctypes
handle = ctypes.windll.kernel32.GetCurrentThread()
ctypes.windll.kernel32.SetThreadAffinityMask(handle, 1 << self.cpu_core)
```

Note: On Windows, `SetThreadAffinityMask` pins the calling thread. Since CPython is effectively single-threaded per process (GIL), this is equivalent to process-level affinity for Python modules. For Rust threads spawned within the same process, affinity is set explicitly per thread using the `core_affinity` crate.

**Windows is a supported development platform.** Linux is the production target. Any module behaviour that differs between platforms must be documented in the module's config file.

### 6.6 Minimal Concrete Module

```python
class MyStrategy(Module):
    service_name = "strategy.momentum"
    cpu_core = 4

    def on_start(self):
        self.subscribe("EQUITY.NYSE.AAPL.QUOTE")
        self.subscribe("EQUITY.NYSE.AAPL.BAR.M5")

    def on_quote(self, topic: str, quote: Quote) -> None:
        if quote.ask - quote.bid > self.threshold:
            order = Order(instrument=quote.instrument, side=Side.BUY, ...)
            self.publish("INTERNAL.OMS.ORDER", order)

    def on_bar(self, topic: str, bar: Bar, interval: BarInterval) -> None:
        # interval is always BarInterval.M5 for this subscription
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
│   │   ├── types.py                # Re-exports from tyche_core: Quote, Trade, Tick,
│   │   │                           # Bar, Order, OrderEvent, Ack, Position, Risk, Model
│   │   └── enums.py                # Re-exports from tyche_core: Side, OrderType, TIF,
│   │                               # BarInterval, ModelKind, AssetClass
│   └── utils/
│       ├── __init__.py
│       ├── serialization.py        # MessagePack encode/decode helpers
│       ├── topics.py               # Topic builder/parser (enforces symbol normalisation)
│       └── logging.py              # Structured JSON logger
│
├── tyche-core/                     # Rust crate — hot path types + serialization
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs
│       ├── types.rs                # #[repr(C)] Tick, Quote, Trade, Bar, Order, etc.
│       ├── instrument.rs           # InstrumentId bit packing
│       ├── enums.rs                # BarInterval (#[repr(u8)]), ModelKind, Side, etc.
│       ├── clock.rs                # LiveClock, SimClock (Rust side)
│       ├── serialization.rs        # MessagePack encode/decode (rmp-serde)
│       ├── ffi_bridge.rs           # PAIR socket FFI bridge implementation
│       └── python.rs               # PyO3 bindings — exports all public types + init_ffi_bridge
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
│   │   ├── core_engine_design_v1.md
│   │   └── core_engine_design_v2.md
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

### 7.1 Build Requirements

| Component | Minimum Version | Notes |
|-----------|----------------|-------|
| Rust toolchain | 1.78.0 (stable) | Edition 2021 |
| maturin | 1.5.0 | `pip install maturin>=1.5` |
| PyO3 | 0.22.x | `pyo3 = { version = "0.22", features = ["extension-module"] }` |
| Python | 3.11+ | Required for `tomllib` in stdlib |
| pyzmq | 25.0+ | Must match installed libzmq >= 4.3.4 |
| rmp-serde | 1.3.x | MessagePack serialization |
| core_affinity | 0.8.x | Rust thread CPU pinning |

Build command: `maturin develop --release` (dev), `maturin build --release` (dist).

---

## 8. Shared-Memory Migration Path

The Bus XPUB/XSUB proxy is replaced in Phase 2 by a Rust-based `RingBufferManager`. Module subscription API is unchanged from Python's perspective.

```
Phase 1 (current):
  Module PUB → tcp:5556 → Bus XPUB/XSUB → tcp:5557 → Module SUB

Phase 2 (future):
  Module Rust writer → SPSC ring buffer (shared memory) → Module Rust reader
  Bus process replaced by RingBufferManager (Rust)
  Python module subscription API: identical
```

**Fan-out model for Phase 2:** The `RingBufferManager` maintains one SPSC ring buffer per `(topic, subscriber)` pair. A Rust routing thread reads from each publisher's write-side buffer and copies into the read-side buffers of all matching subscribers. This preserves the one-to-many fan-out semantics of XPUB/XSUB while eliminating network stack overhead.

Ring buffer types use `#[repr(C)]` layout established in Phase 1, enabling zero-copy cast from ZeroMQ payload bytes to shared-memory slots during any transition period.

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
