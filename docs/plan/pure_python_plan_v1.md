# Pure Python Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite TycheEngine from hybrid Rust/Python to pure-Python architecture with IPC-based microservices.

**Architecture:** Three packages: `tyche-core` (Nexus/Bus services), `tyche-cli` (client library for modules), `tyche-launcher` (process lifecycle manager). Communication via ZeroMQ IPC sockets with MessagePack serialization.

**Tech Stack:** Python 3.11+, ZeroMQ (pyzmq), MessagePack (msgpack), pytest, ruff

---

## Project State at Plan Time

The repository currently contains a hybrid Rust/Python implementation with PyO3 bindings. The new architecture will completely replace this with pure Python. The old `tyche/` directory, `tyche-core/` Rust crate, and existing tests will be removed and replaced with the new structure.

Key files to be removed:
- `tyche/` (old Python package)
- `tyche-core/` (Rust crate)
- `tests/` (old tests)
- `Cargo.toml`, `Cargo.lock`
- Old config files

---

## File Structure

```
TycheEngine/
├── tyche-core/                # Core service package (Nexus + Bus)
│   ├── pyproject.toml
│   └── tyche_core/
│       ├── __init__.py        # Version info
│       ├── __main__.py        # Entry point: python -m tyche_core
│       ├── nexus.py           # ROUTER socket, registry, lifecycle
│       ├── bus.py             # XPUB/XSUB proxy
│       └── config.py          # Core configuration loader
│
├── tyche-cli/                 # Client library for modules
│   ├── pyproject.toml
│   └── tyche_cli/
│       ├── __init__.py        # Public exports
│       ├── __main__.py        # Entry point for testing
│       ├── module.py          # Module base class
│       ├── types.py           # Tick, Quote, Trade, Bar, Order, etc.
│       ├── serialization.py   # MessagePack encode/decode
│       ├── transport.py       # ZMQ socket management
│       └── protocol.py        # Wire protocol constants
│
├── tyche-launcher/            # Module lifecycle manager
│   ├── pyproject.toml
│   └── tyche_launcher/
│       ├── __init__.py
│       ├── __main__.py        # Entry point: python -m tyche_launcher
│       ├── launcher.py        # Process management
│       ├── monitor.py         # Health checking
│       └── config.py          # Launcher config loader
│
├── tests/
│   ├── unit/
│   │   ├── test_types.py
│   │   ├── test_serialization.py
│   │   ├── test_protocol.py
│   │   └── test_config.py
│   └── integration/
│       ├── test_nexus_registration.py
│       ├── test_bus_pubsub.py
│       ├── test_module_base.py
│       └── test_launcher.py
│
├── strategies/
│   └── momentum.py            # Example strategy
│
├── config/
│   ├── core-config.json
│   ├── launcher-config.json
│   └── modules/
│       └── momentum-config.json
│
├── Makefile
└── README.md
```

---

## Task 1: Clean up old codebase

**Files:**
- Delete: `tyche/`
- Delete: `tyche-core/`
- Delete: `tests/`
- Delete: `Cargo.toml`, `Cargo.lock`
- Delete: Old config files in `config/`

- [ ] **Step 1: Remove old packages**

```bash
git rm -rf tyche/
git rm -rf tyche-core/
git rm -rf tests/
git rm -f Cargo.toml Cargo.lock
git rm -rf config/
```

- [ ] **Step 2: Commit cleanup**

```bash
git commit -m "chore: remove old Rust/Python hybrid codebase"
```

---

## Task 2: Create tyche-cli package skeleton

**Files:**
- Create: `tyche-cli/pyproject.toml`
- Create: `tyche-cli/tyche_cli/__init__.py`
- Create: `tyche-cli/tyche_cli/protocol.py`

- [ ] **Step 1: Write pyproject.toml**

```toml
# tyche-cli/pyproject.toml
[project]
name = "tyche-cli"
version = "1.0.0"
description = "TycheEngine client library for module development"
requires-python = ">=3.11"
dependencies = [
    "pyzmq>=25.0",
    "msgpack>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "ruff>=0.1.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Create protocol constants**

```python
# tyche-cli/tyche_cli/protocol.py
"""Wire protocol constants."""

# Message types
READY = b"READY"
ACK = b"ACK"
HB = b"HB"
CMD = b"CMD"
REPLY = b"REPLY"
DISCO = b"DISCO"

# Command types
CMD_START = b"START"
CMD_STOP = b"STOP"
CMD_RECONFIGURE = b"RECONFIGURE"
CMD_STATUS = b"STATUS"

# Status codes
STATUS_OK = b"OK"
STATUS_ERROR = b"ERROR"

# Protocol version
PROTOCOL_VERSION = 1

# Default timeouts
DEFAULT_HEARTBEAT_INTERVAL_MS = 1000
DEFAULT_REGISTRATION_TIMEOUT_MS = 5000
HEARTBEAT_TIMEOUT_MULTIPLIER = 3
```

- [ ] **Step 3: Create package init**

```python
# tyche-cli/tyche_cli/__init__.py
"""TycheEngine client library."""

__version__ = "1.0.0"

from .types import Tick, Quote, Trade, Bar, Order, OrderEvent, Ack, Position, Risk
from .module import Module
from .serialization import encode, decode

__all__ = [
    "Module",
    "Tick",
    "Quote",
    "Trade",
    "Bar",
    "Order",
    "OrderEvent",
    "Ack",
    "Position",
    "Risk",
    "encode",
    "decode",
]
```

- [ ] **Step 4: Commit package skeleton**

```bash
git add tyche-cli/
git commit -m "feat: create tyche-cli package skeleton"
```

---

## Task 3: Implement types module (TDD)

**Files:**
- Create: `tyche-cli/tyche_cli/types.py`
- Create: `tests/unit/test_types.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_types.py
import pytest
from tyche_cli.types import Tick, Quote, Trade, Bar, Order


def test_tick_creation():
    tick = Tick(
        instrument_id=12345,
        price=150.25,
        size=100.0,
        side="buy",
        timestamp_ns=1711632000000000000
    )
    assert tick.instrument_id == 12345
    assert tick.price == 150.25
    assert tick.side == "buy"


def test_tick_is_frozen():
    tick = Tick(
        instrument_id=12345,
        price=150.25,
        size=100.0,
        side="buy",
        timestamp_ns=1711632000000000000
    )
    with pytest.raises(AttributeError):
        tick.price = 200.0


def test_tick_is_hashable():
    tick = Tick(
        instrument_id=12345,
        price=150.25,
        size=100.0,
        side="buy",
        timestamp_ns=1711632000000000000
    )
    d = {tick: "value"}
    assert d[tick] == "value"


def test_quote_creation():
    quote = Quote(
        instrument_id=12345,
        bid_price=150.20,
        bid_size=500.0,
        ask_price=150.30,
        ask_size=300.0,
        timestamp_ns=1711632000000000000
    )
    assert quote.bid_price == 150.20
    assert quote.ask_price == 150.30


def test_order_creation():
    order = Order(
        instrument_id=12345,
        client_order_id=987654321,
        price=150.25,
        qty=100.0,
        side="buy",
        order_type="limit",
        tif="GTC",
        timestamp_ns=1711632000000000000
    )
    assert order.order_type == "limit"
    assert order.tif == "GTC"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd tyche-cli
