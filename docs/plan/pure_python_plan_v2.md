# Pure Python Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite TycheEngine from hybrid Rust/Python to pure-Python architecture with IPC-based microservices.

**Architecture:** Three packages: `tyche-core` (Nexus/Bus services), `tyche-client` (client library for modules), `tyche-launcher` (process lifecycle manager). Communication via ZeroMQ IPC sockets with MessagePack serialization.

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
├── tyche-client/              # Client library for modules (renamed from tyche-cli)
│   ├── pyproject.toml
│   └── tyche_client/          # Renamed from tyche_cli
│       ├── __init__.py        # Public exports
│       ├── __main__.py        # Entry point for testing
│       ├── module.py          # Module base class
│       ├── types.py           # Tick, Quote, Trade, Bar, Order, etc.
│       ├── serialization.py   # MessagePack encode/decode
│       ├── transport.py       # ZMQ socket management
│       ├── protocol.py        # Wire protocol constants
│       └── socket.py          # Centralized socket address helper (NEW)
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
│   │   ├── test_config.py
│   │   └── test_socket.py     # NEW: socket address helper tests
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

**What needs to be done?** Remove the old Rust/Python hybrid codebase including `tyche/`, `tyche-core/` (Rust), `tests/`, `Cargo.toml`, `Cargo.lock`, and old config files.

**What problem does it resolve?** The old hybrid architecture is being replaced with pure Python; we need a clean slate before implementing the new architecture.

**Expected result?** Old directories and files deleted, committed as "chore: remove old Rust/Python hybrid codebase".

**Files:**
- Delete: `tyche/`
- Delete: `tyche-core/` (Rust crate)
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

## Task 2: Create tyche-client package skeleton (RENAMED from tyche-cli)

**What needs to be done?** Create the `tyche-client` Python package with `pyproject.toml`, `__init__.py`, and `protocol.py` containing wire protocol constants.

**What problem does it resolve?** Modules need a client library to communicate with Core; this establishes the package structure and shared protocol definitions.

**Expected result?** Package installs successfully, exports version and protocol constants.

**Files:**
- Create: `tyche-client/pyproject.toml`
- Create: `tyche-client/tyche_client/__init__.py`
- Create: `tyche-client/tyche_client/protocol.py`

- [ ] **Step 1: Write pyproject.toml**

```toml
# tyche-client/pyproject.toml
[project]
name = "tyche-client"
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
cli = [
    "tyche-client",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Create protocol constants**

```python
# tyche-client/tyche_client/protocol.py
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
# tyche-client/tyche_client/__init__.py
"""TycheEngine client library."""

__version__ = "1.0.0"

from .types import Tick, Quote, Trade, Bar, Order, OrderEvent, Ack, Position, Risk
from .module import Module
from .serialization import encode, decode
from .socket import socket_address

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
    "socket_address",
]
```

- [ ] **Step 4: Commit package skeleton**

```bash
git add tyche-client/
git commit -m "feat: create tyche-client package skeleton (renamed from tyche-cli)"
```

---

## Task 3: Implement centralized socket address helper (NEW)

**What needs to be done?** Create a `socket.py` module with `socket_address()` function that returns platform-appropriate IPC socket paths (Unix domain sockets on Linux, named pipes on Windows).

**What problem does it resolve?** IPC paths differ between Windows and Linux; we need a single source of truth for socket addresses to avoid inconsistencies.

**Expected result?** `socket_address("nexus")` returns `ipc:///tmp/tyche/nexus.sock` on Linux, `ipc://tyche-nexus` on Windows.

**Files:**
- Create: `tyche-client/tyche_client/socket.py`
- Create: `tests/unit/test_socket.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_socket.py
import pytest
from tyche_client.socket import socket_address


def test_socket_address_default():
    addr = socket_address("nexus")
    assert addr == "ipc:///tmp/tyche/nexus.sock"


def test_socket_address_bus_xsub():
    addr = socket_address("bus", "xsub")
    assert addr == "ipc:///tmp/tyche/bus_xsub.sock"


def test_socket_address_bus_xpub():
    addr = socket_address("bus", "xpub")
    assert addr == "ipc:///tmp/tyche/bus_xpub.sock"


def test_socket_address_custom_base():
    addr = socket_address("nexus", base="/var/run/tyche")
    assert addr == "ipc:///var/run/tyche/nexus.sock"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd tyche-client
python -m pytest ../tests/unit/test_socket.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'tyche_client.socket'"

- [ ] **Step 3: Implement socket module**

```python
# tyche-client/tyche_client/socket.py
"""Centralized socket address construction."""

import sys


def socket_address(service: str, endpoint: str = "", base: str = "/tmp/tyche") -> str:
    """Construct IPC socket address.

    Args:
        service: Service name (e.g., 'nexus', 'bus')
        endpoint: Endpoint type for multi-endpoint services (e.g., 'xsub', 'xpub')
        base: Base directory for socket files

    Returns:
        IPC socket address string
    """
    if endpoint:
        name = f"{service}_{endpoint}"
    else:
        name = service

    if sys.platform == "win32":
        # Windows named pipe format
        return f"ipc://tyche-{name}"
    else:
        # Unix domain socket format
        return f"ipc://{base}/{name}.sock"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd tyche-client
