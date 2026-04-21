---
name: Phase 1 Pattern Map
description: Existing codebase patterns for persistence backend implementation
type: reference
---

# Pattern Map: Phase 1 — Schema & Backend Foundation

**Mapped:** 2026-04-21
**Files analyzed:** 10
**Analogs found:** 9 / 10

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/modules/trading/persistence/backend.py` | interface | CRUD | `src/modules/trading/gateway/base.py` GatewayModule | exact |
| `src/modules/trading/persistence/clickhouse_backend.py` | service | CRUD | `src/modules/trading/oms/order_store.py` (if exists) or `GatewayModule` | partial |
| `src/modules/trading/persistence/jsonl_backend.py` | service | file-I/O | `src/modules/trading/store/recorder.py` DataRecorderModule | exact |
| `src/modules/trading/persistence/schema.py` | utility | batch | `src/modules/trading/models/order.py` dataclass patterns | role-match |
| `src/modules/trading/persistence/__init__.py` | config | — | `src/modules/trading/models/__init__.py` | exact |
| `docker/clickhouse-compose.yml` | config | — | None found | no analog |
| `tests/unit/test_backend.py` | test | request-response | `tests/unit/test_message.py` | role-match |
| `tests/integration/test_clickhouse_backend.py` | test | request-response | `tests/integration/test_engine_module.py` | role-match |

## Pattern Assignments

### `src/modules/trading/persistence/backend.py` (interface, CRUD)

**Analog:** `src/modules/trading/gateway/base.py` (GatewayModule)

**Imports pattern** (lines 1-19):
```python
"""Abstract base class for exchange/venue gateway modules.

A Gateway is a TycheModule that bridges external exchange APIs with the internal
event system. Each venue should have its own Gateway process for fault isolation.
"""

import logging
import time
from abc import abstractmethod
from typing import Any, Dict, List, Optional

from modules.trading import events
from modules.trading.models.enums import OrderStatus
from modules.trading.models.order import Fill, Order, OrderUpdate
from modules.trading.models.tick import Bar, Quote, Trade
from tyche.module import TycheModule
from tyche.types import DurabilityLevel, Endpoint, InterfacePattern