python -m pytest ../tests/unit/test_types.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'tyche_cli.types'"

- [ ] **Step 3: Implement types module**

```python
# tyche-cli/tyche_cli/types.py
"""Market data and order types."""

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
    interval: str
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

- [ ] **Step 4: Run test to verify it passes**

```bash
cd tyche-cli
pip install -e .
python -m pytest ../tests/unit/test_types.py -v
```

Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add tyche-cli/tyche_cli/types.py tests/unit/test_types.py
git commit -m "feat: add tyche_cli types module"
```

---

## Task 4: Implement serialization module (TDD)

**Files:**
- Create: `tyche-cli/tyche_cli/serialization.py`
- Create: `tests/unit/test_serialization.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_serialization.py
import pytest
from tyche_cli.types import Tick, Quote, Order
from tyche_cli.serialization import encode, decode, TYPE_MAP


def test_encode_tick():
    tick = Tick(
        instrument_id=12345,
        price=150.25,
        size=100.0,
        side="buy",
        timestamp_ns=1711632000000000000
    )
    data = encode(tick)
    assert isinstance(data, bytes)
    # Should be valid msgpack
    import msgpack
    d = msgpack.unpackb(data)
    assert d["_type"] == "Tick"
    assert d["instrument_id"] == 12345
    assert d["price"] == 150.25


def test_decode_tick():
    import msgpack
    data = msgpack.packb({
        "_type": "Tick",
        "instrument_id": 12345,
        "price": 150.25,
        "size": 100.0,
        "side": "buy",
        "timestamp_ns": 1711632000000000000
    })
    obj = decode(data)
    assert isinstance(obj, Tick)
    assert obj.instrument_id == 12345
    assert obj.price == 150.25


def test_roundtrip_quote():
    quote = Quote(
        instrument_id=12345,
        bid_price=150.20,
        bid_size=500.0,
        ask_price=150.30,
        ask_size=300.0,
        timestamp_ns=1711632000000000000
    )
    data = encode(quote)
    decoded = decode(data)
    assert decoded == quote


def test_decode_unknown_type_raises():
    import msgpack
    data = msgpack.packb({
        "_type": "UnknownType",
        "field": "value"
    })
    with pytest.raises(ValueError, match="Unknown type"):
        decode(data)


def test_type_map_has_all_types():
    from tyche_cli.types import OrderEvent, Ack, Position, Risk, Trade, Bar
    assert "Tick" in TYPE_MAP
    assert "Quote" in TYPE_MAP
    assert "Trade" in TYPE_MAP
    assert "Bar" in TYPE_MAP
    assert "Order" in TYPE_MAP
    assert "OrderEvent" in TYPE_MAP
    assert "Ack" in TYPE_MAP
    assert "Position" in TYPE_MAP
    assert "Risk" in TYPE_MAP
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd tyche-cli
python -m pytest ../tests/unit/test_serialization.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'tyche_cli.serialization'"

- [ ] **Step 3: Implement serialization module**

```python
# tyche-cli/tyche_cli/serialization.py
"""MessagePack serialization/deserialization."""

import msgpack
from typing import Any, Dict, Type

from .types import Tick, Quote, Trade, Bar, Order, OrderEvent, Ack, Position, Risk