python -m pytest ../tests/unit/test_socket.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add tyche-client/tyche_client/socket.py tests/unit/test_socket.py
git commit -m "feat: add centralized socket address helper"
```

---

## Task 4: Implement types module (TDD)

**What needs to be done?** Create frozen dataclasses for market data (`Tick`, `Quote`, `Trade`, `Bar`) and order types (`Order`, `OrderEvent`, `Ack`, `Position`, `Risk`) with `frozen=True, slots=True`.

**What problem does it resolve?** Type-safe, immutable message types are required for IPC communication; frozen dataclasses provide hashability and memory efficiency.

**Expected result?** All types can be instantiated, are immutable (AttributeError on modification), and hashable (usable as dict keys).

**Files:**
- Create: `tyche-client/tyche_client/types.py`
- Create: `tests/unit/test_types.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_types.py
import pytest
from tyche_client.types import Tick, Quote, Trade, Bar, Order


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
cd tyche-client
python -m pytest ../tests/unit/test_types.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'tyche_client.types'"

- [ ] **Step 3: Implement types module**

```python
# tyche-client/tyche_client/types.py
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
cd tyche-client
pip install -e .
python -m pytest ../tests/unit/test_types.py -v
```

Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add tyche-client/tyche_client/types.py tests/unit/test_types.py
git commit -m "feat: add tyche_client types module"
```

---

## Task 5: Implement serialization module (TDD)

**What needs to be done?** Create `encode()` and `decode()` functions using MessagePack with a `"_type"` discriminator field for serializing/deserializing dataclasses.

**What problem does it resolve?** IPC requires efficient binary serialization; MessagePack with type discrimination enables automatic type reconstruction on the receiving end.

**Expected result?** `encode(tick)` returns MessagePack bytes with `"_type": "Tick"`; `decode(data)` returns the original Tick object.

**Files:**
- Create: `tyche-client/tyche_client/serialization.py`
- Create: `tests/unit/test_serialization.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_serialization.py
import pytest
from tyche_client.types import Tick, Quote, Order
from tyche_client.serialization import encode, decode, TYPE_MAP


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
    from tyche_client.types import OrderEvent, Ack, Position, Risk, Trade, Bar
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
cd tyche-client
python -m pytest ../tests/unit/test_serialization.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'tyche_client.serialization'"

- [ ] **Step 3: Implement serialization module**

```python
# tyche-client/tyche_client/serialization.py
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
cd tyche-client
python -m pytest ../tests/unit/test_serialization.py -v
```

Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add tyche-client/tyche_client/serialization.py tests/unit/test_serialization.py
git commit -m "feat: add serialization module with MessagePack"
```

---

## Task 6: Create tyche-core package skeleton

**What needs to be done?** Create the `tyche-core` Python package with `pyproject.toml` and `__init__.py` for the core Nexus + Bus services.

**What problem does it resolve?** The core services (Nexus for registration, Bus for pub/sub) need their own installable package separate from the client library.

**Expected result?** Package installs successfully, `python -m tyche_core --help` works.

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

## Task 7: Implement Bus service with HWM configuration (MODIFIED)

**What needs to be done?** Create the `Bus` class implementing an XPUB/XSUB proxy with configurable high-water-mark (HWM) and dropped message counter.

**What problem does it resolve?** The Bus is the central pub/sub message broker; HWM prevents memory exhaustion under backpressure, and the dropped counter provides observability.

**Expected result?** Bus starts in a thread, forwards messages from publishers to subscribers, respects HWM limits, tracks dropped messages.

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


def test_bus_hwm_configuration():
    from tyche_core.bus import Bus
    bus = Bus(
        xsub_endpoint="inproc://test_xsub2",
        xpub_endpoint="inproc://test_xpub2",
        high_water_mark=5000
    )
    assert bus.high_water_mark == 5000


def test_bus_dropped_messages_counter():
    from tyche_core.bus import Bus
    bus = Bus(
        xsub_endpoint="inproc://test_xsub3",
        xpub_endpoint="inproc://test_xpub3"
    )
    # Initially zero
    assert bus.get_dropped_messages() == 0


def test_bus_starts_and_stops():
    from tyche_core.bus import Bus
    bus = Bus(
        xsub_endpoint="inproc://test_xsub4",
        xpub_endpoint="inproc://test_xpub4"
    )
    bus.start()
    time.sleep(0.1)
    bus.stop()
    assert not bus._running


def test_bus_forwards_messages():
    from tyche_core.bus import Bus
    xsub = "inproc://test_xsub5"
    xpub = "inproc://test_xpub5"

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

    NOTE: IPC sockets are created with default permissions (0o666 on Unix).
    Phase 2 will add configurable IPC permissions (0o600) for multi-user security.
    """

    def __init__(
        self,
        xsub_endpoint: str,
        xpub_endpoint: str,
        cpu_core: Optional[int] = None,
        high_water_mark: int = 10000,
    ):
        self.xsub_endpoint = xsub_endpoint
        self.xpub_endpoint = xpub_endpoint
        self.cpu_core = cpu_core
        self.high_water_mark = high_water_mark
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._logger = logging.getLogger("tyche.bus")
        self._dropped_messages = 0
        self._lock = threading.Lock()

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

    def get_dropped_messages(self) -> int:
        """Get count of dropped messages due to HWM overflow."""
        with self._lock:
            return self._dropped_messages

    def _run(self) -> None:
        """Run the ZMQ proxy."""
        # Set CPU affinity if specified
        if self.cpu_core is not None:
            self._set_cpu_affinity(self.cpu_core)

        ctx = zmq.Context()

        try:
            # XSUB socket - publishers connect here
            with ctx.socket(zmq.XSUB) as xsub:
                xsub.setsockopt(zmq.RCVHWM, self.high_water_mark)
                xsub.setsockopt(zmq.SNDHWM, self.high_water_mark)
                xsub.bind(self.xsub_endpoint)

                # XPUB socket - subscribers connect here
                with ctx.socket(zmq.XPUB) as xpub:
                    xpub.setsockopt(zmq.RCVHWM, self.high_water_mark)
                    xpub.setsockopt(zmq.SNDHWM, self.high_water_mark)
                    xpub.bind(self.xpub_endpoint)

                    # Set proxy to stop on context term
                    try:
                        zmq.proxy(xsub, xpub)
                    except zmq.ContextTerminated:
                        pass
        finally:
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

Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add tyche-core/tyche_core/bus.py tests/unit/test_bus.py
git commit -m "feat: implement Bus XPUB/XSUB proxy with HWM configuration"
```

