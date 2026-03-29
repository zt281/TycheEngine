# Pure Python Architecture Design v1

**Date:** 2026-03-28
**Status:** Ready for Review
**Author:** Architect Agent

---

## 1. Overview

This document specifies the complete rewrite of TycheEngine from a hybrid Rust/Python architecture to a pure-Python, process-based microservices architecture. The primary goals are:

1. **Protect proprietary IP** — Remove Rust hot-path code before open-sourcing
2. **Stability and expandability** — Pure Python is easier to debug, test, and extend
3. **Millisecond latency is acceptable** — For current use cases, Python performance is sufficient
4. **Clean evolution path** — Network protocol allows future native (C/C++) modules
5. **Future shared-memory optimization** — IPC sockets can later be replaced with shared memory

---

## 2. Architecture Principles

### 2.1 Complete Process Separation

- Core (Nexus + Bus) and Modules are **completely independent processes**
- No shared code, no shared memory, no imports between Core and Modules
- Communication is **network-only** via ZeroMQ IPC sockets
- Modules only import `tyche-client` (client library), never `tyche-core`

### 2.2 IPC Transport

- **Protocol:** ZeroMQ IPC (Unix domain sockets on Linux, named pipes on Windows)
- **Nexus:** `ipc:///tmp/tyche/nexus.sock` (Linux) or `ipc://tyche-nexus` (Windows)
- **Bus XSUB:** `ipc:///tmp/tyche/bus_xsub.sock` (Linux) or `ipc://tyche-bus-xsub` (Windows)
- **Bus XPUB:** `ipc:///tmp/tyche/bus_xpub.sock` (Linux) or `ipc://tyche-bus-xpub` (Windows)

### 2.3 Type System

- Pure Python `dataclasses` with `frozen=True, slots=True`
- Immutable, hashable for caching
- MessagePack serialization with `"_type"` discriminator

### 2.4 Configuration

- **Core config:** JSON file for Nexus/Bus settings
- **Module configs:** JSON file per module
- **Launcher config:** JSON file defining modules and lifecycle policies
- Core addresses passed to modules via **CLI arguments** (`--nexus`, `--bus-xsub`, `--bus-xpub`)

---

## 3. Package Structure

### 3.1 tyche-core (Core Service)

```
tyche-core/
├── pyproject.toml
└── tyche_core/
    ├── __init__.py
    ├── __main__.py          # Entry point: python -m tyche_core
    ├── nexus.py             # ROUTER socket, registry, lifecycle
    ├── bus.py               # XPUB/XSUB proxy
    └── config.py            # Core configuration loader
```

**Responsibilities:**
- Create and manage IPC socket directory (`/tmp/tyche/`)
- Run Nexus (ROUTER/DEALER) for module registration and commands
- Run Bus (XPUB/XSUB) for data streaming
- Track module health via heartbeats
- Ordered shutdown on signal

**Key Interfaces:**
- `Nexus(endpoint, cpu_core, heartbeat_interval_ms, heartbeat_timeout_ms)` — registration service
- `Bus(xsub_endpoint, xpub_endpoint, cpu_core, high_water_mark)` — pub/sub proxy
- `load_config(path)` → dict — JSON config loader
- `load_config_with_defaults(path)` → dict — config with defaults merged

### 3.2 tyche-client (Client Library)

```
tyche-client/
├── pyproject.toml
└── tyche_client/
    ├── __init__.py
    ├── __main__.py          # Entry point for testing
    ├── module.py            # Module base class
    ├── types.py             # Tick, Quote, Trade, Bar, Order, etc.
    ├── serialization.py     # MessagePack encode/decode
    ├── transport.py         # ZMQ socket management
    └── protocol.py          # Wire protocol constants
```

**Responsibilities:**
- Provide base `Module` class for strategy implementations
- Define all market data and order types as dataclasses
- Handle serialization/deserialization with MessagePack
- Manage ZMQ connections to Core
- Implement registration, heartbeat, and command handling

**Key Interfaces:**
- `Module(nexus_endpoint, bus_xsub_endpoint, bus_xpub_endpoint, config_path)` — base class
- `encode(obj)` → bytes — MessagePack serialization with type discriminator
- `decode(data)` → object — MessagePack deserialization
- `get_socket_address(name)` → str — centralized socket address helper