TYPE_MAP: Dict[str, Type] = {
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


def encode(obj: Any) -> bytes:
    """Encode a dataclass to MessagePack bytes.

    Args:
        obj: A dataclass instance with _type field.

    Returns:
        MessagePack-encoded bytes.
    """
    from dataclasses import asdict
    d = asdict(obj)
    d["_type"] = type(obj).__name__
    return msgpack.packb(d, use_bin_type=True)


def decode(data: bytes) -> Any:
    """Decode MessagePack bytes to a dataclass.

    Args:
        data: MessagePack-encoded bytes.

    Returns:
        A dataclass instance.

    Raises:
        ValueError: If the type is unknown.
    """
    d = msgpack.unpackb(data, raw=False)
    type_name = d.pop("_type", None)
    if type_name is None:
        raise ValueError("Missing '_type' field in message")
    cls = TYPE_MAP.get(type_name)
    if cls is None:
        raise ValueError(f"Unknown type: {type_name}")
    return cls(**d)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd tyche-cli
python -m pytest ../tests/unit/test_serialization.py -v
```

Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add tyche-cli/tyche_cli/serialization.py tests/unit/test_serialization.py
git commit -m "feat: add serialization module with MessagePack"
```

---

## Task 5: Create tyche-core package skeleton

**Files:**
- Create: `tyche-core/pyproject.toml`
- Create: `tyche-core/tyche_core/__init__.py`

- [ ] **Step 1: Write pyproject.toml**

```toml
# tyche-core/pyproject.toml
[project]
name = "tyche-core"
version = "1.0.0"
description = "TycheEngine core service (Nexus + Bus)"
requires-python = ">=3.11"
dependencies = [
    "pyzmq>=25.0",
    "msgpack>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "ruff>=0.1.0",
]

[project.scripts]
tyche-core = "tyche_core.__main__:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Create package init**

```python
# tyche-core/tyche_core/__init__.py
"""TycheEngine core service."""

__version__ = "1.0.0"
```

- [ ] **Step 3: Commit package skeleton**

```bash
git add tyche-core/
git commit -m "feat: create tyche-core package skeleton"
```

---

## Task 6: Implement Bus service (TDD)

**Files:**
- Create: `tyche-core/tyche_core/bus.py`
- Create: `tests/unit/test_bus.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_bus.py
import pytest
import zmq
import threading
import time


def test_bus_creation():
    from tyche_core.bus import Bus
    bus = Bus(
        xsub_endpoint="inproc://test_xsub",
        xpub_endpoint="inproc://test_xpub"
    )
    assert bus.xsub_endpoint == "inproc://test_xsub"
    assert bus.xpub_endpoint == "inproc://test_xpub"


def test_bus_starts_and_stops():
    from tyche_core.bus import Bus
    bus = Bus(
        xsub_endpoint="inproc://test_xsub2",
        xpub_endpoint="inproc://test_xpub2"
    )
    bus.start()
    time.sleep(0.1)
    bus.stop()
    assert not bus._running


def test_bus_forwards_messages():
    from tyche_core.bus import Bus
    xsub = "inproc://test_xsub3"
    xpub = "inproc://test_xpub3"

    bus = Bus(xsub_endpoint=xsub, xpub_endpoint=xpub)
    bus.start()
    time.sleep(0.1)

    ctx = zmq.Context()

    # Publisher connects to XSUB
    pub = ctx.socket(zmq.PUB)
    pub.connect(xsub)

    # Subscriber connects to XPUB
    sub = ctx.socket(zmq.SUB)
    sub.connect(xpub)
    sub.setsockopt(zmq.SUBSCRIBE, b"test")

    time.sleep(0.1)

    # Publish message
    pub.send_multipart([b"test.topic", b"payload"])

    # Receive message
    topic, payload = sub.recv_multipart()
    assert topic == b"test.topic"
    assert payload == b"payload"

    sub.close()
    pub.close()
    ctx.term()
    bus.stop()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd tyche-core
python -m pytest ../tests/unit/test_bus.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'tyche_core.bus'"

- [ ] **Step 3: Implement Bus module**

```python
# tyche-core/tyche_core/bus.py
"""Bus service - XPUB/XSUB proxy for data streaming."""

import zmq
import threading
import logging
from typing import Optional


class Bus:
    """XPUB/XSUB proxy for pub/sub messaging.

    Publishers connect to XSUB endpoint.
    Subscribers connect to XPUB endpoint.
    """

    def __init__(
        self,
        xsub_endpoint: str,
        xpub_endpoint: str,
        cpu_core: Optional[int] = None,
    ):
        self.xsub_endpoint = xsub_endpoint
        self.xpub_endpoint = xpub_endpoint
        self.cpu_core = cpu_core
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._logger = logging.getLogger("tyche.bus")

    def start(self) -> None:
        """Start the Bus proxy in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._logger.info(f"Bus started on {self.xsub_endpoint} / {self.xpub_endpoint}")

    def stop(self) -> None:
        """Stop the Bus proxy."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        self._logger.info("Bus stopped")

    def _run(self) -> None:
        """Run the ZMQ proxy."""
        # Set CPU affinity if specified
        if self.cpu_core is not None:
            self._set_cpu_affinity(self.cpu_core)

        ctx = zmq.Context()

        # XSUB socket - publishers connect here
        xsub = ctx.socket(zmq.XSUB)
        xsub.bind(self.xsub_endpoint)

        # XPUB socket - subscribers connect here
        xpub = ctx.socket(zmq.XPUB)
        xpub.bind(self.xpub_endpoint)

        # Set proxy to stop on context term
        try:
            zmq.proxy(xsub, xpub)
        except zmq.ContextTerminated:
            pass
        finally:
            xsub.close()
            xpub.close()
            ctx.term()

    def _set_cpu_affinity(self, core: int) -> None:
        """Set CPU affinity for this thread."""
        import sys
        if sys.platform == "linux":
            import os
            os.sched_setaffinity(0, {core})
        elif sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.SetThreadAffinityMask(-1, 1 << core)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd tyche-core
pip install -e .
python -m pytest ../tests/unit/test_bus.py -v
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add tyche-core/tyche_core/bus.py tests/unit/test_bus.py
git commit -m "feat: implement Bus XPUB/XSUB proxy service"
```

---

## Task 7: Implement Nexus service (TDD)

**Files:**
- Create: `tyche-core/tyche_core/nexus.py`
- Create: `tests/unit/test_nexus.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_nexus.py
import pytest
import zmq
import threading
import time
import json


def test_nexus_creation():
    from tyche_core.nexus import Nexus
    nexus = Nexus(endpoint="inproc://test_nexus")
    assert nexus.endpoint == "inproc://test_nexus"


def test_nexus_registers_module():
    from tyche_core.nexus import Nexus

    endpoint = "inproc://test_nexus2"
    nexus = Nexus(endpoint=endpoint)
    nexus.start()
    time.sleep(0.1)

    # Create module client
    ctx = zmq.Context()
    dealer = ctx.socket(zmq.DEALER)
    dealer.connect(endpoint)

    # Send READY
    dealer.send_multipart([
        b"READY",
        (1).to_bytes(4, "big"),  # protocol version
        json.dumps({
            "service_name": "test.module",
            "protocol_version": 1,
            "subscriptions": [],
            "heartbeat_interval_ms": 1000,
        }).encode()
    ])

    # Receive ACK
    frames = dealer.recv_multipart()
    assert frames[0] == b"ACK"
    assert len(frames) == 4  # ACK, correlation_id, assigned_id, heartbeat_interval

    dealer.close()
    ctx.term()
    nexus.stop()


def test_nexus_heartbeat_tracking():
    from tyche_core.nexus import Nexus

    endpoint = "inproc://test_nexus3"
    nexus = Nexus(endpoint=endpoint, heartbeat_timeout_ms=500)
    nexus.start()
    time.sleep(0.1)

    ctx = zmq.Context()
    dealer = ctx.socket(zmq.DEALER)
    dealer.connect(endpoint)

    # Register
    dealer.send_multipart([
        b"READY",
        (1).to_bytes(4, "big"),
        json.dumps({
            "service_name": "test.module2",
            "protocol_version": 1,
            "subscriptions": [],
            "heartbeat_interval_ms": 100,
        }).encode()
    ])
    frames = dealer.recv_multipart()
    correlation_id = int.from_bytes(frames[1], "big")

    # Wait for module to be tracked
    time.sleep(0.1)
    assert len(nexus._modules) == 1

    # Send heartbeat
    dealer.send_multipart([
        b"HB",
        (123456789).to_bytes(8, "big"),
        correlation_id.to_bytes(8, "big")
    ])

    dealer.close()
    ctx.term()
    nexus.stop()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd tyche-core
python -m pytest ../tests/unit/test_nexus.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'tyche_core.nexus'"

- [ ] **Step 3: Implement Nexus module**

```python
# tyche-core/tyche_core/nexus.py
"""Nexus service - module registration and lifecycle management."""

import zmq
import threading
import logging
import json
import time
from typing import Dict, Optional
from dataclasses import dataclass, field

from .protocol import READY, ACK, HB, CMD, REPLY, DISCO
from .protocol import CMD_START, CMD_STOP, CMD_RECONFIGURE, CMD_STATUS
from .protocol import STATUS_OK, STATUS_ERROR, PROTOCOL_VERSION


@dataclass
class ModuleDescriptor:
    """Registration info for a connected module."""
    service_name: str
    service_version: str
    protocol_version: int
    subscriptions: list
    heartbeat_interval_ms: int
    capabilities: list
    metadata: dict
    correlation_id: int
    assigned_id: str
    last_heartbeat_ns: int = 0
    status: str = "registered"  # registered, starting, running, stopping, stopped


class Nexus:
    """Nexus - ROUTER socket for module registration and control."""

    def __init__(
        self,
        endpoint: str,
        cpu_core: Optional[int] = None,
        heartbeat_interval_ms: int = 1000,
        heartbeat_timeout_ms: int = 3000,
    ):
        self.endpoint = endpoint
        self.cpu_core = cpu_core
        self.heartbeat_interval_ms = heartbeat_interval_ms
        self.heartbeat_timeout_ms = heartbeat_timeout_ms

        self._modules: Dict[str, ModuleDescriptor] = {}
        self._modules_by_correlation: Dict[int, str] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._ctx: Optional[zmq.Context] = None
        self._socket: Optional[zmq.Socket] = None
        self._logger = logging.getLogger("tyche.nexus")
        self._correlation_counter = 0

    def start(self) -> None:
        """Start the Nexus service."""
        self._running = True
        self._ctx = zmq.Context()
        self._socket = self._ctx.socket(zmq.ROUTER)
        self._socket.bind(self.endpoint)

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._logger.info(f"Nexus started on {self.endpoint}")

    def stop(self) -> None:
        """Stop the Nexus service."""
        self._running = False
        if self._ctx:
            self._ctx.term()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._logger.info("Nexus stopped")

    def _run(self) -> None:
        """Main run loop."""
        if self.cpu_core is not None:
            self._set_cpu_affinity(self.cpu_core)

        poller = zmq.Poller()
        poller.register(self._socket, zmq.POLLIN)

        last_check = time.time_ns()

        while self._running:
            events = dict(poller.poll(timeout=100))

            if self._socket in events:
                self._handle_message()

            # Check for heartbeat timeouts every 100ms
            now = time.time_ns()
            if now - last_check > 100_000_000:  # 100ms
                self._check_timeouts()
                last_check = now

    def _handle_message(self) -> None:
        """Handle incoming message."""
        frames = self._socket.recv_multipart()
        # ROUTER prepends identity
        identity = frames[0]
        msg_type = frames[1]

        if msg_type == READY:
            self._handle_ready(identity, frames[2:])
        elif msg_type == HB:
            self._handle_heartbeat(identity, frames[2:])
        elif msg_type == REPLY:
            self._handle_reply(identity, frames[2:])
        elif msg_type == DISCO:
            self._handle_disconnect(identity, frames[2:])
        else:
            self._logger.warning(f"Unknown message type: {msg_type}")

    def _handle_ready(self, identity: bytes, frames: list) -> None:
        """Handle module registration."""
        if len(frames) < 2:
            self._logger.error("Invalid READY message")
            return

        protocol_version = int.from_bytes(frames[0], "big")
        descriptor_json = frames[1].decode()

        try:
            descriptor_data = json.loads(descriptor_json)
        except json.JSONDecodeError as e:
            self._logger.error(f"Invalid descriptor JSON: {e}")
            return

        # Generate IDs
        self._correlation_counter += 1
        correlation_id = self._correlation_counter
        assigned_id = f"{descriptor_data['service_name']}.{correlation_id}"

        descriptor = ModuleDescriptor(
            service_name=descriptor_data["service_name"],
            service_version=descriptor_data.get("service_version", "1.0.0"),
            protocol_version=protocol_version,
            subscriptions=descriptor_data.get("subscriptions", []),
            heartbeat_interval_ms=descriptor_data.get(
                "heartbeat_interval_ms", self.heartbeat_interval_ms
            ),
            capabilities=descriptor_data.get("capabilities", []),
            metadata=descriptor_data.get("metadata", {}),
            correlation_id=correlation_id,
            assigned_id=assigned_id,
            last_heartbeat_ns=time.time_ns(),
        )

        with self._lock:
            self._modules[identity.hex()] = descriptor
            self._modules_by_correlation[correlation_id] = identity.hex()

        self._logger.info(f"Registered module: {assigned_id}")

        # Send ACK
        self._socket.send_multipart([
            identity,
            ACK,
            correlation_id.to_bytes(8, "big"),
            assigned_id.encode(),
            descriptor.heartbeat_interval_ms.to_bytes(4, "big"),
        ])

    def _handle_heartbeat(self, identity: bytes, frames: list) -> None:
        """Handle heartbeat."""
        if len(frames) < 2:
            return

        timestamp_ns = int.from_bytes(frames[0], "big")
        correlation_id = int.from_bytes(frames[1], "big")

        with self._lock:
            key = identity.hex()
            if key in self._modules:
                self._modules[key].last_heartbeat_ns = timestamp_ns

    def _handle_reply(self, identity: bytes, frames: list) -> None:
        """Handle command reply."""
        if len(frames) < 2:
            return

        correlation_id = int.from_bytes(frames[0], "big")
        status = frames[1]
        message = frames[2].decode() if len(frames) > 2 else ""

        self._logger.debug(f"Reply from {correlation_id}: {status} - {message}")

    def _handle_disconnect(self, identity: bytes, frames: list) -> None:
        """Handle disconnect."""
        key = identity.hex()
        with self._lock:
            if key in self._modules:
                descriptor = self._modules.pop(key)
                self._modules_by_correlation.pop(descriptor.correlation_id, None)
                self._logger.info(f"Module disconnected: {descriptor.assigned_id}")

    def _check_timeouts(self) -> None:
        """Check for heartbeat timeouts."""
        now = time.time_ns()
        timeout_ns = self.heartbeat_timeout_ms * 1_000_000

        with self._lock:
            dead_modules = []
            for key, descriptor in self._modules.items():
                if now - descriptor.last_heartbeat_ns > timeout_ns:
                    dead_modules.append(key)
                    self._logger.warning(f"Heartbeat timeout: {descriptor.assigned_id}")

            for key in dead_modules:
                descriptor = self._modules.pop(key)
                self._modules_by_correlation.pop(descriptor.correlation_id, None)

    def send_command(self, assigned_id: str, command: bytes, payload: bytes = b"") -> bool:
        """Send command to a module."""
        with self._lock:
            for key, descriptor in self._modules.items():
                if descriptor.assigned_id == assigned_id:
                    # Find identity
                    identity = bytes.fromhex(key)
                    self._socket.send_multipart([
                        identity,
                        CMD,
                        command,
                        payload,
                    ])
                    return True
        return False

    def broadcast_command(self, command: bytes, payload: bytes = b"") -> None:
        """Send command to all modules."""
        with self._lock:
            for key in self._modules:
                identity = bytes.fromhex(key)
                self._socket.send_multipart([
                    identity,
                    CMD,
                    command,
                    payload,
                ])

    def get_modules(self) -> Dict[str, ModuleDescriptor]:
        """Get copy of module registry."""
        with self._lock:
            return dict(self._modules)

    def _set_cpu_affinity(self, core: int) -> None:
        """Set CPU affinity."""
        import sys
        if sys.platform == "linux":
            import os
            os.sched_setaffinity(0, {core})
        elif sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.SetThreadAffinityMask(-1, 1 << core)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd tyche-core
python -m pytest ../tests/unit/test_nexus.py -v
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add tyche-core/tyche_core/nexus.py tests/unit/test_nexus.py
git commit -m "feat: implement Nexus registration and heartbeat service"
```

---

## Task 8: Add protocol constants to tyche-core

**Files:**
- Create: `tyche-core/tyche_core/protocol.py`

- [ ] **Step 1: Create protocol constants**

```python
# tyche-core/tyche_core/protocol.py
"""Wire protocol constants (mirrors tyche_cli.protocol)."""

# Message types
READY = b"READY"
ACK = b"ACK"
HB = b"HB"
CMD = b"CMD"
REPLY = b"REPLY"
DISCO = b"DISCO"

# Command types
CMD_START = b"START"
CMD_STOP = b"STOP"
CMD_RECONFIGURE = b"RECONFIGURE"
CMD_STATUS = b"STATUS"

# Status codes
STATUS_OK = b"OK"
STATUS_ERROR = b"ERROR"

# Protocol version
PROTOCOL_VERSION = 1

# Default timeouts
DEFAULT_HEARTBEAT_INTERVAL_MS = 1000
DEFAULT_REGISTRATION_TIMEOUT_MS = 5000
HEARTBEAT_TIMEOUT_MULTIPLIER = 3
```

- [ ] **Step 2: Commit**

```bash
git add tyche-core/tyche_core/protocol.py
git commit -m "feat: add protocol constants to tyche-core"
```

---

## Task 9: Implement tyche-core config loader

**Files:**
- Create: `tyche-core/tyche_core/config.py`
- Create: `tests/unit/test_core_config.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_core_config.py
import pytest
import json
import tempfile
import os


def test_load_core_config():
    from tyche_core.config import load_config

    config = {
        "nexus": {
            "endpoint": "ipc:///tmp/tyche/nexus.sock",
            "cpu_core": 0,
        },
        "bus": {
            "xsub_endpoint": "ipc:///tmp/tyche/bus_xsub.sock",
            "xpub_endpoint": "ipc:///tmp/tyche/bus_xpub.sock",
            "cpu_core": 1,
        },
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config, f)
        f.flush()
        loaded = load_config(f.name)
        os.unlink(f.name)

    assert loaded["nexus"]["endpoint"] == "ipc:///tmp/tyche/nexus.sock"
    assert loaded["bus"]["cpu_core"] == 1


def test_load_config_missing_file():
    from tyche_core.config import load_config

    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/config.json")


def test_load_config_defaults():
    from tyche_core.config import load_config_with_defaults

    config = {"nexus": {}}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config, f)
        f.flush()
        loaded = load_config_with_defaults(f.name)
        os.unlink(f.name)

    assert loaded["nexus"]["endpoint"] == "ipc:///tmp/tyche/nexus.sock"
    assert loaded["bus"]["xsub_endpoint"] == "ipc:///tmp/tyche/bus_xsub.sock"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd tyche-core