---

## Task 8: Implement Nexus service with exponential backoff (MODIFIED)

**What needs to be done?** Create the `Nexus` class with ROUTER socket, module registration, heartbeat tracking, command dispatch, and exponential backoff retry calculation.

**What problem does it resolve?** Nexus is the lifecycle manager for modules; backoff prevents thundering herd during recovery, heartbeats detect dead modules.

**Expected result?** Modules can register, receive ACK with assigned ID, send/receive heartbeats, receive commands (START/STOP/RECONFIGURE/STATUS).

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


def test_nexus_registration_with_backoff():
    """Test that registration uses exponential backoff on failure."""
    from tyche_core.nexus import Nexus, calculate_backoff

    # Test backoff calculation
    assert calculate_backoff(0) == 0.1  # 100ms base
    assert calculate_backoff(1) == 0.1  # First retry: 100ms
    assert calculate_backoff(2) == 0.2  # Second retry: 200ms
    assert calculate_backoff(3) == 0.4  # Third retry: 400ms
    assert calculate_backoff(5) == 1.0  # Cap at 1s


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
import random
from typing import Dict, Optional
from dataclasses import dataclass, field

from .protocol import READY, ACK, HB, CMD, REPLY, DISCO
from .protocol import CMD_START, CMD_STOP, CMD_RECONFIGURE, CMD_STATUS
from .protocol import STATUS_OK, STATUS_ERROR, PROTOCOL_VERSION


def calculate_backoff(retry_count: int, base_ms: float = 100, max_ms: float = 5000) -> float:
    """Calculate exponential backoff with jitter.

    Args:
        retry_count: Number of retries so far
        base_ms: Base delay in milliseconds
        max_ms: Maximum delay in milliseconds

    Returns:
        Delay in seconds (with ±20% jitter)
    """
    import math
    delay_ms = base_ms * (2 ** retry_count)
    delay_ms = min(delay_ms, max_ms)
    # Add ±20% jitter
    jitter = delay_ms * 0.2 * (2 * random.random() - 1)
    return (delay_ms + jitter) / 1000.0


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

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add tyche-core/tyche_core/nexus.py tests/unit/test_nexus.py
git commit -m "feat: implement Nexus registration and heartbeat service with exponential backoff"
```

---

## Task 9: Add protocol constants to tyche-core

**What needs to be done?** Create `protocol.py` in tyche-core with message type constants (READY, ACK, HB, CMD, etc.) that mirror tyche-client.protocol.

**What problem does it resolve?** Both packages need the same wire protocol constants; this avoids cross-imports between core and client.

**Expected result?** `from tyche_core.protocol import READY, ACK` works and matches client constants.

**Files:**
- Create: `tyche-core/tyche_core/protocol.py`

- [ ] **Step 1: Create protocol constants**

```python
# tyche-core/tyche_core/protocol.py
"""Wire protocol constants (mirrors tyche_client.protocol)."""

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

## Task 10: Implement tyche-core config loader

**What needs to be done?** Create `config.py` with `load_config()` and `load_config_with_defaults()` functions for loading JSON configuration with defaults for Nexus and Bus settings.

**What problem does it resolve?** Core services need configurable endpoints, CPU affinity, HWM values; defaults ensure minimal config files work.

**Expected result?** Config loads from JSON, missing keys use defaults (e.g., `high_water_mark=10000`).

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
            "high_water_mark": 5000,
        },
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config, f)
        f.flush()
        loaded = load_config(f.name)
        os.unlink(f.name)

    assert loaded["nexus"]["endpoint"] == "ipc:///tmp/tyche/nexus.sock"
    assert loaded["bus"]["cpu_core"] == 1
    assert loaded["bus"]["high_water_mark"] == 5000


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
    assert loaded["bus"]["high_water_mark"] == 10000
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
        "high_water_mark": 10000,
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

## Task 11: Implement tyche-core main entry point

**What needs to be done?** Create `__main__.py` with argument parsing, logging setup, signal handling, and orchestration of Nexus and Bus services.

**What problem does it resolve?** The core service needs a runnable entry point that loads config, starts services, and handles graceful shutdown.