**Module Abstract Methods:**
- `on_init()` — called after successful registration
- `on_start()` — called when Nexus sends START command
- `on_stop()` — called when Nexus sends STOP command
- `on_reconfigure(new_config)` — called on RECONFIGURE command
- `on_tick(tick)`, `on_quote(quote)`, `on_trade(trade)`, `on_bar(bar)`, `on_order_event(event)` — data handlers

### 3.3 tyche-launcher (Lifecycle Manager)

```
tyche-launcher/
├── pyproject.toml
└── tyche_launcher/
    ├── __init__.py
    ├── __main__.py          # Entry point: python -m tyche_launcher
    ├── launcher.py          # Process management
    ├── monitor.py           # Health checking with circuit breaker
    └── config.py            # Launcher config loader
```

**Responsibilities:**
- Read launcher configuration (modules to start)
- Start each module as independent subprocess
- Monitor health and restart on failure (per restart policy)
- Implement circuit breaker to prevent restart storms
- Graceful shutdown on signal

**Key Interfaces:**
- `Launcher(config)` — process manager
- `ProcessMonitor(name, restart_policy, max_restarts, restart_window_seconds)` — per-process state
- `CircuitBreaker(max_failures, window_seconds)` — prevents restart storms
- `load_launcher_config(path)` → LauncherConfig

---

## 4. Wire Protocol v1

### 4.1 Socket Types

| Component | Socket Type | Endpoint | Purpose |
|-----------|-------------|----------|---------|
| Nexus | ROUTER | `ipc:///tmp/tyche/nexus.sock` | Accept module connections |
| Module | DEALER | connects to Nexus | Register, heartbeat, commands |
| Bus | XSUB | `ipc:///tmp/tyche/bus_xsub.sock` | Accept publisher data |
| Bus | XPUB | `ipc:///tmp/tyche/bus_xpub.sock` | Fan out to subscribers |
| Module | PUB | connects to Bus XSUB | Publish data |
| Module | SUB | connects to Bus XPUB | Subscribe to topics |

### 4.2 Nexus Protocol

All messages are multipart ZMQ frames.

#### Registration Flow

**Module → Nexus (READY)**
```
Frame 1: b"READY"
Frame 2: protocol_version (4 bytes, uint32, big-endian)
Frame 3: json_descriptor (UTF-8 encoded)
```

**JSON Descriptor Fields:**
- `service_name` (str, required) — unique module identifier
- `service_version` (str) — semantic version
- `protocol_version` (int) — wire protocol version
- `subscriptions` (list[str]) — topic patterns to subscribe
- `heartbeat_interval_ms` (int) — desired heartbeat interval
- `capabilities` (list[str]) — e.g., ["publish", "subscribe"]
- `metadata` (dict) — opaque additional data

**Nexus → Module (ACK)**
```
Frame 1: b"ACK"
Frame 2: correlation_id (8 bytes, uint64, big-endian)
Frame 3: assigned_service_id (UTF-8 string)
Frame 4: heartbeat_interval_ms (4 bytes, uint32, big-endian)
```

#### Heartbeat

**Bidirectional (HB)**
```
Frame 1: b"HB"
Frame 2: timestamp_ns (8 bytes, uint64, big-endian)
Frame 3: correlation_id (8 bytes, uint64, big-endian)
```

Sent by both sides at `heartbeat_interval_ms`. If no HB received for 3× interval, peer is considered dead.

#### Commands

**Nexus → Module (CMD)**
```
Frame 1: b"CMD"
Frame 2: command_type (b"START", b"STOP", b"RECONFIGURE", b"STATUS")
Frame 3: payload (JSON for RECONFIGURE, empty for others)
```

**Module → Nexus (REPLY)**
```
Frame 1: b"REPLY"
Frame 2: correlation_id (8 bytes, uint64, big-endian)
Frame 3: status (b"OK" or b"ERROR")
Frame 4: message (UTF-8, empty if OK)
```

#### Disconnect

**Module → Nexus (DISCO)**
```
Frame 1: b"DISCO"
Frame 2: correlation_id (8 bytes, uint64, big-endian)
Frame 3: reason (UTF-8, optional)
```