python -m pytest ../tests/unit/test_core_config.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'tyche_core.config'"

- [ ] **Step 3: Implement config module**

```python
# tyche-core/tyche_core/config.py
"""Configuration loading for tyche-core."""

import json
from typing import Dict, Any


DEFAULT_CONFIG = {
    "nexus": {
        "endpoint": "ipc:///tmp/tyche/nexus.sock",
        "cpu_core": 0,
        "heartbeat_interval_ms": 1000,
        "heartbeat_timeout_ms": 3000,
    },
    "bus": {
        "xsub_endpoint": "ipc:///tmp/tyche/bus_xsub.sock",
        "xpub_endpoint": "ipc:///tmp/tyche/bus_xpub.sock",
        "cpu_core": 1,
    },
    "launcher": {
        "enabled": False,
        "config_path": "launcher-config.json",
    },
}


def load_config(path: str) -> Dict[str, Any]:
    """Load configuration from JSON file.

    Args:
        path: Path to config file.

    Returns:
        Configuration dictionary.

    Raises:
        FileNotFoundError: If file doesn't exist.
        json.JSONDecodeError: If file is invalid JSON.
    """
    with open(path) as f:
        return json.load(f)


def load_config_with_defaults(path: str) -> Dict[str, Any]:
    """Load configuration with defaults for missing values."""
    config = load_config(path)
    merged = _deep_merge(DEFAULT_CONFIG, config)
    return merged


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd tyche-core
python -m pytest ../tests/unit/test_core_config.py -v
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add tyche-core/tyche_core/config.py tests/unit/test_core_config.py
git commit -m "feat: add tyche-core config loader with defaults"
```