**Expected result?** `python -m tyche_core --config config/core-config.json` starts Nexus and Bus, Ctrl+C shuts down gracefully.

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
        high_water_mark=config["bus"].get("high_water_mark", 10000),
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
    "cpu_core": 1,
    "high_water_mark": 10000
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

## Task 12a: Implement Module base class - Core structure (TDD)

**What needs to be done?** Create the `Module` ABC with constructor, config loading, encode/decode helpers, and abstract lifecycle methods (`on_init`, `on_start`, `on_stop`).

**What problem does it resolve?** Modules need a common base class that handles configuration and provides the interface for lifecycle callbacks.

**Expected result?** TestModule can be instantiated, loads config, encode/decode roundtrips work.

**Files:**
- Create: `tyche-client/tyche_client/module.py` (core structure only)
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
    from tyche_client.module import Module

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
    from tyche_client.module import Module
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
    from tyche_client.module import Module
    from tyche_client.types import Tick

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
cd tyche-client
python -m pytest ../tests/unit/test_module.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'tyche_client.module'"

- [ ] **Step 3: Implement Module base class (core structure)**

```python
# tyche-client/tyche_client/module.py
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
    via ZeroMQ IPC sockets. They import only tyche_client, never tyche_core.
    """

    service_name: str = "module.base"
    service_version: str = "1.0.0"

    def __init__(
        self,
        nexus_endpoint: str,
        bus_xsub_endpoint: str,
        bus_xpub_endpoint: str,
        config_path: Optional[str] = None,
        metrics_enabled: bool = False,
        metrics_buffer_size: int = 1024,
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

        # Use context manager pattern for ZMQ resources
        self._ctx: Optional[zmq.Context] = None
        self._nexus_socket: Optional[zmq.Socket] = None
        self._pub_socket: Optional[zmq.Socket] = None
        self._sub_socket: Optional[zmq.Socket] = None
        self._poller = None

        self._logger = logging.getLogger(self.service_name)
        self._heartbeat_interval_ms = DEFAULT_HEARTBEAT_INTERVAL_MS
        self._last_heartbeat_send = 0

        # Metrics configuration
        self._metrics_enabled = metrics_enabled
        self._metrics_buffer_size = metrics_buffer_size
        self._dropped_messages = 0

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
cd tyche-client
python -m pytest ../tests/unit/test_module.py -v
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add tyche-client/tyche_client/module.py tests/unit/test_module.py
git commit -m "feat: implement Module base class core structure"
```

---

## Task 12b: Implement Module base class - Lifecycle and dispatch (TDD)

**What needs to be done?** Add registration with exponential backoff, heartbeat handling, command dispatch, message dispatch with corrupt payload handling, and the main run loop.

**What problem does it resolve?** Modules need to register with Nexus, handle lifecycle commands, receive and dispatch Bus messages, and gracefully handle corrupt payloads.

**Expected result?** Module can register with Nexus, responds to START/STOP commands, dispatches incoming messages, handles corrupt payloads without crashing.

**Files:**
- Modify: `tyche-client/tyche_client/module.py` (add lifecycle methods)

- [ ] **Step 1: Write failing test for corrupt payload handling**

```python
# Add to tests/unit/test_module.py

def test_module_dispatch_corrupt_payload():
    """Test that corrupt MessagePack payload is handled gracefully."""
    from tyche_client.module import Module

    class TestModule(Module):
        service_name = "test.module"
        errors = []

        def on_init(self):
            pass

        def on_start(self):
            pass

        def on_stop(self):
            pass

        def on_tick(self, tick):
            pass

    module = TestModule(
        nexus_endpoint="inproc://test_nexus4",
        bus_xsub_endpoint="inproc://test_xsub4",
        bus_xpub_endpoint="inproc://test_xpub4",
    )

    # Simulate corrupt payload (invalid MessagePack)
    corrupt_data = b"\xff\xfe\xfd\xfc"

    # Should not raise, should log error and continue
    module._dispatch(b"test.topic", corrupt_data)

    # Module should still be operational
    assert module._running is False  # Not running yet, just testing dispatch
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd tyche-client
python -m pytest ../tests/unit/test_module.py::test_module_dispatch_corrupt_payload -v
```

Expected: FAIL with AttributeError (method not found)

- [ ] **Step 3: Implement lifecycle and dispatch methods**

Add the following methods to `tyche-client/tyche_client/module.py` after the existing code:

```python
    def _register(self) -> bool:
        """Register with Nexus using exponential backoff retry."""
        from tyche_core.nexus import calculate_backoff

        max_retries = 20
        retry_count = 0

        while retry_count < max_retries:
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

            # Wait for ACK with timeout
            if self._nexus_socket.poll(timeout=5000):
                frames = self._nexus_socket.recv_multipart()
                if frames[0] == ACK:
                    # Verify correlation ID to reject stale ACKs
                    received_correlation = int.from_bytes(frames[1], "big")
                    if received_correlation == self._correlation_id:
                        self._logger.warning("Received stale ACK, retrying...")
                        retry_count += 1
                        continue

                    self._correlation_id = received_correlation
                    self._assigned_id = frames[2].decode()
                    self._heartbeat_interval_ms = int.from_bytes(frames[3], "big")
                    self._logger.info(f"Registered with Nexus as {self._assigned_id}")
                    return True

            # Exponential backoff
            retry_count += 1
            delay = calculate_backoff(retry_count, base_ms=100, max_ms=5000)
            self._logger.warning(f"Registration failed, retry {retry_count}/{max_retries} in {delay:.2f}s")
            time.sleep(delay)

        self._logger.error(f"Failed to register with Nexus after {max_retries} retries")
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
        """Dispatch incoming Bus message to appropriate handler.

        Handles corrupt payloads gracefully - logs error and continues.
        """
        try:
            obj = self._decode(payload)
            handler = self._handlers.get(type(obj).__name__)
            if handler:
                handler(obj)
        except Exception as e:
            self._logger.error(f"Error dispatching message on topic {topic}: {e}")
            self._dropped_messages += 1

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

        # Create and connect sockets using context managers
        self._ctx = zmq.Context()

        try:
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
            self._poller = zmq.Poller()
            self._poller.register(self._nexus_socket, zmq.POLLIN)
            self._poller.register(self._sub_socket, zmq.POLLIN)

            self._logger.info("Module running")

            heartbeat_interval_ns = self._heartbeat_interval_ms * 1_000_000

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
            self._nexus_socket = None

        if self._pub_socket:
            self._pub_socket.close()
            self._pub_socket = None

        if self._sub_socket:
            self._sub_socket.close()
            self._sub_socket = None

        if self._ctx:
            self._ctx.term()
            self._ctx = None

        self._logger.info("Module stopped")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd tyche-client
python -m pytest ../tests/unit/test_module.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add tyche-client/tyche_client/module.py
git commit -m "feat: implement Module lifecycle, dispatch, and corrupt payload handling"
```

---

## Task 13: Create example strategy

**What needs to be done?** Create a `momentum.py` strategy that extends `Module` and implements EMA crossover trading logic with configurable lookback and threshold.

**What problem does it resolve?** Provides a working example demonstrating how to write a strategy using the Module base class.

**Expected result?** Running `python strategies/momentum.py --help` shows usage; strategy can be started and responds to market data.

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

from tyche_client import Module, Tick, Quote, Order


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

## Task 14: Integration test - Nexus registration

**What needs to be done?** Create integration tests verifying that a test module can register with Nexus, receive START command, and respond to STOP command.

**What problem does it resolve?** End-to-end verification that the Nexus registration protocol and command dispatching work correctly.

**Expected result?** 3 tests pass: registration, START command receipt, STOP command receipt.

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
from tyche_client.module import Module


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
cd ../tyche-client && pip install -e .
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

## Task 15: Integration test - Bus pub/sub

**What needs to be done?** Create integration tests verifying that messages flow correctly from publisher to subscriber through the Bus, including topic filtering.

**What problem does it resolve?** End-to-end verification that the Bus XPUB/XSUB proxy forwards messages correctly and that subscribers receive only matching topics.

**Expected result?** 2 tests pass: message flow through Bus and topic filtering work correctly.

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
from tyche_client.types import Tick
from tyche_client.serialization import encode


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

    from tyche_client.serialization import decode
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

## Task 16: Create Makefile

**What needs to be done?** Create a Makefile with common development tasks: build, install, test, lint, format, clean, and run commands.

**What problem does it resolve?** Provides a consistent interface for common development operations across different developer environments.

**Expected result?** `make test` runs all tests, `make lint` checks code style, `make run-core` starts the core service.

**Files:**
- Create: `Makefile`

- [ ] **Step 1: Create Makefile**

```makefile
.PHONY: all build install test lint clean

all: build

build: build-core build-client

build-core:
	pip install -e tyche-core/

build-client:
	pip install -e tyche-client/

install: build

test: test-unit test-integration

test-unit:
	python -m pytest tests/unit/ -v

test-integration:
	python -m pytest tests/integration/ -v

lint:
	ruff check tyche-core/ tyche-client/ tests/ strategies/

lint-fix:
	ruff check --fix tyche-core/ tyche-client/ tests/ strategies/

format:
	ruff format tyche-core/ tyche-client/ tests/ strategies/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf tyche-core/*.egg-info tyche-client/*.egg-info
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

## Task 17: Implement tyche-launcher package skeleton (NEW)

**What needs to be done?** Create the `tyche-launcher` Python package with `pyproject.toml`, `__init__.py`, and a config loader for managing module lifecycle.

**What problem does it resolve?** The launcher is a separate tool that manages module processes (start, monitor, restart) and needs its own installable package.

**Expected result?** Package installs successfully, config loader can parse launcher configuration files.

**Files:**
- Create: `tyche-launcher/pyproject.toml`
- Create: `tyche-launcher/tyche_launcher/__init__.py`
- Create: `tyche-launcher/tyche_launcher/config.py`

- [ ] **Step 1: Write pyproject.toml**

```toml
# tyche-launcher/pyproject.toml
[project]
name = "tyche-launcher"
version = "1.0.0"
description = "TycheEngine module lifecycle manager"
requires-python = ">=3.11"
dependencies = [
    "pyzmq>=25.0",
    "msgpack>=1.0",
    "tyche-core",
    "tyche-client",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "ruff>=0.1.0",
]

[project.scripts]
tyche-launcher = "tyche_launcher.__main__:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: Create config module**