### 4.3 Bus Protocol

**Publishing:**
```
Frame 1: topic (UTF-8)
Frame 2: payload (MessagePack bytes)
```

**Subscribing:**
- Connect SUB socket to Bus XPUB endpoint
- Set subscription filter: `socket.setsockopt(zmq.SUBSCRIBE, b"PREFIX")`

**Message format (received by subscriber):**
```
Frame 1: topic (UTF-8)
Frame 2: payload (MessagePack bytes)
```

---

## 5. Type System

### 5.1 Core Types

All types are defined in `tyche_client/types.py` as frozen dataclasses with slots.

**Tick** — Individual trade or price update
- `instrument_id: int`
- `price: float`
- `size: float`
- `side: Literal["buy", "sell"]`
- `timestamp_ns: int`

**Quote** — Bid/ask spread
- `instrument_id: int`
- `bid_price: float`, `bid_size: float`
- `ask_price: float`, `ask_size: float`
- `timestamp_ns: int`

**Trade** — Executed trade
- `instrument_id: int`
- `price: float`, `size: float`
- `aggressor_side: Literal["buy", "sell"]`
- `timestamp_ns: int`

**Bar** — OHLCV candlestick
- `instrument_id: int`
- `open: float`, `high: float`, `low: float`, `close: float`
- `volume: float`
- `interval: str` (e.g., "M1", "M5", "H1")
- `timestamp_ns: int`

**Order** — Order request
- `instrument_id: int`
- `client_order_id: int`
- `price: float`, `qty: float`
- `side: Literal["buy", "sell"]`
- `order_type: Literal["market", "limit", "stop", "stop_limit"]`
- `tif: Literal["GTC", "IOC", "FOK"]`
- `timestamp_ns: int`

**OrderEvent** — Order lifecycle event
- `instrument_id: int`
- `client_order_id: int`, `exchange_order_id: int`
- `fill_price: float`, `fill_qty: float`
- `kind: Literal["new", "cancel", "replace", "fill", "partial_fill", "reject"]`
- `timestamp_ns: int`

**Ack** — Order acknowledgment
- `client_order_id: int`, `exchange_order_id: int`
- `status: Literal["accepted", "rejected", "cancel_acked"]`
- `sent_ns: int`, `acked_ns: int`

**Position** — Current position
- `instrument_id: int`
- `net_qty: float`, `avg_cost: float`
- `timestamp_ns: int`

**Risk** — Risk metrics
- `instrument_id: int`
- `delta: float`, `gamma: float`, `vega: float`, `theta: float`
- `dv01: float`, `notional: float`, `margin: float`
- `timestamp_ns: int`

### 5.2 Serialization

MessagePack format with type discriminator:

```json
{
  "_type": "Tick",
  "instrument_id": 12345,
  "price": 150.25,
  "size": 100.0,
  "side": "buy",
  "timestamp_ns": 1711632000000000000
}
```

**Serialization Interface:**
- `encode(obj: Any) -> bytes` — Encode dataclass to MessagePack bytes with `_type` field
- `decode(data: bytes) -> Any` — Decode MessagePack bytes to dataclass using `TYPE_MAP`
- `TYPE_MAP: Dict[str, Type]` — Maps type names to dataclass constructors

---

## 6. Configuration

### 6.1 Core Configuration

`core-config.json`:

```json
{
  "nexus": {
    "endpoint": "ipc:///tmp/tyche/nexus.sock",
    "cpu_core": 0,
    "heartbeat_interval_ms": 1000,
    "heartbeat_timeout_ms": 3000
  },
  "bus": {
    "xsub_endpoint": "ipc:///tmp/tyche/bus_xsub.sock",
    "xpub_endpoint": "ipc:///tmp/tyche/bus_xpub.sock",
    "cpu_core": 1,
    "high_water_mark": 10000
  },
  "launcher": {
    "enabled": false,
    "config_path": "launcher-config.json"
  }
}
```

### 6.2 Module Configuration

`config.json` (in module working directory):

```json
{
  "strategy": {
    "name": "momentum",
    "lookback_period": 20,
    "threshold": 0.001
  },
  "logging": {
    "level": "INFO",
    "file": "logs/momentum.log"
  }
}
```