---

## Task 10: Implement tyche-core main entry point

**Files:**
- Create: `tyche-core/tyche_core/__main__.py`
- Create: `config/core-config.json`

- [ ] **Step 1: Write main entry point**

```python
# tyche-core/tyche_core/__main__.py
"""Entry point for tyche-core service."""

import argparse
import logging
import signal
import sys
import os
from pathlib import Path

from .nexus import Nexus
from .bus import Bus
from .config import load_config_with_defaults


def setup_logging(level: str = "INFO") -> None:
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def ensure_socket_dir(endpoint: str) -> None:
    """Create socket directory if needed."""
    if endpoint.startswith("ipc://"):
        path = endpoint[6:]  # Remove ipc://
        dir_path = os.path.dirname(path)
        if dir_path:
            Path(dir_path).mkdir(parents=True, exist_ok=True)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="TycheEngine Core Service")
    parser.add_argument(
        "--config",
        default="config/core-config.json",
        help="Path to configuration file",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    args = parser.parse_args()

    setup_logging(args.log_level)
    logger = logging.getLogger("tyche.core")

    # Load config
    try:
        config = load_config_with_defaults(args.config)
    except FileNotFoundError:
        logger.error(f"Config file not found: {args.config}")
        return 1

    # Ensure socket directories exist
    ensure_socket_dir(config["nexus"]["endpoint"])
    ensure_socket_dir(config["bus"]["xsub_endpoint"])
    ensure_socket_dir(config["bus"]["xpub_endpoint"])

    # Create services
    nexus = Nexus(
        endpoint=config["nexus"]["endpoint"],
        cpu_core=config["nexus"].get("cpu_core"),
        heartbeat_interval_ms=config["nexus"]["heartbeat_interval_ms"],
        heartbeat_timeout_ms=config["nexus"]["heartbeat_timeout_ms"],
    )

    bus = Bus(
        xsub_endpoint=config["bus"]["xsub_endpoint"],
        xpub_endpoint=config["bus"]["xpub_endpoint"],
        cpu_core=config["bus"].get("cpu_core"),
    )

    # Setup signal handlers
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        nexus.stop()
        bus.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start services
    try:
        bus.start()
        nexus.start()
        logger.info("TycheEngine Core started")

        # Keep main thread alive
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        nexus.stop()
        bus.stop()
        logger.info("TycheEngine Core stopped")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Create default config**

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
    "cpu_core": 1
  },
  "launcher": {
    "enabled": false,
    "config_path": "launcher-config.json"
  }
}
```

- [ ] **Step 3: Test the entry point**

```bash
cd tyche-core
pip install -e .

# Test help
python -m tyche_core --help

# Test config loading (will fail with socket error if run without args, that's expected)
python -c "from tyche_core.__main__ import main; import sys; sys.argv = ['tyche-core', '--help']; main()"
```

Expected: Help message displayed successfully

- [ ] **Step 4: Commit**

```bash
git add tyche-core/tyche_core/__main__.py config/core-config.json
git commit -m "feat: add tyche-core main entry point"
```

---

## Task 11: Implement Module base class (TDD)

**Files:**
- Create: `tyche-cli/tyche_cli/module.py`
- Create: `tests/unit/test_module.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_module.py
import pytest
import zmq
import threading
import time
import json


def test_module_creation():
    from tyche_cli.module import Module

    class TestModule(Module):
        service_name = "test.module"

        def on_init(self):
            pass

        def on_start(self):
            pass

        def on_stop(self):
            pass

    module = TestModule(
        nexus_endpoint="inproc://test_nexus",
        bus_xsub_endpoint="inproc://test_xsub",
        bus_xpub_endpoint="inproc://test_xpub",
    )
    assert module.service_name == "test.module"


def test_module_loads_config():
    from tyche_cli.module import Module
    import tempfile
    import os

    config = {"strategy": {"name": "test"}}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config, f)
        config_path = f.name

    try:
        class TestModule(Module):
            service_name = "test.module"

            def on_init(self):
                pass

            def on_start(self):
                pass

            def on_stop(self):
                pass

        module = TestModule(
            nexus_endpoint="inproc://test_nexus2",
            bus_xsub_endpoint="inproc://test_xsub2",
            bus_xpub_endpoint="inproc://test_xpub2",
            config_path=config_path,
        )
        module._load_config()
        assert module._config["strategy"]["name"] == "test"
    finally:
        os.unlink(config_path)


def test_module_encode_decode():
    from tyche_cli.module import Module
    from tyche_cli.types import Tick

    class TestModule(Module):
        service_name = "test.module"

        def on_init(self):
            pass

        def on_start(self):
            pass

        def on_stop(self):
            pass

    module = TestModule(
        nexus_endpoint="inproc://test_nexus3",
        bus_xsub_endpoint="inproc://test_xsub3",
        bus_xpub_endpoint="inproc://test_xpub3",
    )

    tick = Tick(
        instrument_id=12345,
        price=150.25,
        size=100.0,
        side="buy",
        timestamp_ns=1711632000000000000
    )

    data = module._encode(tick)
    decoded = module._decode(data)
    assert decoded == tick
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd tyche-cli
python -m pytest ../tests/unit/test_module.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'tyche_cli.module'"

- [ ] **Step 3: Implement Module base class**

```python
# tyche-cli/tyche_cli/module.py
"""Module base class for TycheEngine strategies."""