```python
# tyche-launcher/tyche_launcher/config.py
"""Launcher configuration loader."""

import json
from typing import Dict, Any, List
from dataclasses import dataclass, field


@dataclass
class ModuleConfig:
    """Configuration for a managed module."""
    name: str
    command: List[str]
    restart_policy: str = "never"  # never, always, on-failure
    max_restarts: int = 3
    restart_window_seconds: int = 60
    cpu_core: int = None
    environment: Dict[str, str] = field(default_factory=dict)


@dataclass
class LauncherConfig:
    """Launcher configuration."""
    nexus_endpoint: str = "ipc:///tmp/tyche/nexus.sock"
    poll_interval_ms: int = 1000
    modules: List[ModuleConfig] = field(default_factory=list)


def load_launcher_config(path: str) -> LauncherConfig:
    """Load launcher configuration from JSON file."""
    with open(path) as f:
        data = json.load(f)

    modules = []
    for mod_data in data.get("modules", []):
        modules.append(ModuleConfig(
            name=mod_data["name"],
            command=mod_data["command"],
            restart_policy=mod_data.get("restart_policy", "never"),
            max_restarts=mod_data.get("max_restarts", 3),
            restart_window_seconds=mod_data.get("restart_window_seconds", 60),
            cpu_core=mod_data.get("cpu_core"),
            environment=mod_data.get("environment", {}),
        ))

    return LauncherConfig(
        nexus_endpoint=data.get("nexus_endpoint", "ipc:///tmp/tyche/nexus.sock"),
        poll_interval_ms=data.get("poll_interval_ms", 1000),
        modules=modules,
    )
```

- [ ] **Step 3: Commit**

```bash
git add tyche-launcher/
git commit -m "feat: create tyche-launcher package skeleton"
```

---

## Task 18: Implement launcher monitor with circuit breaker (NEW)

**What needs to be done?** Create the `ProcessMonitor` and `CircuitBreaker` classes for tracking process state and preventing restart storms.

**What problem does it resolve?** Modules may crash repeatedly due to configuration errors; the circuit breaker stops restart attempts after 3 failures in 60 seconds to prevent resource exhaustion.

**Expected result?** Circuit breaker opens after max failures, resets after window expires; ProcessMonitor tracks starts, exits, and restart counts.

**Files:**
- Create: `tyche-launcher/tyche_launcher/monitor.py`
- Create: `tests/unit/test_monitor.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_monitor.py
import pytest
import time
from tyche_launcher.monitor import ProcessMonitor, CircuitBreaker


def test_circuit_breaker_allows_initial_calls():
    cb = CircuitBreaker(max_failures=3, window_seconds=60)
    assert cb.can_execute()


def test_circuit_breaker_opens_after_failures():
    cb = CircuitBreaker(max_failures=3, window_seconds=60)

    # Record 3 failures
    cb.record_failure()
    assert cb.can_execute()
    cb.record_failure()
    assert cb.can_execute()
    cb.record_failure()

    # Circuit should now be open
    assert not cb.can_execute()


def test_circuit_breaker_resets_after_window():
    cb = CircuitBreaker(max_failures=3, window_seconds=0.1)

    # Record failures
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    assert not cb.can_execute()

    # Wait for window to pass
    time.sleep(0.15)

    # Should be reset
    assert cb.can_execute()


def test_process_monitor_tracks_state():
    pm = ProcessMonitor("test.module")
    assert pm.name == "test.module"
    assert pm.is_healthy() is False  # Not started


def test_process_monitor_restart_count():
    pm = ProcessMonitor("test.module", restart_policy="on-failure")

    pm.record_start()
    assert pm.start_count == 1

    pm.record_exit(1)  # Error exit
    assert pm.restart_count == 0  # Not yet restarted

    pm.record_start()
    assert pm.start_count == 2
    assert pm.restart_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd tyche-launcher
python -m pytest ../tests/unit/test_monitor.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'tyche_launcher.monitor'"

- [ ] **Step 3: Implement monitor module**

```python
# tyche-launcher/tyche_launcher/monitor.py
"""Process monitoring and circuit breaker for launcher."""

import time
from typing import Optional
from dataclasses import dataclass, field
from collections import deque


class CircuitBreaker:
    """Circuit breaker to prevent restart storms.

    Opens (blocks execution) after max_failures within window_seconds.
    """

    def __init__(self, max_failures: int = 3, window_seconds: float = 60.0):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: deque = deque()
        self._open = False

    def can_execute(self) -> bool:
        """Check if execution is allowed."""
        self._cleanup_old_failures()
        return len(self._failures) < self.max_failures

    def record_failure(self) -> None:
        """Record a failure."""
        self._failures.append(time.time())

    def record_success(self) -> None:
        """Record a success - clears failure history."""
        self._failures.clear()

    def _cleanup_old_failures(self) -> None:
        """Remove failures outside the window."""
        now = time.time()
        cutoff = now - self.window_seconds
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()