Module receives Core endpoints via CLI:

```bash
python my_strategy.py \
  --nexus ipc:///tmp/tyche/nexus.sock \
  --bus-xsub ipc:///tmp/tyche/bus_xsub.sock \
  --bus-xpub ipc:///tmp/tyche/bus_xpub.sock \
  --config config.json
```

### 6.3 Launcher Configuration

`launcher-config.json`:

```json
{
  "nexus_endpoint": "ipc:///tmp/tyche/nexus.sock",
  "poll_interval_ms": 1000,
  "modules": [
    {
      "name": "strategy.momentum",
      "command": ["python", "strategies/momentum.py", "--nexus", "..."],
      "restart_policy": "on-failure",
      "max_restarts": 3,
      "restart_window_seconds": 60,
      "cpu_core": 2,
      "environment": {}
    }
  ]
}
```

**Restart policies:**
- `never` — Do not restart
- `always` — Always restart on exit
- `on-failure` — Restart only if exit code != 0

---

## 7. Module Base Class

`tyche_client/module.py` provides the `Module` abstract base class.

**Constructor Signature:**
```python
Module(
    nexus_endpoint: str,
    bus_xsub_endpoint: str,
    bus_xpub_endpoint: str,
    config_path: Optional[str] = None,
    metrics_enabled: bool = False,
    metrics_buffer_size: int = 1024,
)
```

**Key Methods:**
- `run()` — Main event loop (blocking)
- `subscribe(topic_pattern: str)` — Subscribe to Bus topic
- `publish(topic: str, obj: Any)` — Publish object to Bus
- `send_order(order: Order)` — Send order via internal topic

**Lifecycle Methods (to be overridden by subclasses):**
- `on_init()` — Called after successful registration with Nexus
- `on_start()` — Called when Nexus sends START command
- `on_stop()` — Called when Nexus sends STOP command
- `on_reconfigure(new_config: dict)` — Called on RECONFIGURE command
- `on_tick(tick: Tick)` — Handle Tick data
- `on_quote(quote: Quote)` — Handle Quote data
- `on_trade(trade: Trade)` — Handle Trade data
- `on_bar(bar: Bar)` — Handle Bar data
- `on_order_event(event: OrderEvent)` — Handle OrderEvent data

**Protected Helper Methods:**
- `_load_config()` — Load JSON config from `config_path`
- `_encode(obj) -> bytes` — Serialize object to MessagePack
- `_decode(data: bytes) -> Any` — Deserialize MessagePack to object
- `_dispatch(topic: bytes, payload: bytes)` — Route incoming message to handler

**Behavioral Requirements:**
1. Registration uses exponential backoff retry (max 20 attempts)
2. Correlation ID must be verified on ACK to reject stale responses
3. Heartbeats sent at `heartbeat_interval_ms`
4. Corrupt payloads logged and dropped, module continues running
5. STOP command sends REPLY before setting stop flag
6. Clean disconnect sends DISCO before socket close

---

## 8. Example Strategy Requirements

The momentum strategy example demonstrates:

1. **Configuration handling** — Load lookback period and threshold from config
2. **Topic subscription** — Subscribe to `EQUITY.NYSE.*.Tick` and `EQUITY.NYSE.*.Quote`
3. **State management** — Track fast/slow EMA values and current position
4. **Signal generation** — Generate buy when fast MA crosses above slow MA + threshold
5. **Order placement** — Use `send_order()` to submit orders via Bus
6. **Lifecycle compliance** — Implement `on_init`, `on_start`, `on_stop`

---

## 9. Evolution Path

### Phase 1: Pure Python (Current)
- All modules written in Python
- IPC via ZeroMQ domain sockets
- Millisecond-level latency

### Phase 2: Native Modules
- Write performance-critical modules in C/C++
- Provide C client library (`libtyche-cli`)
- Same wire protocol, same IPC endpoints
- Native modules link against `libtyche-cli`

### Phase 3: Shared Memory Optimization
- Replace IPC sockets with shared memory ring buffers for hot path
- Keep control plane (Nexus) on IPC for isolation
- Bus becomes shared memory fabric
- Requires protocol changes, versioned evolution

