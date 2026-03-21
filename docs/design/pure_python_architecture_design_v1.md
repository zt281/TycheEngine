# Pure Python Architecture Design v1

**Date:** 2026-03-28
**Status:** Draft → Ready for Review
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
- Modules only import `tyche-cli` (client library), never `tyche-core`

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

### 3.2 tyche-cli (Client Library)

```
tyche-cli/
├── pyproject.toml
└── tyche_cli/
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

### 3.3 tyche-launcher (Lifecycle Manager)

```
tyche-launcher/
├── pyproject.toml
└── tyche_launcher/
    ├── __init__.py
    ├── __main__.py          # Entry point: python -m tyche_launcher
    ├── launcher.py          # Process management
    ├── monitor.py           # Health checking
    └── config.py            # Launcher config loader
```

**Responsibilities:**
- Read launcher configuration (modules to start)
- Start each module as independent subprocess
- Monitor health and restart on failure (per restart policy)
- Graceful shutdown on signal

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

**JSON Descriptor:**
```json
{
  "service_name": "strategy.momentum",
  "service_version": "1.0.0",
  "protocol_version": 1,
  "subscriptions": ["EQUITY.NYSE.*.Tick"],
  "heartbeat_interval_ms": 1000,
  "capabilities": ["publish", "subscribe"],
  "metadata": {}
}
```

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

All types are defined in `tyche_cli/types.py`:

```python
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True, slots=True)
class Tick:
    instrument_id: int
    price: float
    size: float
    side: Literal["buy", "sell"]
    timestamp_ns: int

@dataclass(frozen=True, slots=True)
class Quote:
    instrument_id: int
    bid_price: float
    bid_size: float
    ask_price: float
    ask_size: float
    timestamp_ns: int

@dataclass(frozen=True, slots=True)
class Trade:
    instrument_id: int
    price: float
    size: float
    aggressor_side: Literal["buy", "sell"]
    timestamp_ns: int

@dataclass(frozen=True, slots=True)
class Bar:
    instrument_id: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    interval: str  # e.g., "M1", "M5", "H1"
    timestamp_ns: int

@dataclass(frozen=True, slots=True)
class Order:
    instrument_id: int
    client_order_id: int
    price: float
    qty: float
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit", "stop", "stop_limit"]
    tif: Literal["GTC", "IOC", "FOK"]
    timestamp_ns: int

@dataclass(frozen=True, slots=True)
class OrderEvent:
    instrument_id: int
    client_order_id: int
    exchange_order_id: int
    fill_price: float
    fill_qty: float
    kind: Literal["new", "cancel", "replace", "fill", "partial_fill", "reject"]
    timestamp_ns: int

@dataclass(frozen=True, slots=True)
class Ack:
    client_order_id: int
    exchange_order_id: int
    status: Literal["accepted", "rejected", "cancel_acked"]
    sent_ns: int
    acked_ns: int

@dataclass(frozen=True, slots=True)
class Position:
    instrument_id: int
    net_qty: float
    avg_cost: float
    timestamp_ns: int

@dataclass(frozen=True, slots=True)
class Risk:
    instrument_id: int
    delta: float
    gamma: float
    vega: float
    theta: float
    dv01: float
    notional: float
    margin: float
    timestamp_ns: int
```

### 5.2 Serialization

MessagePack format with type discriminator:

```python
{
  "_type": "Tick",
  "instrument_id": 12345,
  "price": 150.25,
  "size": 100.0,
  "side": "buy",
  "timestamp_ns": 1711632000000000000
}
```

Serialization functions:

```python
def encode(obj: Any) -> bytes:
    """Encode a dataclass to MessagePack bytes."""
    ...

def decode(data: bytes) -> Any:
    """Decode MessagePack bytes to a dataclass."""
    ...

TYPE_MAP = {
    "Tick": Tick,
    "Quote": Quote,
    "Trade": Trade,
    "Bar": Bar,
    "Order": Order,
    "OrderEvent": OrderEvent,
    "Ack": Ack,
    "Position": Position,
    "Risk": Risk,
}
```

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
    "registration_timeout_ms": 5000
  },
  "bus": {
    "xsub_endpoint": "ipc:///tmp/tyche/bus_xsub.sock",
    "xpub_endpoint": "ipc:///tmp/tyche/bus_xpub.sock",
    "cpu_core": 1
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
  "core": {
    "nexus_endpoint": "ipc:///tmp/tyche/nexus.sock",
    "bus_xsub_endpoint": "ipc:///tmp/tyche/bus_xsub.sock",
    "bus_xpub_endpoint": "ipc:///tmp/tyche/bus_xpub.sock"
  },
  "modules": [
    {
      "name": "momentum",
      "command": "python",
      "args": ["strategies/momentum.py"],
      "working_dir": "./strategies",
      "config_file": "./strategies/config.json",
      "env": {
        "STRATEGY_NAME": "momentum"
      },
      "cpu_core": 2,
      "restart_policy": "always",
      "depends_on": []
    },
    {
      "name": "arbitrage",
      "command": "./arbitrage/arbitrage_module",
      "args": [],
      "working_dir": "./arbitrage",
      "config_file": "./arbitrage/config.json",
      "restart_policy": "on-failure",
      "max_restarts": 5,
      "depends_on": ["momentum"]
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

```python
# tyche_cli/module.py