import zmq
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Callable

from .types import Tick, Quote, Trade, Bar, Order, OrderEvent
from .serialization import encode, decode
from .protocol import (
    READY, ACK, HB, CMD, REPLY, DISCO,
    CMD_START, CMD_STOP, CMD_RECONFIGURE, CMD_STATUS,
    STATUS_OK, STATUS_ERROR, PROTOCOL_VERSION,
    DEFAULT_HEARTBEAT_INTERVAL_MS,
)


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
        self._assigned_id: str = ""
        self._running = False
        self._initialized = False
        self._ctx = zmq.Context()
        self._nexus_socket: Optional[zmq.Socket] = None
        self._pub_socket: Optional[zmq.Socket] = None
        self._sub_socket: Optional[zmq.Socket] = None
        self._poller = zmq.Poller()

        self._logger = logging.getLogger(self.service_name)
        self._heartbeat_interval_ms = DEFAULT_HEARTBEAT_INTERVAL_MS
        self._last_heartbeat_send = 0

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
                self._logger.info(f"Loaded config from {self.config_path}")

    def _encode(self, obj: Any) -> bytes:
        """Encode object to MessagePack."""
        return encode(obj)

    def _decode(self, data: bytes) -> Any:
        """Decode MessagePack to object."""
        return decode(data)

    def _register(self) -> bool:
        """Register with Nexus."""
        self._nexus_socket.send_multipart([
            READY,
            PROTOCOL_VERSION.to_bytes(4, "big"),
            json.dumps({
                "service_name": self.service_name,
                "service_version": self.service_version,
                "protocol_version": PROTOCOL_VERSION,
                "subscriptions": [],
                "heartbeat_interval_ms": self._heartbeat_interval_ms,
                "capabilities": ["publish", "subscribe"],
                "metadata": {},
            }).encode(),
        ])

        # Wait for ACK
        if self._nexus_socket.poll(timeout=5000):
            frames = self._nexus_socket.recv_multipart()
            if frames[0] == ACK:
                self._correlation_id = int.from_bytes(frames[1], "big")
                self._assigned_id = frames[2].decode()
                self._heartbeat_interval_ms = int.from_bytes(frames[3], "big")
                self._logger.info(f"Registered with Nexus as {self._assigned_id}")
                return True

        self._logger.error("Failed to register with Nexus")
        return False

    def _send_heartbeat(self) -> None:
        """Send heartbeat to Nexus."""
        now = time.time_ns()
        self._nexus_socket.send_multipart([
            HB,
            now.to_bytes(8, "big"),
            self._correlation_id.to_bytes(8, "big"),
        ])

    def _handle_command(self, cmd_type: bytes, payload: bytes) -> None:
        """Handle command from Nexus."""
        if cmd_type == CMD_START:
            self._logger.info("Received START command")
            self.on_start()
            self._send_reply(STATUS_OK)
        elif cmd_type == CMD_STOP:
            self._logger.info("Received STOP command")
            self._send_reply(STATUS_OK)
            self._running = False
        elif cmd_type == CMD_RECONFIGURE:
            self._logger.info("Received RECONFIGURE command")
            try:
                new_config = json.loads(payload)
                self.on_reconfigure(new_config)
                self._send_reply(STATUS_OK)
            except json.JSONDecodeError as e:
                self._send_reply(STATUS_ERROR, str(e).encode())
        elif cmd_type == CMD_STATUS:
            self.on_status()
            self._send_reply(STATUS_OK)

    def _send_reply(self, status: bytes, message: bytes = b"") -> None:
        """Send reply to Nexus."""
        frames = [REPLY, self._correlation_id.to_bytes(8, "big"), status]
        if message:
            frames.append(message)
        self._nexus_socket.send_multipart(frames)

    def _handle_nexus_message(self, frames: list) -> None:
        """Handle message from Nexus."""
        msg_type = frames[0]

        if msg_type == CMD:
            cmd_type = frames[1] if len(frames) > 1 else b""
            payload = frames[2] if len(frames) > 2 else b""
            self._handle_command(cmd_type, payload)

    def _dispatch(self, topic: bytes, payload: bytes) -> None:
        """Dispatch incoming Bus message to appropriate handler."""
        try:
            obj = self._decode(payload)
            handler = self._handlers.get(type(obj).__name__)
            if handler:
                handler(obj)
        except Exception as e:
            self._logger.error(f"Error dispatching message: {e}")

    def subscribe(self, topic_pattern: str) -> None:
        """Subscribe to topic pattern on Bus."""
        if self._sub_socket:
            self._sub_socket.setsockopt(zmq.SUBSCRIBE, topic_pattern.encode())
            self._logger.debug(f"Subscribed to: {topic_pattern}")

    def publish(self, topic: str, obj: Any) -> None:
        """Publish object to Bus topic."""
        if self._pub_socket:
            self._pub_socket.send_multipart([
                topic.encode(),
                self._encode(obj),
            ])

    def send_order(self, order: Order) -> None:
        """Send order via internal topic."""
        self.publish("INTERNAL.OMS.ORDER", order)

    def run(self) -> None:
        """Main run loop."""
        self._load_config()

        # Create and connect sockets
        self._nexus_socket = self._ctx.socket(zmq.DEALER)
        self._nexus_socket.connect(self.nexus_endpoint)

        self._pub_socket = self._ctx.socket(zmq.PUB)
        self._pub_socket.connect(self.bus_xsub_endpoint)

        self._sub_socket = self._ctx.socket(zmq.SUB)
        self._sub_socket.connect(self.bus_xpub_endpoint)

        # Register with Nexus
        if not self._register():
            self._cleanup()
            return

        self._initialized = True
        self.on_init()

        self._running = True
        self._poller.register(self._nexus_socket, zmq.POLLIN)
        self._poller.register(self._sub_socket, zmq.POLLIN)

        self._logger.info("Module running")

        heartbeat_interval_ns = self._heartbeat_interval_ms * 1_000_000

        try:
            while self._running:
                events = dict(self._poller.poll(timeout=100))

                # Handle Nexus messages
                if self._nexus_socket in events:
                    frames = self._nexus_socket.recv_multipart()
                    self._handle_nexus_message(frames)

                # Handle Bus messages
                if self._sub_socket in events:
                    topic, payload = self._sub_socket.recv_multipart()
                    self._dispatch(topic, payload)

                # Send heartbeat
                now = time.time_ns()
                if now - self._last_heartbeat_send > heartbeat_interval_ns:
                    self._send_heartbeat()
                    self._last_heartbeat_send = now

        except KeyboardInterrupt:
            self._logger.info("Interrupted by user")
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        """Clean up resources."""
        self._logger.info("Cleaning up...")

        if self._nexus_socket:
            # Send disconnect
            try:
                self._nexus_socket.send_multipart([
                    DISCO,
                    self._correlation_id.to_bytes(8, "big"),
                ])
            except:
                pass
            self._nexus_socket.close()

        if self._pub_socket:
            self._pub_socket.close()

        if self._sub_socket:
            self._sub_socket.close()

        self._ctx.term()
        self._logger.info("Module stopped")

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
        self._logger.info("Configuration updated")

    def on_status(self) -> None:
        """Called when Nexus sends STATUS command."""
        pass

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

    def on_order_event(self, event: OrderEvent) -> None:
        """Override to handle OrderEvent messages."""
        pass
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd tyche-cli
python -m pytest ../tests/unit/test_module.py -v
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add tyche-cli/tyche_cli/module.py tests/unit/test_module.py
git commit -m "feat: implement Module base class with full lifecycle"
```

---

## Task 12: Create example strategy

**Files:**
- Create: `strategies/momentum.py`
- Create: `config/modules/momentum-config.json`

- [ ] **Step 1: Write example strategy**

```python
#!/usr/bin/env python3
"""Momentum strategy example."""