---

## 10. Error Handling

### Module Startup Errors
- **Socket directory not found:** Create it or fail with clear error
- **Nexus unreachable:** Retry with exponential backoff, max 5 attempts
- **Registration rejected:** Log error, exit with non-zero code

### Runtime Errors
- **Heartbeat timeout:** Nexus marks module as dead, module attempts reconnection
- **Socket error:** Log error, close sockets, attempt graceful shutdown
- **Serialization error:** Log error, drop message, continue

### Shutdown
1. Nexus sends STOP command
2. Module sends REPLY OK
3. Module sends DISCO
4. Module closes sockets
5. Module exits

---

## 11. Testing Strategy

### Unit Tests
- Type serialization/deserialization
- Protocol frame encoding/decoding
- Config loading

### Integration Tests
- Module registration with Nexus
- Pub/sub over Bus
- Heartbeat timeout detection
- Command handling (START/STOP/RECONFIGURE)
- Launcher restart policies

### End-to-End Tests
- Full stack: Core + Module + Launcher
- Record/replay for deterministic testing

---

## 12. Security Considerations

- IPC sockets are protected by filesystem permissions
- Socket directory (`/tmp/tyche/`) should be owned by service user
- No authentication on protocol (assumes trusted local environment)
- Future: Add shared secret authentication if needed

---

## 13. Platform Notes

### Linux
- Uses Unix domain sockets
- Socket directory: `/tmp/tyche/`
- CPU affinity via `os.sched_setaffinity`

### Windows
- Uses named pipes via ZeroMQ IPC transport
- Socket names: `tyche-nexus`, `tyche-bus-xsub`, `tyche-bus-xpub`
- CPU affinity via `SetThreadAffinityMask`

---

## Appendix A: Protocol Constants

```python
# Message types (bytes)
READY = b"READY"
ACK = b"ACK"
HB = b"HB"
CMD = b"CMD"
REPLY = b"REPLY"
DISCO = b"DISCO"

# Command types (bytes)
CMD_START = b"START"
CMD_STOP = b"STOP"
CMD_RECONFIGURE = b"RECONFIGURE"
CMD_STATUS = b"STATUS"

# Status codes (bytes)
STATUS_OK = b"OK"
STATUS_ERROR = b"ERROR"

# Protocol version
PROTOCOL_VERSION = 1

# Default timeouts
DEFAULT_HEARTBEAT_INTERVAL_MS = 1000
DEFAULT_REGISTRATION_TIMEOUT_MS = 5000
HEARTBEAT_TIMEOUT_MULTIPLIER = 3
```

---

## Appendix B: Directory Layout

```
TycheEngine/
├── tyche-core/
│   ├── pyproject.toml
│   └── tyche_core/
│       ├── __init__.py
│       ├── __main__.py
│       ├── nexus.py
│       ├── bus.py
│       └── config.py
├── tyche-client/
│   ├── pyproject.toml
│   └── tyche_client/
│       ├── __init__.py
│       ├── __main__.py
│       ├── module.py
│       ├── types.py
│       ├── serialization.py
│       ├── transport.py
│       └── protocol.py
├── tyche-launcher/
│   ├── pyproject.toml
│   └── tyche_launcher/
│       ├── __init__.py
│       ├── __main__.py
│       ├── launcher.py
│       ├── monitor.py
│       └── config.py
├── strategies/
│   └── momentum.py
├── config/
│   ├── core-config.json
│   ├── launcher-config.json
│   └── modules/
│       └── momentum-config.json
├── tests/
│   ├── unit/
│   │   ├── test_types.py
│   │   ├── test_serialization.py
│   │   ├── test_module.py
│   │   ├── test_bus.py
│   │   ├── test_nexus.py
│   │   ├── test_core_config.py
│   │   ├── test_monitor.py
│   │   └── test_launcher.py
│   └── integration/
│       ├── test_nexus_registration.py
│       ├── test_bus_pubsub.py
│       └── test_launcher.py
├── docs/
│   ├── design/
│   │   └── pure_python_architecture_design_v1.md
│   ├── plan/
│   ├── review/
│   └── impl/
├── README.md
├── CLAUDE.md
└── Makefile
```