import zmq
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional
from dataclasses import asdict

from .types import Tick, Quote, Trade, Bar, Order
from .serialization import encode, decode
from .transport import create_dealer_socket, create_pub_socket, create_sub_socket
from .protocol import READY, ACK, HB, CMD, REPLY, DISCO

class Module(ABC):
    """Base class for all TycheEngine modules.

    Modules are completely independent processes that communicate with Core
    via ZeroMQ IPC sockets. They import only tyche_cli, never tyche_core.
    """

    service_name: str = "module.base"
    service_version: str = "1.0.0"

    def __init__(
        self,
        nexus_endpoint: str,
        bus_xsub_endpoint: str,
        bus_xpub_endpoint: str,
        config_path: Optional[str] = None,
    ):
        self.nexus_endpoint = nexus_endpoint
        self.bus_xsub_endpoint = bus_xsub_endpoint
        self.bus_xpub_endpoint = bus_xpub_endpoint
        self.config_path = config_path

        self._config: Dict[str, Any] = {}
        self._correlation_id: int = 0
        self._running = False
        self._ctx = zmq.Context()
        self._nexus_socket: Optional[zmq.Socket] = None
        self._pub_socket: Optional[zmq.Socket] = None
        self._sub_socket: Optional[zmq.Socket] = None
        self._poller = zmq.Poller()

        self._logger = logging.getLogger(self.service_name)

        # Handlers for different message types
        self._handlers: Dict[str, Callable] = {
            "Tick": self.on_tick,
            "Quote": self.on_quote,
            "Trade": self.on_trade,
            "Bar": self.on_bar,
            "OrderEvent": self.on_order_event,
        }

    def _load_config(self) -> None:
        """Load module configuration from JSON file."""
        if self.config_path:
            with open(self.config_path) as f:
                self._config = json.load(f)

    def _register(self) -> bool:
        """Register with Nexus. Returns True on success."""
        # Implementation details in spec
        ...

    def _send_heartbeat(self) -> None:
        """Send heartbeat to Nexus."""
        ...

    def _handle_command(self, cmd_type: bytes, payload: bytes) -> None:
        """Handle command from Nexus."""
        if cmd_type == b"START":
            self.on_start()
        elif cmd_type == b"STOP":
            self.on_stop()
            self._running = False
        elif cmd_type == b"RECONFIGURE":
            new_config = json.loads(payload)
            self.on_reconfigure(new_config)
        elif cmd_type == b"STATUS":
            self._send_status()

    def _dispatch(self, topic: bytes, payload: bytes) -> None:
        """Dispatch incoming Bus message to appropriate handler."""
        obj = decode(payload)
        handler = self._handlers.get(type(obj).__name__)
        if handler:
            handler(obj)

    def subscribe(self, topic_pattern: str) -> None:
        """Subscribe to topic pattern on Bus."""
        if self._sub_socket:
            self._sub_socket.setsockopt(zmq.SUBSCRIBE, topic_pattern.encode())

    def publish(self, topic: str, obj: Any) -> None:
        """Publish object to Bus topic."""
        if self._pub_socket:
            self._pub_socket.send_multipart([
                topic.encode(),
                encode(obj)
            ])

    def send_order(self, order: Order) -> None:
        """Send order via internal topic."""
        self.publish("INTERNAL.OMS.ORDER", order)

    def run(self) -> None:
        """Main run loop."""
        self._load_config()

        # Create and connect sockets
        self._nexus_socket = create_dealer_socket(self._ctx, self.nexus_endpoint)
        self._pub_socket = create_pub_socket(self._ctx, self.bus_xsub_endpoint)
        self._sub_socket = create_sub_socket(self._ctx, self.bus_xpub_endpoint)

        # Register with Nexus
        if not self._register():
            self._logger.error("Failed to register with Nexus")
            return

        self._running = True
        self._poller.register(self._nexus_socket, zmq.POLLIN)
        self._poller.register(self._sub_socket, zmq.POLLIN)

        while self._running:
            events = dict(self._poller.poll(timeout=100))  # 100ms timeout for heartbeat

            # Handle Nexus messages
            if self._nexus_socket in events:
                frames = self._nexus_socket.recv_multipart()
                self._handle_nexus_message(frames)

            # Handle Bus messages
            if self._sub_socket in events:
                topic, payload = self._sub_socket.recv_multipart()
                self._dispatch(topic, payload)

            # Send heartbeat
            self._send_heartbeat()

        # Cleanup
        self._nexus_socket.send_multipart([
            DISCO,
            str(self._correlation_id).encode()
        ])
        self._nexus_socket.close()
        self._pub_socket.close()
        self._sub_socket.close()
        self._ctx.term()

    # Abstract methods for subclasses
    @abstractmethod
    def on_init(self) -> None:
        """Called after successful registration."""
        pass

    @abstractmethod
    def on_start(self) -> None:
        """Called when Nexus sends START command."""
        pass

    @abstractmethod
    def on_stop(self) -> None:
        """Called when Nexus sends STOP command."""
        pass

    def on_reconfigure(self, new_config: Dict[str, Any]) -> None:
        """Called when Nexus sends RECONFIGURE command."""
        self._config.update(new_config)

    def on_tick(self, tick: Tick) -> None:
        """Override to handle Tick messages."""
        pass

    def on_quote(self, quote: Quote) -> None:
        """Override to handle Quote messages."""
        pass

    def on_trade(self, trade: Trade) -> None:
        """Override to handle Trade messages."""
        pass

    def on_bar(self, bar: Bar) -> None:
        """Override to handle Bar messages."""
        pass

    def on_order_event(self, event: Any) -> None:
        """Override to handle OrderEvent messages."""
        pass