logger = logging.getLogger(__name__)
```

**Abstract base pattern** (lines 22-114):
```python
class GatewayModule(TycheModule):
    """Abstract base for exchange gateway modules.

    Subclasses implement venue-specific connectivity while this base
    provides standardized event publishing and order handling.
    """

    def __init__(
        self,
        engine_endpoint: Endpoint,
        venue_name: str,
        module_id: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(engine_endpoint, module_id=module_id, **kwargs)
        self.venue_name = venue_name
        self._subscribed_instruments: List[str] = []
        self._connected = False

    # --- Abstract methods (venue-specific implementation) ---

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the exchange."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the exchange."""
        ...

    @abstractmethod
    def submit_order(self, order: Order) -> OrderUpdate:
        """Submit an order to the exchange."""
        ...
```

**Error handling pattern** (lines 158-169):
```python
        try:
            result = self.submit_order(order)
            return result.to_dict()
        except Exception as e:
            logger.error("Order execution failed: %s", e)
            return OrderUpdate(
                order_id=order.order_id,
                instrument_id=order.instrument_id,
                status=OrderStatus.REJECTED,
                timestamp=time.time(),
                reason=str(e),
            ).to_dict()
```

### What to replicate
- Use `from abc import abstractmethod` for interface definitions.
- Use module-level `logger = logging.getLogger(__name__)`.
- Use `**kwargs: Any` in `__init__` to allow subclasses to pass extra config.
- Use `try/except` + `logger.error` for operational error handling, returning result objects rather than raising.

### What to adapt
- `PersistenceBackend` is NOT a `TycheModule` — it is a plain Python ABC with no ZMQ dependency.
- Remove `engine_endpoint`, `module_id`, and `add_interface` patterns.
- Replace gateway-specific methods (`connect`, `submit_order`) with `insert_batch()`, `query()`, `health()`, `ensure_schema()`.

---

### `src/modules/trading/persistence/jsonl_backend.py` (service, file-I/O)

**Analog:** `src/modules/trading/store/recorder.py` (DataRecorderModule)

**Imports pattern** (lines 1-16):
```python
"""Data recorder module - persists market data and trading events.

Subscribes to market data events and writes them to storage for
later replay/backtesting or analysis.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.trading import events
from tyche.module import TycheModule
from tyche.types import Endpoint, InterfacePattern

logger = logging.getLogger(__name__)
```

**File I/O pattern** (lines 91-111):
```python
    def _record_event(self, payload: Dict[str, Any]) -> None:
        """Write event payload to file as JSON line."""
        record = {
            "timestamp": time.time(),
            "data": payload,
        }

        # Determine file path based on date and event type
        date_str = time.strftime("%Y-%m-%d")
        instrument_id = payload.get("instrument_id", "system")
        event_type = self._infer_event_type(payload)

        file_path = self._data_dir / date_str / f"{instrument_id}_{event_type}.jsonl"
        file_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
            self._event_count += 1
        except OSError as e:
            logger.error("Failed to write record: %s", e)
```

**Directory/path pattern** (lines 32-44):
```python
    def __init__(
        self,
        engine_endpoint: Endpoint,
        data_dir: str = "./data/recorded",
        instrument_ids: Optional[List[str]] = None,
        record_fills: bool = True,
        record_orders: bool = True,
        module_id: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(engine_endpoint, module_id=module_id, **kwargs)
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
```

### What to replicate
- Use `pathlib.Path` for all path operations; call `.mkdir(parents=True, exist_ok=True)` before writing.
- Use `json.dumps(record, default=str)` for serialization fallback.
- Use `time.strftime("%Y-%m-%d")` for date-partitioned directories.
- Use `try/except OSError` around file writes with `logger.error`.
- Use `self._event_count` for simple operational metrics.

### What to adapt
- `JsonlBackend` should NOT inherit from `TycheModule`; it is a plain class implementing `PersistenceBackend`.
- Replace `_record_event(payload)` with `insert_batch(rows: List[Dict[str, Any]])`.
- Replace `json.dumps(record, default=str)` with `json.dumps(row, default=str)` where `row` already contains `timestamp`, `event_type`, `instrument_id`, `module_id`, `payload`.
- Add `query()` method that reads JSONL files, filters by date range, and returns `QueryResult`.

---

### `src/modules/trading/persistence/schema.py` (utility, batch)

**Analog:** `src/modules/trading/models/order.py` (dataclass + to_dict/from_dict)

**Dataclass pattern** (lines 16-35):
```python
@dataclass
class Order:
    """Represents a trading order through its lifecycle."""

    instrument_id: str  # String form of InstrumentId
    side: Side
    order_type: OrderType
    quantity: Decimal
    price: Optional[Decimal] = None  # Required for LIMIT/STOP_LIMIT
    stop_price: Optional[Decimal] = None  # Required for STOP/STOP_LIMIT
    time_in_force: TimeInForce = TimeInForce.GTC
    status: OrderStatus = OrderStatus.NEW
    order_id: str = field(default_factory=_generate_order_id)
```

**to_dict / from_dict pattern** (lines 59-98):
```python
    def to_dict(self) -> Dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "side": self.side.name,
            "order_type": self.order_type.name,
            "quantity": str(self.quantity),
            "price": str(self.price) if self.price else None,
            "stop_price": str(self.stop_price) if self.stop_price else None,
            "time_in_force": self.time_in_force.name,
            "status": self.status.name,
            "order_id": self.order_id,
            "venue_order_id": self.venue_order_id,
            "filled_quantity": str(self.filled_quantity),
            "avg_fill_price": str(self.avg_fill_price) if self.avg_fill_price else None,
            "strategy_id": self.strategy_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tag": self.tag,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Order":
        return cls(
            instrument_id=d["instrument_id"],
            side=Side[d["side"]],
            order_type=OrderType[d["order_type"]],
            quantity=Decimal(d["quantity"]),
            price=Decimal(d["price"]) if d.get("price") else None,
            stop_price=Decimal(d["stop_price"]) if d.get("stop_price") else None,
            time_in_force=TimeInForce[d["time_in_force"]],
            status=OrderStatus[d["status"]],
            order_id=d["order_id"],
            venue_order_id=d.get("venue_order_id"),
            filled_quantity=Decimal(d["filled_quantity"]),
            avg_fill_price=Decimal(d["avg_fill_price"]) if d.get("avg_fill_price") else None,
            strategy_id=d.get("strategy_id"),
            created_at=d.get("created_at", 0.0),
            updated_at=d.get("updated_at", 0.0),
            tag=d.get("tag"),
        )
```

### What to replicate
- Use `@dataclass` for all result types (`InsertResult`, `QueryResult`, `SchemaMeta`).
- Use `field(default_factory=...)` for mutable defaults.
- Use `to_dict()` / `from_dict()` for serialization round-trips.
- Use `Decimal(d["price"])` pattern for numeric fields that need precision.

### What to adapt
- `InsertResult` and `QueryResult` are simpler than `Order` — no nested enums or Decimal fields.
- Schema DDL strings should live as module-level constants (not in dataclasses).
- Add a `SchemaManager` class with `ensure_schema(client)` and `get_version(client)` methods.

---

### `src/modules/trading/persistence/__init__.py` (config)

**Analog:** `src/modules/trading/models/__init__.py`

**Package export pattern** (lines 1-37):
```python
"""Trading domain models - pure data classes with no ZMQ dependency."""

from modules.trading.models.account import Account, Balance
from modules.trading.models.enums import (
    AssetClass,
    OrderStatus,
    OrderType,
    PositionSide,
    Side,
    TimeInForce,
    VenueType,
)
from modules.trading.models.instrument import Instrument, InstrumentId
from modules.trading.models.order import Fill, Order, OrderUpdate
from modules.trading.models.position import Position
from modules.trading.models.tick import Bar, Quote, Trade

__all__ = [
    "AssetClass",
    "OrderStatus",
    "OrderType",
    "PositionSide",
    "Side",
    "TimeInForce",
    "VenueType",
    "Instrument",
    "InstrumentId",
    "Bar",
    "Quote",
    "Trade",
    "Fill",
    "Order",
    "OrderUpdate",
    "Position",
    "Account",
    "Balance",
]
```

### What to replicate
- Use docstring describing the package purpose.
- Use explicit imports (not `from .module import *`).
- Define `__all__` explicitly for IDE autocompletion and clean public API.

### What to adapt
- Export `PersistenceBackend`, `ClickHouseBackend`, `JsonlBackend`, `InsertResult`, `QueryResult`, `SchemaManager`.

---

### `tests/unit/test_backend.py` (test, request-response)

**Analog:** `tests/unit/test_message.py`

**Test structure pattern** (lines 1-104):
```python
"""Tests for message serialization and deserialization."""

from decimal import Decimal

from tyche.message import (
    Envelope,
    Message,
    deserialize,
    deserialize_envelope,
    serialize,
    serialize_envelope,
)
from tyche.types import DurabilityLevel, MessageType


def test_message_creation():
    """Message stores all fields correctly."""
    msg = Message(
        msg_type=MessageType.EVENT,
        sender="zeus123456",
        event="on_data",
        payload={"value": 42},
    )
    assert msg.msg_type == MessageType.EVENT
    assert msg.sender == "zeus123456"
    assert msg.event == "on_data"
    assert msg.payload == {"value": 42}
    assert msg.recipient is None
    assert msg.timestamp is None
    assert msg.correlation_id is None


def test_message_serialization_roundtrip():
    """Message survives serialize -> deserialize roundtrip."""
    original = Message(
        msg_type=MessageType.COMMAND,
        sender="athena456",
        event="ack_order",
        payload={"order_id": "A123", "quantity": 100},
        recipient="hermes789",
        durability=DurabilityLevel.SYNC_FLUSH,
        timestamp=1234567890.123,
        correlation_id="corr-001",
    )

    data = serialize(original)
    restored = deserialize(data)

    assert restored.msg_type == original.msg_type
    assert restored.sender == original.sender
    assert restored.event == original.event
    assert restored.payload == original.payload
    assert restored.recipient == original.recipient
    assert restored.durability == original.durability
    assert restored.timestamp == original.timestamp
    assert restored.correlation_id == original.correlation_id
```

### What to replicate
- Use plain `def test_*` functions (no classes).
- Use descriptive docstrings for each test.
- Test round-trip fidelity explicitly.
- Test edge cases (None fields, empty payloads).

### What to adapt
- Test `JsonlBackend` with a temporary directory (`tmp_path` pytest fixture).
- Test `ClickHouseBackend` with mocked `clickhouse_connect` client.
- Test `InsertResult` / `QueryResult` dataclass construction and defaults.

---

### `tests/integration/test_clickhouse_backend.py` (test, request-response)

**Analog:** `tests/integration/test_engine_module.py`

**Integration test pattern** (lines 1-88):
```python
"""Integration tests for 2-node Tyche Engine system.

Tests actual Engine + Module interaction using real ZMQ sockets.
"""

import time

from tyche.engine import TycheEngine
from tyche.example_module import ExampleModule
from tyche.module import TycheModule
from tyche.types import Endpoint


def test_module_registration():
    """Module registers with Engine and appears in the module registry."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 24000),
        event_endpoint=Endpoint("127.0.0.1", 24002),
        heartbeat_endpoint=Endpoint("127.0.0.1", 24004),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 24006),
    )
    engine.start_nonblocking()
    time.sleep(0.3)

    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 24000),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 24006),
        module_id="reg_test_mod",
    )

    try:
        module.start_nonblocking()
        time.sleep(0.5)

        assert module._registered
        assert "reg_test_mod" in engine.modules
        assert engine.modules["reg_test_mod"].module_id == "reg_test_mod"
    finally:
        module.stop()
        engine.stop()