import argparse
import logging
import time

from tyche_cli import Module, Tick, Quote, Order


class MomentumStrategy(Module):
    """Simple momentum strategy using moving average crossover."""

    service_name = "strategy.momentum"
    service_version = "1.0.0"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.fast_ma = 0.0
        self.slow_ma = 0.0
        self.position = 0
        self._order_id_counter = 0

    def on_init(self):
        """Called after registration."""
        # Subscribe to market data
        self.subscribe("EQUITY.NYSE.*.Tick")
        self.subscribe("EQUITY.NYSE.*.Quote")

        # Load strategy config
        cfg = self._config.get("strategy", {})
        self.lookback = cfg.get("lookback_period", 20)
        self.threshold = cfg.get("threshold", 0.001)

        self._logger.info(f"Momentum strategy initialized: lookback={self.lookback}")

    def on_start(self):
        """Called on START command."""
        self._logger.info("Strategy started")

    def on_stop(self):
        """Called on STOP command."""
        self._logger.info("Strategy stopped")

    def on_tick(self, tick: Tick):
        """Process tick data."""
        # Update moving averages using EMA
        alpha_fast = 2.0 / (self.lookback / 2 + 1)
        alpha_slow = 2.0 / (self.lookback + 1)

        self.fast_ma = alpha_fast * tick.price + (1 - alpha_fast) * self.fast_ma
        self.slow_ma = alpha_slow * tick.price + (1 - alpha_slow) * self.slow_ma

        # Skip until we have valid averages
        if self.fast_ma == 0 or self.slow_ma == 0:
            return

        # Trading logic
        if self.fast_ma > self.slow_ma * (1 + self.threshold) and self.position <= 0:
            # Buy signal
            self._place_order(tick, "buy", 100.0)
            self.position = 100

        elif self.fast_ma < self.slow_ma * (1 - self.threshold) and self.position >= 0:
            # Sell signal
            self._place_order(tick, "sell", 100.0)
            self.position = -100

    def on_quote(self, quote: Quote):
        """Process quote data."""
        # Can use quotes for more sophisticated pricing
        pass

    def _place_order(self, tick: Tick, side: str, qty: float):
        """Place an order."""
        self._order_id_counter += 1
        order = Order(
            instrument_id=tick.instrument_id,
            client_order_id=self._order_id_counter,
            price=tick.price,
            qty=qty,
            side=side,
            order_type="limit",
            tif="GTC",
            timestamp_ns=tick.timestamp_ns,
        )
        self.send_order(order)
        self._logger.info(f"Placed {side} order for {qty} @ {tick.price}")


def main():
    parser = argparse.ArgumentParser(description="Momentum Strategy")
    parser.add_argument("--nexus", required=True, help="Nexus IPC endpoint")
    parser.add_argument("--bus-xsub", required=True, help="Bus XSUB IPC endpoint")
    parser.add_argument("--bus-xpub", required=True, help="Bus XPUB IPC endpoint")
    parser.add_argument("--config", default="config.json", help="Module config file")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

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

- [ ] **Step 2: Create strategy config**

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

- [ ] **Step 3: Commit**

```bash
git add strategies/momentum.py config/modules/momentum-config.json
git commit -m "feat: add example momentum strategy"
```

---

## Task 13: Integration test - Nexus registration

**Files:**
- Create: `tests/integration/test_nexus_registration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/integration/test_nexus_registration.py
"""Integration test for Nexus module registration."""

import pytest
import zmq
import threading
import time
import json
import tempfile
import os

from tyche_core.nexus import Nexus
from tyche_core.bus import Bus
from tyche_cli.module import Module


class TestModule(Module):
    """Test module for integration tests."""

    service_name = "test.integration"
    service_version = "1.0.0"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.init_called = False
        self.start_called = False
        self.stop_called = False

    def on_init(self):
        self.init_called = True

    def on_start(self):
        self.start_called = True

    def on_stop(self):
        self.stop_called = True


@pytest.fixture
def endpoints():
    """Generate unique endpoints for each test."""
    import uuid
    uid = uuid.uuid4().hex[:8]
    return {
        "nexus": f"inproc://test_nexus_{uid}",
        "xsub": f"inproc://test_xsub_{uid}",
        "xpub": f"inproc://test_xpub_{uid}",
    }


@pytest.fixture
def core_services(endpoints):
    """Start Nexus and Bus services."""
    nexus = Nexus(endpoint=endpoints["nexus"])
    bus = Bus(
        xsub_endpoint=endpoints["xsub"],
        xpub_endpoint=endpoints["xpub"],
    )

    bus.start()
    nexus.start()
    time.sleep(0.1)

    yield nexus, bus

    nexus.stop()
    bus.stop()


def test_module_registers_with_nexus(endpoints, core_services):
    """Test that a module can register with Nexus."""
    nexus, bus = core_services

    module = TestModule(
        nexus_endpoint=endpoints["nexus"],
        bus_xsub_endpoint=endpoints["xsub"],
        bus_xpub_endpoint=endpoints["xpub"],
    )

    # Run module in background thread
    thread = threading.Thread(target=module.run, daemon=True)
    thread.start()

    # Wait for registration
    time.sleep(0.3)

    # Check that module is registered
    modules = nexus.get_modules()
    assert len(modules) == 1

    module_key = list(modules.keys())[0]
    assert modules[module_key].service_name == "test.integration"


def test_module_receives_start_command(endpoints, core_services):
    """Test that module receives START command."""
    nexus, bus = core_services

    module = TestModule(
        nexus_endpoint=endpoints["nexus"],
        bus_xsub_endpoint=endpoints["xsub"],
        bus_xpub_endpoint=endpoints["xpub"],
    )

    thread = threading.Thread(target=module.run, daemon=True)
    thread.start()

    time.sleep(0.3)

    # Get assigned ID and send START
    modules = nexus.get_modules()
    assigned_id = list(modules.values())[0].assigned_id

    from tyche_core.protocol import CMD_START
    nexus.send_command(assigned_id, CMD_START)

    time.sleep(0.2)

    assert module.start_called


def test_module_receives_stop_command(endpoints, core_services):
    """Test that module receives STOP command and shuts down."""
    nexus, bus = core_services

    module = TestModule(
        nexus_endpoint=endpoints["nexus"],
        bus_xsub_endpoint=endpoints["xsub"],
        bus_xpub_endpoint=endpoints["xpub"],
    )

    thread = threading.Thread(target=module.run, daemon=True)
    thread.start()

    time.sleep(0.3)

    modules = nexus.get_modules()
    assigned_id = list(modules.values())[0].assigned_id

    from tyche_core.protocol import CMD_STOP
    nexus.send_command(assigned_id, CMD_STOP)

    time.sleep(0.3)

    assert module.stop_called
```