```

---

## 8. Example Strategy

```python
#!/usr/bin/env python3
"""Momentum strategy example."""

import argparse
import logging
from tyche_cli import Module, Tick, Quote, Order

class MomentumStrategy(Module):
    service_name = "strategy.momentum"
    service_version = "1.0.0"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.fast_ma = 0.0
        self.slow_ma = 0.0
        self.position = 0

    def on_init(self):
        """Called after registration."""
        self.subscribe("EQUITY.NYSE.*.Tick")
        self.subscribe("EQUITY.NYSE.*.Quote")

        cfg = self._config.get("strategy", {})
        self.lookback = cfg.get("lookback_period", 20)
        self.threshold = cfg.get("threshold", 0.001)

        self.logger.info(f"Momentum strategy initialized: lookback={self.lookback}")

    def on_start(self):
        """Called on START command."""
        self.logger.info("Strategy started")

    def on_stop(self):
        """Called on STOP command."""
        self.logger.info("Strategy stopped")

    def on_tick(self, tick: Tick):
        """Process tick data."""
        # Update moving averages
        alpha_fast = 2.0 / (self.lookback / 2 + 1)
        alpha_slow = 2.0 / (self.lookback + 1)

        self.fast_ma = alpha_fast * tick.price + (1 - alpha_fast) * self.fast_ma
        self.slow_ma = alpha_slow * tick.price + (1 - alpha_slow) * self.slow_ma

        # Trading logic
        if self.fast_ma > self.slow_ma * (1 + self.threshold) and self.position <= 0:
            # Buy signal
            self.send_order(Order(
                instrument_id=tick.instrument_id,
                client_order_id=self._next_order_id(),
                price=tick.price,
                qty=100.0,
                side="buy",
                order_type="limit",
                tif="GTC",
                timestamp_ns=tick.timestamp_ns
            ))
            self.position = 100

        elif self.fast_ma < self.slow_ma * (1 - self.threshold) and self.position >= 0:
            # Sell signal
            self.send_order(Order(
                instrument_id=tick.instrument_id,
                client_order_id=self._next_order_id(),
                price=tick.price,
                qty=100.0,
                side="sell",
                order_type="limit",
                tif="GTC",
                timestamp_ns=tick.timestamp_ns
            ))
            self.position = -100

    def on_quote(self, quote: Quote):
        """Process quote data."""
        # Can use quotes for more sophisticated pricing
        pass

    def _next_order_id(self) -> int:
        """Generate unique order ID."""
        import time
        return int(time.time_ns())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--nexus", required=True, help="Nexus IPC endpoint")
    parser.add_argument("--bus-xsub", required=True, help="Bus XSUB IPC endpoint")
    parser.add_argument("--bus-xpub", required=True, help="Bus XPUB IPC endpoint")
    parser.add_argument("--config", default="config.json", help="Module config file")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    strategy = MomentumStrategy(
        nexus_endpoint=args.nexus,
        bus_xsub_endpoint=args.bus_xsub,
        bus_xpub_endpoint=args.bus_xpub,
        config_path=args.config,
    )
    strategy.run()


if __name__ == "__main__":
    main()
```

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
# tyche_cli/protocol.py

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
├── tyche-cli/
│   ├── pyproject.toml
│   └── tyche_cli/
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
│   │   └── test_protocol.py
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