```

**Cleanup pattern** (lines 32-40, 73-88):
```python
    try:
        module.start_nonblocking()
        time.sleep(0.5)
        # ... assertions ...
    finally:
        module.stop()
        engine.stop()
```

### What to replicate
- Use `try/finally` for resource cleanup in every integration test.
- Use `time.sleep()` for async stabilization (acceptable for integration tests).
- Use descriptive docstrings.

### What to adapt
- Use `pytest` fixtures for Docker ClickHouse container lifecycle (e.g., `testcontainers` or `docker-compose` via subprocess).
- Test `ClickHouseBackend.insert_batch()` followed by `query()` to verify round-trip.
- Test schema creation via `SchemaManager.ensure_schema()`.
- No ZMQ in these tests — pure backend/DB integration.

---

## Shared Patterns

### Dataclass + to_dict/from_dict
**Source:** `src/modules/trading/models/order.py`, `src/modules/trading/models/tick.py`
**Apply to:** `InsertResult`, `QueryResult`, `SchemaMeta`, event row dicts
```python
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class InsertResult:
    success: bool
    rows_inserted: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "rows_inserted": self.rows_inserted,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "InsertResult":
        return cls(
            success=d["success"],
            rows_inserted=d.get("rows_inserted", 0),
            error=d.get("error"),
        )