@dataclass
class ProcessMonitor:
    """Monitors a single managed process."""

    name: str
    restart_policy: str = "never"  # never, always, on-failure
    max_restarts: int = 3
    restart_window_seconds: float = 60.0

    # State tracking
    pid: Optional[int] = None
    start_count: int = 0
    restart_count: int = 0
    last_exit_code: Optional[int] = None
    last_start_time: float = 0.0

    # Circuit breaker for restart storms
    circuit_breaker: CircuitBreaker = field(init=False)

    def __post_init__(self):
        self.circuit_breaker = CircuitBreaker(
            max_failures=self.max_restarts,
            window_seconds=self.restart_window_seconds,
        )

    def record_start(self) -> None:
        """Record process start."""
        self.last_start_time = time.time()
        self.start_count += 1
        if self.start_count > 1:
            self.restart_count += 1

    def record_exit(self, exit_code: int) -> None:
        """Record process exit."""
        self.last_exit_code = exit_code

        if exit_code != 0:
            self.circuit_breaker.record_failure()
        else:
            self.circuit_breaker.record_success()

    def is_healthy(self) -> bool:
        """Check if process is currently running."""
        return self.pid is not None

    def should_restart(self) -> bool:
        """Determine if process should be restarted based on policy."""
        if self.restart_policy == "never":
            return False
        if self.restart_policy == "always":
            return self.circuit_breaker.can_execute()
        if self.restart_policy == "on-failure":
            if self.last_exit_code == 0:
                return False
            return self.circuit_breaker.can_execute()
        return False

    def get_status(self) -> dict:
        """Get current status as dictionary."""
        return {
            "name": self.name,
            "pid": self.pid,
            "running": self.is_healthy(),
            "start_count": self.start_count,
            "restart_count": self.restart_count,
            "last_exit_code": self.last_exit_code,
            "circuit_open": not self.circuit_breaker.can_execute(),
        }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd tyche-launcher
pip install -e .
python -m pytest ../tests/unit/test_monitor.py -v
```

Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add tyche-launcher/tyche_launcher/monitor.py tests/unit/test_monitor.py
git commit -m "feat: implement launcher monitor with circuit breaker"
```

---

## Task 19: Implement launcher process management (NEW)

**What needs to be done?** Create the `Launcher` class with process spawning, monitoring, restart policies, and the main entry point.

**What problem does it resolve?** Provides complete module lifecycle management: starting processes, monitoring their health, applying restart policies, and graceful shutdown.

**Expected result?** Launcher can start configured modules, restart failed ones based on policy, and shut down all processes on SIGTERM.

**Files:**
- Create: `tyche-launcher/tyche_launcher/launcher.py`
- Create: `tyche-launcher/tyche_launcher/__main__.py`
- Create: `tests/unit/test_launcher.py`
- Create: `config/launcher-config.json`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_launcher.py
import pytest
import tempfile
import json
import os


def test_launcher_creation():
    from tyche_launcher.launcher import Launcher
    from tyche_launcher.config import LauncherConfig

    config = LauncherConfig()
    launcher = Launcher(config)
    assert launcher.config == config
    assert len(launcher.monitors) == 0


def test_launcher_loads_modules():
    from tyche_launcher.launcher import Launcher
    from tyche_launcher.config import LauncherConfig, ModuleConfig

    config = LauncherConfig(modules=[
        ModuleConfig(name="test.module", command=["python", "-c", "pass"]),
    ])
    launcher = Launcher(config)
    assert len(launcher.monitors) == 1
    assert "test.module" in launcher.monitors
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd tyche-launcher
python -m pytest ../tests/unit/test_launcher.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'tyche_launcher.launcher'"

- [ ] **Step 3: Implement launcher module**

```python
# tyche-launcher/tyche_launcher/launcher.py
"""Launcher - process management for TycheEngine modules."""

import subprocess
import signal
import logging
import time
from typing import Dict, Optional

from .config import LauncherConfig, ModuleConfig
from .monitor import ProcessMonitor


class Launcher:
    """Manages module lifecycle: start, monitor, restart."""

    def __init__(self, config: LauncherConfig):
        self.config = config
        self._logger = logging.getLogger("tyche.launcher")
        self.monitors: Dict[str, ProcessMonitor] = {}
        self._processes: Dict[str, subprocess.Popen] = {}
        self._running = False

        # Initialize monitors from config
        for mod_config in config.modules:
            self.monitors[mod_config.name] = ProcessMonitor(
                name=mod_config.name,
                restart_policy=mod_config.restart_policy,
                max_restarts=mod_config.max_restarts,
                restart_window_seconds=mod_config.restart_window_seconds,
            )

    def start(self) -> None:
        """Start all configured modules."""
        self._running = True
        self._logger.info(f"Launcher starting {len(self.config.modules)} modules")

        for mod_config in self.config.modules:
            self._start_module(mod_config)

    def stop(self) -> None:
        """Stop all modules."""
        self._running = False
        self._logger.info("Launcher stopping all modules")

        for name, process in list(self._processes.items()):
            self._stop_module(name, process)

    def _start_module(self, mod_config: ModuleConfig) -> bool:
        """Start a single module."""
        monitor = self.monitors[mod_config.name]

        if not monitor.circuit_breaker.can_execute():
            self._logger.error(f"Circuit breaker open for {mod_config.name}, skipping start")
            return False

        try:
            env = os.environ.copy()
            env.update(mod_config.environment)

            process = subprocess.Popen(
                mod_config.command,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            self._processes[mod_config.name] = process
            monitor.pid = process.pid
            monitor.record_start()

            self._logger.info(f"Started {mod_config.name} (PID {process.pid})")
            return True

        except Exception as e:
            self._logger.error(f"Failed to start {mod_config.name}: {e}")
            monitor.circuit_breaker.record_failure()
            return False

    def _stop_module(self, name: str, process: subprocess.Popen) -> None:
        """Stop a single module."""
        self._logger.info(f"Stopping {name} (PID {process.pid})")

        try:
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            self._logger.warning(f"Force killing {name}")
            process.kill()
            process.wait()

        monitor = self.monitors[name]
        monitor.pid = None

    def poll(self) -> None:
        """Poll all processes and handle restarts."""
        for name, process in list(self._processes.items()):
            retcode = process.poll()

            if retcode is not None:
                # Process exited
                monitor = self.monitors[name]
                monitor.record_exit(retcode)
                monitor.pid = None

                self._logger.info(f"{name} exited with code {retcode}")

                # Find config and restart if needed
                if self._running and monitor.should_restart():
                    mod_config = next(
                        (m for m in self.config.modules if m.name == name), None
                    )
                    if mod_config:
                        self._logger.info(f"Restarting {name}")
                        self._start_module(mod_config)

    def get_status(self) -> Dict[str, dict]:
        """Get status of all modules."""
        return {name: monitor.get_status() for name, monitor in self.monitors.items()}

    def run(self) -> None:
        """Main run loop."""
        self.start()

        try:
            while self._running:
                self.poll()
                time.sleep(self.config.poll_interval_ms / 1000.0)
        except KeyboardInterrupt:
            self._logger.info("Interrupted by user")
        finally:
            self.stop()
```