- [ ] **Step 2: Run integration test**

```bash
cd tyche-core && pip install -e .
cd ../tyche-cli && pip install -e .
cd ..
python -m pytest tests/integration/test_nexus_registration.py -v
```

Expected: 3 PASSED

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_nexus_registration.py
git commit -m "test: add Nexus registration integration tests"
```

---

## Task 14: Integration test - Bus pub/sub

**Files:**
- Create: `tests/integration/test_bus_pubsub.py`

- [ ] **Step 1: Write integration test**

```python
# tests/integration/test_bus_pubsub.py
"""Integration test for Bus pub/sub."""

import pytest
import zmq
import threading
import time

from tyche_core.bus import Bus
from tyche_cli.types import Tick
from tyche_cli.serialization import encode


@pytest.fixture
def endpoints():
    """Generate unique endpoints for each test."""
    import uuid
    uid = uuid.uuid4().hex[:8]
    return {
        "xsub": f"inproc://test_xsub_{uid}",
        "xpub": f"inproc://test_xpub_{uid}",
    }


@pytest.fixture
def bus_service(endpoints):
    """Start Bus service."""
    bus = Bus(
        xsub_endpoint=endpoints["xsub"],
        xpub_endpoint=endpoints["xpub"],
    )
    bus.start()
    time.sleep(0.1)

    yield bus

    bus.stop()


def test_pub_sub_message_flow(endpoints, bus_service):
    """Test that messages flow from pub to sub through Bus."""
    ctx = zmq.Context()

    # Create publisher
    pub = ctx.socket(zmq.PUB)
    pub.connect(endpoints["xsub"])

    # Create subscriber
    sub = ctx.socket(zmq.SUB)
    sub.connect(endpoints["xpub"])
    sub.setsockopt(zmq.SUBSCRIBE, b"TEST")

    time.sleep(0.2)

    # Publish message
    tick = Tick(
        instrument_id=12345,
        price=150.25,
        size=100.0,
        side="buy",
        timestamp_ns=1711632000000000000,
    )

    pub.send_multipart([b"TEST.TOPIC", encode(tick)])

    # Receive message
    topic, payload = sub.recv_multipart()
    assert topic == b"TEST.TOPIC"

    from tyche_cli.serialization import decode
    decoded = decode(payload)
    assert decoded.instrument_id == 12345
    assert decoded.price == 150.25

    pub.close()
    sub.close()
    ctx.term()


def test_topic_filtering(endpoints, bus_service):
    """Test that subscribers only receive matching topics."""
    ctx = zmq.Context()

    pub = ctx.socket(zmq.PUB)
    pub.connect(endpoints["xsub"])

    # Subscriber for AAPL only
    sub = ctx.socket(zmq.SUB)
    sub.connect(endpoints["xpub"])
    sub.setsockopt(zmq.SUBSCRIBE, b"EQUITY.NYSE.AAPL")

    time.sleep(0.2)

    # Publish AAPL tick
    pub.send_multipart([b"EQUITY.NYSE.AAPL.Tick", b"aapl_data"])

    # Publish MSFT tick
    pub.send_multipart([b"EQUITY.NYSE.MSFT.Tick", b"msft_data"])

    # Only AAPL should be received
    topic, payload = sub.recv_multipart()
    assert topic == b"EQUITY.NYSE.AAPL.Tick"
    assert payload == b"aapl_data"

    # Check no more messages (with timeout)
    sub.setsockopt(zmq.RCVTIMEO, 100)
    with pytest.raises(zmq.Again):
        sub.recv_multipart()

    pub.close()
    sub.close()
    ctx.term()
```

- [ ] **Step 2: Run integration test**

```bash
python -m pytest tests/integration/test_bus_pubsub.py -v
```

Expected: 2 PASSED

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_bus_pubsub.py
git commit -m "test: add Bus pub/sub integration tests"
```

---

## Task 15: Create Makefile

**Files:**
- Create: `Makefile`

- [ ] **Step 1: Create Makefile**

```makefile
.PHONY: all build install test lint clean

all: build

build: build-core build-cli

build-core:
	pip install -e tyche-core/

build-cli:
	pip install -e tyche-cli/

install: build

test: test-unit test-integration

test-unit:
	python -m pytest tests/unit/ -v

test-integration:
	python -m pytest tests/integration/ -v

lint:
	ruff check tyche-core/ tyche-cli/ tests/ strategies/

lint-fix:
	ruff check --fix tyche-core/ tyche-cli/ tests/ strategies/

format:
	ruff format tyche-core/ tyche-cli/ tests/ strategies/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf tyche-core/*.egg-info tyche-cli/*.egg-info
	rm -rf .pytest_cache

run-core:
	python -m tyche_core --config config/core-config.json

run-momentum:
	python strategies/momentum.py \
		--nexus ipc:///tmp/tyche/nexus.sock \
		--bus-xsub ipc:///tmp/tyche/bus_xsub.sock \
		--bus-xpub ipc:///tmp/tyche/bus_xpub.sock \
		--config config/modules/momentum-config.json
```

- [ ] **Step 2: Commit**

```bash
git add Makefile
git commit -m "chore: add Makefile with common tasks"
```

---

## Task 16: Final verification

- [ ] **Step 1: Run all unit tests**

```bash
python -m pytest tests/unit/ -v
```

Expected: All tests pass

- [ ] **Step 2: Run all integration tests**

```bash
python -m pytest tests/integration/ -v
```

Expected: All tests pass

- [ ] **Step 3: Run linting**

```bash
make lint
```

Expected: No errors (or only minor warnings)

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: address linting issues" || echo "No fixes needed"
```

---

## Summary

This plan implements the complete pure-Python architecture for TycheEngine:

1. **tyche-core**: Nexus (ROUTER) + Bus (XPUB/XSUB) services
2. **tyche-cli**: Client library with types, serialization, and Module base class
3. **IPC transport**: ZeroMQ over Unix domain sockets / named pipes
4. **Protocol**: Binary wire protocol with MessagePack serialization
5. **Example**: Momentum strategy demonstrating the API
6. **Tests**: Unit and integration tests for all major components

After completing all tasks:
- `tyche-core` can be installed and run as a service
- `tyche-cli` provides the base class for writing modules
- Modules are completely separate processes with no shared code
- The architecture supports future evolution to native modules