```

### Logging Convention
**Source:** `src/modules/trading/store/recorder.py`, `src/tyche/module.py`
**Apply to:** All persistence modules
```python
import logging

logger = logging.getLogger(__name__)

# In methods:
logger.error("Failed to write record: %s", e)
logger.info("DataRecorder stopped. Total events recorded: %d", self._event_count)
```

### Error Handling (Operational)
**Source:** `src/modules/trading/gateway/base.py`, `src/modules/trading/store/recorder.py`
**Apply to:** `ClickHouseBackend.insert_batch()`, `JsonlBackend.insert_batch()`
```python
try:
    # ... do work ...
    return InsertResult(success=True, rows_inserted=len(rows))
except Exception as e:
    logger.error("Batch insert failed: %s", e)
    return InsertResult(success=False, error=str(e))
```

### Pathlib + mkdir Pattern
**Source:** `src/modules/trading/store/recorder.py`
**Apply to:** `JsonlBackend`
```python
from pathlib import Path

self._data_dir = Path(data_dir)
self._data_dir.mkdir(parents=True, exist_ok=True)

file_path = self._data_dir / date_str / f"{instrument_id}_{event_type}.jsonl"
file_path.parent.mkdir(parents=True, exist_ok=True)
```

### msgpack Serialization
**Source:** `src/tyche/message.py`
**Apply to:** Payload encoding in `ClickHouseBackend` and `JsonlBackend`
```python
import msgpack

def _encode_decimal(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return {"__decimal__": str(obj)}
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, bytes):
        return obj.decode("utf-8")
    raise TypeError(f"Cannot serialize {type(obj)}")

payload_bytes = msgpack.packb(payload, default=_encode_decimal, use_bin_type=True)
```

### Threading + Graceful Shutdown
**Source:** `src/tyche/module.py`
**Apply to:** Phase 2 `PersistenceModule` (not Phase 1 backends, but good to note)
```python
self._running = False
self._stop_event.set()

for t in self._threads:
    t.join(timeout=2.0)

for sock in [self._pub_socket, self._sub_socket, self._heartbeat_socket]:
    if sock is not None:
        sock.close()

if self.context:
    self.context.destroy(linger=0)
    self.context = None
```

### Test Configuration
**Source:** `tests/conftest.py`
**Apply to:** All new test files
```python
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
```

### pyproject.toml Optional Dependencies
**Source:** `pyproject.toml` lines 14-18
**Apply to:** Add `clickhouse-connect` under `[project.optional-dependencies]`
```toml
[project.optional-dependencies]
ctp = [
    "openctp-ctp>=6.7.0",
]
persistence = [
    "clickhouse-connect>=0.7.0",
]
```

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `docker/clickhouse-compose.yml` | config | — | No existing Docker Compose files in the codebase |

## Metadata

**Analog search scope:** `src/modules/trading/`, `src/tyche/`, `tests/unit/`, `tests/integration/`
**Files scanned:** 25+
**Pattern extraction date:** 2026-04-21