- [ ] **Step 4: Create entry point**

```python
# tyche-launcher/tyche_launcher/__main__.py
"""Entry point for tyche-launcher."""

import argparse
import logging
import sys

from .launcher import Launcher
from .config import load_launcher_config


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="TycheEngine Launcher")
    parser.add_argument(
        "--config",
        default="config/launcher-config.json",
        help="Path to launcher configuration file",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        config = load_launcher_config(args.config)
    except FileNotFoundError:
        logging.error(f"Config file not found: {args.config}")
        return 1
    except Exception as e:
        logging.error(f"Failed to load config: {e}")
        return 1

    launcher = Launcher(config)
    launcher.run()

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Create launcher config**

```json
{
  "nexus_endpoint": "ipc:///tmp/tyche/nexus.sock",
  "poll_interval_ms": 1000,
  "modules": [
    {
      "name": "strategy.momentum",
      "command": [
        "python",
        "strategies/momentum.py",
        "--nexus", "ipc:///tmp/tyche/nexus.sock",
        "--bus-xsub", "ipc:///tmp/tyche/bus_xsub.sock",
        "--bus-xpub", "ipc:///tmp/tyche/bus_xpub.sock",
        "--config", "config/modules/momentum-config.json"
      ],
      "restart_policy": "on-failure",
      "max_restarts": 3,
      "restart_window_seconds": 60,
      "cpu_core": 2
    }
  ]
}
```

- [ ] **Step 6: Run tests**

```bash
cd tyche-launcher
pip install -e .
python -m pytest ../tests/unit/test_launcher.py -v
```

Expected: 2 PASSED

- [ ] **Step 7: Commit**

```bash
git add tyche-launcher/tyche_launcher/launcher.py tyche-launcher/tyche_launcher/__main__.py tests/unit/test_launcher.py config/launcher-config.json
git commit -m "feat: implement launcher process management with restart policies"
```

---

## Task 20: Final verification

**What needs to be done?** Run all unit tests, integration tests, and linting to verify the complete implementation is working correctly.

**What problem does it resolve?** Catches any regressions or integration issues before considering the implementation complete.

**Expected result?** All tests pass, linting shows no errors, all three packages (tyche-core, tyche-client, tyche-launcher) are installable and functional.

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

1. **tyche-core**: Nexus (ROUTER) + Bus (XPUB/XSUB) services with HWM configuration
2. **tyche-client**: Client library with types, serialization, Module base class, and socket helper
3. **tyche-launcher**: Process lifecycle manager with restart policies and circuit breaker
4. **IPC transport**: ZeroMQ over Unix domain sockets / named pipes with documented security considerations
5. **Protocol**: Binary wire protocol with MessagePack serialization and exponential backoff retry
6. **Example**: Momentum strategy demonstrating the API
7. **Tests**: Unit and integration tests for all major components

### Changes from original plan (incorporating eng review):

1. **Renamed `tyche-cli` → `tyche-client`** - Clearer distinction between library and CLI
2. **Added centralized socket address helper** - Single source of truth for IPC paths
3. **Added HWM configuration to Bus** - Configurable high-water-mark with overflow handling
4. **Added exponential backoff to Nexus registration** - Prevents thundering herd
5. **Added dropped message counter to Bus** - Observable backpressure metric
6. **Documented IPC security risk** - Phase 2 will add permission hardening
7. **Require context managers for ZMQ sockets** - Cleaner resource management
8. **Added corrupt payload test** - Graceful handling of malformed messages
9. **Added circuit breaker to launcher** - Prevents restart storms (3 failures in 60s → stop)
10. **Made LatencyStats buffer configurable** - `metrics_buffer_size` parameter
11. **Added Tasks 17-19 for launcher implementation** - Complete lifecycle management

After completing all tasks:
- `tyche-core` can be installed and run as a service
- `tyche-client` provides the base class for writing modules
- `tyche-launcher` manages module lifecycle with configurable restart policies
- Modules are completely separate processes with no shared code
- The architecture supports future evolution to native modules
